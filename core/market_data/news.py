"""뉴스 파싱·캐싱. 요약은 Gemini Gateway에 위임한다 (docs/BIN.md).

뉴스 소스는 API 키가 필요 없는 무료 RSS 피드를 사용한다 — KR은 Google News RSS 검색,
US는 Yahoo Finance RSS 헤드라인 피드. `_infer_market`과 동일한 규칙(숫자 종목코드 → KR,
알파벳 티커 → US)으로 심볼만 보고 시장을 판별한다 (docs/INTERNAL_API.md 참고).
"""

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
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


def _feed_url(symbol: str) -> str:
    """숫자 종목코드는 KR(Google News RSS 검색), 알파벳 티커는 US(Yahoo Finance RSS).

    symbol은 URL 인코딩해 쿼리 파라미터 주입(&·= 등)이 불가능하게 한다.
    """
    encoded = quote(symbol, safe="")
    if symbol.isdigit():
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


async def get_news_summary(symbol: str) -> str:
    articles = await fetch_news(symbol)
    return await gemini_gateway.summarize_news(articles)
