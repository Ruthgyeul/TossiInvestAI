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


@pytest.mark.asyncio
async def test_get_news_summary_delegates_to_gemini(
    fake_redis, monkeypatch: pytest.MonkeyPatch  # noqa: ANN001
) -> None:
    async def _fetch_news(symbol: str) -> list[str]:
        return ["헤드라인 1"]

    async def _summarize_news(articles: list[str]) -> str:
        assert articles == ["헤드라인 1"]
        return "요약 결과"

    monkeypatch.setattr(news, "fetch_news", _fetch_news)
    monkeypatch.setattr(news.gemini_gateway, "summarize_news", _summarize_news)

    result = await news.get_news_summary("005930")

    assert result == "요약 결과"
