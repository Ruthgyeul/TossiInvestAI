"""뉴스 파싱·캐싱. 요약은 Gemini Gateway에 위임한다 (docs/BIN.md).

뉴스 소스는 API 키가 필요 없는 무료 RSS 피드를 사용한다 — KR 종목은 Google News RSS
검색, US 종목은 Yahoo Finance RSS 헤드라인 피드. `_infer_market`과 동일한 규칙(숫자
종목코드 → KR, 알파벳 티커 → US)으로 심볼만 보고 시장을 판별한다 (docs/INTERNAL_API.md 참고).

종목별 뉴스와 별개로, KR 종목에는 시장 전반 경제 뉴스(한국경제·매일경제·서울경제·머니투데이
RSS)를 함께 제공한다 — 매크로 헤드라인은 개별 종목 결정의 배경 컨텍스트로 쓰인다. 시장
전반 뉴스는 종목과 무관하므로 종목별로 중복 요청하지 않고 `news:market:{market}` 키로
한 번만 캐싱한다.
"""

import asyncio
import json
from urllib.parse import quote
from xml.etree.ElementTree import ParseError

import aiohttp
import structlog
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from core.db.redis import get_redis
from core.gateway.gemini import gemini_gateway

log = structlog.get_logger(__name__)

_NEWS_CACHE_TTL = 900  # 15분 — 트레이딩 루프 주기(15분)보다 자주 재요청하지 않는다
_MAX_ARTICLES = 5
_MAX_MARKET_ARTICLES = 6  # 여러 경제지 피드를 병합하므로 종목별보다 상한을 조금 높인다
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)

# KR 시장 전반 경제 뉴스 RSS 피드 — 종목 무관 매크로 헤드라인. 무료·API 키 불필요.
# 개별 피드 장애는 병합 과정에서 조용히 무시되므로 일부 소스가 죽어도 나머지로 동작한다.
#
# 전부 HTTPS만 사용한다 — 평문 HTTP 피드는 경로상 공격자가 헤드라인을 변조해
# Gemini 요약 → Claude 결정 프롬프트로 주입할 수 있는 채널이 된다(보안 감사 M-01).
# HTTPS를 제공하지 않는 소스(서울경제 rss.hankooki.com)는 목록에서 제외했다.
_KR_ECONOMY_FEEDS = (
    "https://www.hankyung.com/feed/economy",    # 한국경제
    "https://www.mk.co.kr/rss/30100041/",       # 매일경제 (경제)
    "https://rss.mt.co.kr/mt_news.xml",         # 머니투데이
)

# 시장별 전반 뉴스 피드 매핑. US는 종목별 Yahoo Finance 피드로 충분해 전반 피드를 두지 않는다.
_MARKET_FEEDS: dict[str, tuple[str, ...]] = {"KR": _KR_ECONOMY_FEEDS}


def _is_kr_symbol(symbol: str) -> bool:
    """숫자 종목코드는 KR, 알파벳 티커는 US (`_feed_url`과 동일한 규칙)."""
    return symbol.isdigit()


def _feed_url(symbol: str) -> str:
    """숫자 종목코드는 KR(Google News RSS 검색), 알파벳 티커는 US(Yahoo Finance RSS).

    symbol은 URL 인코딩해 쿼리 파라미터 주입(&·= 등)이 불가능하게 한다.
    """
    encoded = quote(symbol, safe="")
    if _is_kr_symbol(symbol):
        return f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={encoded}&region=US&lang=en-US"


def _parse_rss_titles(xml_text: str, limit: int) -> list[str]:
    # defusedxml: 외부 피드 XML의 엔티티 확장(billion laughs)·외부 엔티티(XXE) 공격을 차단한다.
    try:
        root = ET.fromstring(xml_text)
    except (ParseError, DefusedXmlException):
        return []
    titles = [item.findtext("title") for item in root.iter("item")]
    return [title.strip() for title in titles if title and title.strip()][:limit]


def _merge_headlines(*groups: list[str]) -> list[str]:
    """여러 피드의 헤드라인을 순서를 보존하며 중복 제거해 병합한다."""
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for title in group:
            if title not in seen:
                seen.add(title)
                merged.append(title)
    return merged


async def _fetch_feed_titles(
    session: aiohttp.ClientSession, url: str, limit: int
) -> list[str]:
    """단일 RSS 피드에서 헤드라인을 가져온다. 개별 피드 장애는 삼키고 빈 리스트를 반환한다."""
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            xml_text = await response.text()
    except Exception as e:  # noqa: BLE001 — 개별 피드 장애가 뉴스 수집 전체를 막으면 안 된다
        log.warning("news_feed_fetch_failed", url=url, error=str(e))
        return []
    return _parse_rss_titles(xml_text, limit)


async def fetch_news(symbol: str) -> list[str]:
    """무료 RSS 피드에서 종목 관련 최신 헤드라인을 가져온다.

    Redis `news:{symbol}` 캐시 우선. 피드 장애·타임아웃은 예외를 삼키고 빈 리스트를
    반환한다 — 뉴스 수집 실패가 트레이딩 루프 전체를 막으면 안 된다.
    """
    redis = get_redis()
    key = f"news:{symbol}"
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)  # type: ignore[no-any-return]

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.get(_feed_url(symbol)) as response:
                response.raise_for_status()
                xml_text = await response.text()
    except Exception as e:  # noqa: BLE001 — 뉴스 소스 장애가 트레이딩 루프를 막으면 안 된다
        log.warning("news_fetch_failed", symbol=symbol, error=str(e))
        return []

    articles = _parse_rss_titles(xml_text, _MAX_ARTICLES)
    await redis.set(key, json.dumps(articles), ex=_NEWS_CACHE_TTL)
    return articles


async def fetch_market_news(market: str) -> list[str]:
    """시장 전반 경제 뉴스 헤드라인을 여러 RSS 피드에서 병합해 가져온다 (KR만 지원).

    Redis `news:market:{market}` 캐시 우선. 종목과 무관하므로 종목별로 중복 요청하지 않는다.
    피드는 동시에 조회하고 개별 장애는 무시한다 — 일부 소스가 죽어도 나머지로 동작한다.
    """
    feeds = _MARKET_FEEDS.get(market, ())
    if not feeds:
        return []

    redis = get_redis()
    key = f"news:market:{market}"
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)  # type: ignore[no-any-return]

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            groups = await asyncio.gather(
                *(_fetch_feed_titles(session, url, _MAX_ARTICLES) for url in feeds)
            )
    except Exception as e:  # noqa: BLE001 — 뉴스 소스 장애가 트레이딩 루프를 막으면 안 된다
        log.warning("market_news_fetch_failed", market=market, error=str(e))
        return []

    articles = _merge_headlines(*groups)[:_MAX_MARKET_ARTICLES]
    await redis.set(key, json.dumps(articles), ex=_NEWS_CACHE_TTL)
    return articles


async def get_news_summary(symbol: str) -> str:
    articles = await fetch_news(symbol)
    if _is_kr_symbol(symbol):
        # KR 종목: 시장 전반 경제 뉴스 헤드라인을 함께 제공해 매크로 배경을 반영한다.
        market_news = await fetch_market_news("KR")
        articles = _merge_headlines(articles, market_news)
    return await gemini_gateway.summarize_news(articles)
