"""core/market_data/news.py — 무료 RSS 뉴스 소스 단위 테스트 (docs/BIN.md)."""

import pytest
from aioresponses import aioresponses

from core.market_data import news

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item><title>삼성전자, 3분기 실적 예상치 상회</title><link>https://example.com/1</link></item>
    <item><title>반도체 업황 개선 전망</title><link>https://example.com/2</link></item>
  </channel>
</rss>
"""


def test_feed_url_picks_google_news_for_numeric_kr_symbol() -> None:
    url = news._feed_url("005930")
    assert url.startswith("https://news.google.com/rss/search")
    assert "005930" in url


def test_feed_url_picks_yahoo_finance_for_us_ticker() -> None:
    url = news._feed_url("AAPL")
    assert url.startswith("https://feeds.finance.yahoo.com/rss/2.0/headline")
    assert "AAPL" in url


def test_parse_rss_titles_extracts_and_limits() -> None:
    titles = news._parse_rss_titles(_SAMPLE_RSS, limit=1)
    assert titles == ["삼성전자, 3분기 실적 예상치 상회"]


def test_parse_rss_titles_returns_empty_on_malformed_xml() -> None:
    assert news._parse_rss_titles("not xml", limit=5) == []


def test_feed_url_encodes_symbol_against_query_injection() -> None:
    url = news._feed_url("AAPL&hl=en&extra=1")
    assert "&extra=1" not in url
    assert "AAPL%26hl%3Den%26extra%3D1" in url


def test_parse_rss_titles_blocks_entity_expansion_attack() -> None:
    """defusedxml — billion laughs 류 엔티티 확장 XML은 파싱을 거부하고 빈 목록을 반환한다."""
    bomb = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<rss version="2.0"><channel><item><title>&lol3;</title></item></channel></rss>
"""
    assert news._parse_rss_titles(bomb, limit=5) == []


@pytest.mark.asyncio
async def test_fetch_news_parses_feed_and_caches(fake_redis) -> None:  # noqa: ANN001
    with aioresponses() as mocked:
        mocked.get(news._feed_url("005930"), body=_SAMPLE_RSS)
        articles = await news.fetch_news("005930")

    assert articles == [
        "삼성전자, 3분기 실적 예상치 상회",
        "반도체 업황 개선 전망",
    ]

    # 캐시된 두 번째 호출은 HTTP 목업 없이도 성공해야 한다.
    with aioresponses():
        cached_articles = await news.fetch_news("005930")
    assert cached_articles == articles


@pytest.mark.asyncio
async def test_fetch_news_returns_empty_list_on_feed_failure(fake_redis) -> None:  # noqa: ANN001
    with aioresponses() as mocked:
        mocked.get(news._feed_url("005930"), status=500)
        articles = await news.fetch_news("005930")

    assert articles == []


def test_feed_url_picks_google_news_for_us_lowercase_stays_us() -> None:
    # 알파벳이 하나라도 있으면 US로 판별한다 (isdigit == False).
    assert not news._is_kr_symbol("AAPL")
    assert news._is_kr_symbol("005930")


def test_all_market_feeds_use_https() -> None:
    """보안 감사 M-01 — 평문 HTTP 피드는 MITM 헤드라인 주입 채널이 되므로 금지한다."""
    for feeds in news._MARKET_FEEDS.values():
        for url in feeds:
            assert url.startswith("https://"), f"평문 HTTP 피드 금지: {url}"


def test_merge_headlines_dedups_and_preserves_order() -> None:
    merged = news._merge_headlines(
        ["A", "B"],
        ["B", "C"],
        ["A", "D"],
    )
    assert merged == ["A", "B", "C", "D"]


@pytest.mark.asyncio
async def test_fetch_market_news_merges_feeds_and_caches(fake_redis) -> None:  # noqa: ANN001
    feed_a = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>한국은행 기준금리 동결</title></item>
      <item><title>공통 헤드라인</title></item>
    </channel></rss>"""
    feed_b = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>공통 헤드라인</title></item>
      <item><title>코스피 2600 회복</title></item>
    </channel></rss>"""

    with aioresponses() as mocked:
        # 3개 KR 경제 피드 중 2개는 정상, 1개는 장애 — 부분 실패에도 병합돼야 한다.
        feeds = news._KR_ECONOMY_FEEDS
        mocked.get(feeds[0], body=feed_a)
        mocked.get(feeds[1], body=feed_b)
        mocked.get(feeds[2], status=500)
        articles = await news.fetch_market_news("KR")

    assert articles == [
        "한국은행 기준금리 동결",
        "공통 헤드라인",
        "코스피 2600 회복",
    ]

    # 두 번째 호출은 캐시에서 HTTP 목업 없이 동일 결과를 반환해야 한다.
    with aioresponses():
        cached = await news.fetch_market_news("KR")
    assert cached == articles


@pytest.mark.asyncio
async def test_fetch_market_news_returns_empty_for_us(fake_redis) -> None:  # noqa: ANN001
    assert await news.fetch_market_news("US") == []


@pytest.mark.asyncio
async def test_get_news_summary_merges_market_news_for_kr(
    fake_redis, monkeypatch: pytest.MonkeyPatch  # noqa: ANN001
) -> None:
    async def _fetch_news(symbol: str) -> list[str]:
        return ["종목 헤드라인"]

    async def _fetch_market_news(market: str) -> list[str]:
        assert market == "KR"
        return ["시장 헤드라인"]

    async def _summarize_news(articles: list[str]) -> str:
        assert articles == ["종목 헤드라인", "시장 헤드라인"]
        return "요약 결과"

    monkeypatch.setattr(news, "fetch_news", _fetch_news)
    monkeypatch.setattr(news, "fetch_market_news", _fetch_market_news)
    monkeypatch.setattr(news.gemini_gateway, "summarize_news", _summarize_news)

    result = await news.get_news_summary("005930")

    assert result == "요약 결과"


@pytest.mark.asyncio
async def test_get_news_summary_skips_market_news_for_us(
    fake_redis, monkeypatch: pytest.MonkeyPatch  # noqa: ANN001
) -> None:
    async def _fetch_news(symbol: str) -> list[str]:
        return ["헤드라인 1"]

    async def _fetch_market_news(market: str) -> list[str]:
        raise AssertionError("US 종목은 시장 전반 뉴스를 요청하지 않아야 한다")

    async def _summarize_news(articles: list[str]) -> str:
        assert articles == ["헤드라인 1"]
        return "요약 결과"

    monkeypatch.setattr(news, "fetch_news", _fetch_news)
    monkeypatch.setattr(news, "fetch_market_news", _fetch_market_news)
    monkeypatch.setattr(news.gemini_gateway, "summarize_news", _summarize_news)

    result = await news.get_news_summary("AAPL")

    assert result == "요약 결과"
