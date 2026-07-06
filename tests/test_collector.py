"""core/market_data/collector.py 인기 종목/공포탐욕지수 대체 지표 단위 테스트.

docs/TOSS_API.md에 시장 전체 "인기 종목"·"공포탐욕지수" 엔드포인트가 없으므로, 관심 종목
자체의 거래량 급증·등락 비율만으로 계산하는 대체 지표를 검증한다.
"""

import pytest

from core.market_data import collector


def test_popular_top10_ranks_by_volume_ratio_descending() -> None:
    prices = {
        "A": {"volume_ratio": 1.2},
        "B": {"volume_ratio": 3.5},
        "C": {"volume_ratio": 2.0},
        "D": {},  # volume_ratio 없음 → 제외
    }

    assert collector._popular_top10(prices) == ["B", "C", "A"]


def test_popular_top10_limits_to_ten_symbols() -> None:
    prices = {f"S{i}": {"volume_ratio": float(i)} for i in range(15)}

    result = collector._popular_top10(prices)

    assert len(result) == 10
    assert result[0] == "S14"  # 가장 높은 volume_ratio


def test_fear_greed_index_all_advancing_is_100() -> None:
    prices = {
        "A": {"day_change_pct": 1.5},
        "B": {"day_change_pct": 0.3},
    }

    assert collector._fear_greed_index(prices) == 100


def test_fear_greed_index_all_declining_is_0() -> None:
    prices = {
        "A": {"day_change_pct": -1.5},
        "B": {"day_change_pct": -0.3},
    }

    assert collector._fear_greed_index(prices) == 0


def test_fear_greed_index_mixed_breadth() -> None:
    prices = {
        "A": {"day_change_pct": 1.0},
        "B": {"day_change_pct": -1.0},
        "C": {"day_change_pct": -0.5},
        "D": {"day_change_pct": 2.0},
    }

    # 4종목 중 2종목 상승 → 50
    assert collector._fear_greed_index(prices) == 50


def test_fear_greed_index_none_when_no_data() -> None:
    assert collector._fear_greed_index({"A": {}}) is None


@pytest.mark.asyncio
async def test_collect_symbol_computes_gap_pct_and_day_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """core/strategy/us/overnight.py의 익일 갭 대응이 사용하는 필드 (전일 종가 대비 당일 시가)."""

    async def _get_price(symbol):  # noqa: ANN001
        return {"price": 220.0}

    async def _get_candles(symbol, timeframe):  # noqa: ANN001
        return [
            {"open": 195.0, "close": 200.0, "volume": 100},
            {"open": 218.0, "close": 220.0, "volume": 120},
        ]

    async def _get_stock_warnings(symbol):  # noqa: ANN001
        return {"has_restriction": False}

    async def _get_news_summary(symbol):  # noqa: ANN001
        return "뉴스 없음"

    monkeypatch.setattr(collector.toss_market, "get_price", _get_price)
    monkeypatch.setattr(collector.toss_market, "get_candles", _get_candles)
    monkeypatch.setattr(collector.toss_market, "get_stock_warnings", _get_stock_warnings)
    monkeypatch.setattr(collector, "get_news_summary", _get_news_summary)

    entry = await collector._collect_symbol("US", "AAPL")

    assert entry["day_open"] == 218.0
    assert entry["gap_pct"] == pytest.approx(9.0)  # (218-200)/200*100


@pytest.mark.asyncio
async def test_collect_symbol_publishes_news_summary_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """docs/DISCORD.md "#stock-news: 뉴스 수집마다" — 실제 요약이 나오면 이벤트를 발행한다."""

    async def _get_price(symbol):  # noqa: ANN001
        return {"price": 75_000}

    async def _get_candles(symbol, timeframe):  # noqa: ANN001
        return [{"close": 74_000, "volume": 100}, {"close": 75_000, "volume": 120}]

    async def _get_stock_warnings(symbol):  # noqa: ANN001
        return {"has_restriction": False}

    async def _get_news_summary(symbol):  # noqa: ANN001
        return "실적 호조 전망"

    published: list[tuple[str, dict]] = []

    async def _publish_event(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        published.append((event_type, payload))

    monkeypatch.setattr(collector.toss_market, "get_price", _get_price)
    monkeypatch.setattr(collector.toss_market, "get_candles", _get_candles)
    monkeypatch.setattr(collector.toss_market, "get_stock_warnings", _get_stock_warnings)
    monkeypatch.setattr(collector, "get_news_summary", _get_news_summary)
    monkeypatch.setattr(collector, "publish_event", _publish_event)

    await collector._collect_symbol("KR", "005930")

    assert published == [("news_summary", {"symbol": "005930", "summary": "실적 호조 전망"})]


@pytest.mark.asyncio
async def test_collect_symbol_skips_event_when_no_news(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_price(symbol):  # noqa: ANN001
        return {"price": 75_000}

    async def _get_candles(symbol, timeframe):  # noqa: ANN001
        return []

    async def _get_stock_warnings(symbol):  # noqa: ANN001
        return {"has_restriction": False}

    async def _get_news_summary(symbol):  # noqa: ANN001
        return "뉴스 없음"

    async def _publish_should_not_be_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("뉴스가 없으면 이벤트를 발행하면 안 된다")

    monkeypatch.setattr(collector.toss_market, "get_price", _get_price)
    monkeypatch.setattr(collector.toss_market, "get_candles", _get_candles)
    monkeypatch.setattr(collector.toss_market, "get_stock_warnings", _get_stock_warnings)
    monkeypatch.setattr(collector, "get_news_summary", _get_news_summary)
    monkeypatch.setattr(collector, "publish_event", _publish_should_not_be_called)

    await collector._collect_symbol("KR", "005930")
