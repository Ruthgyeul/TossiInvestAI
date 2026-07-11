"""core/report/extras.py — 리포트 확장 지표 단위 테스트 (docs/REPORT.md "확장 지표")."""

from datetime import UTC, datetime, timedelta

import pytest

import core.report.extras as extras


def test_compute_unrealized_converts_us_and_sums() -> None:
    holdings = [
        {"symbol": "005930", "market": "KR", "quantity": 2, "avgPrice": 74_000.0,
         "currentPrice": 78_400.0, "pnlPct": 0.0595},
        {"symbol": "NVDA", "market": "US", "quantity": 3, "avgPrice": 158.0,
         "currentPrice": 172.3, "pnlPct": 0.0905},
    ]
    result = extras.compute_unrealized(holdings, rate=1_000.0)
    # KR 8,800 + US (14.3*3)*1000 = 42,900 → 51,700
    assert result["total_krw"] == 51_700
    assert result["total_pct"] > 0
    assert {r["symbol"] for r in result["rows"]} == {"005930", "NVDA"}


def test_compute_fx_none_without_rate() -> None:
    assert extras.compute_fx([], rate=None) is None


def test_compute_fx_exposure_and_sensitivity() -> None:
    holdings = [{"symbol": "NVDA", "market": "US", "quantity": 3, "currentPrice": 100.0}]
    fx = extras.compute_fx(holdings, rate=1_000.0)
    assert fx["us_exposure_krw"] == 300_000
    assert fx["sensitivity_1pct_krw"] == 3_000


def test_compute_bands_percent_b() -> None:
    prices = {"A": {"bb_upper": 110.0, "bb_lower": 90.0, "price": 100.0}}
    bands = extras.compute_bands(prices)
    assert bands[0]["pct_b"] == pytest.approx(0.5)
    assert bands[0]["bandwidth"] == pytest.approx(0.2)


def test_compute_bands_skips_incomplete() -> None:
    assert extras.compute_bands({"A": {"price": 100.0}}) == []


def test_compute_risk_lines_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extras.settings, "REPORT_STOP_LOSS_PCT", 0.10)
    monkeypatch.setattr(extras.settings, "REPORT_TAKE_PROFIT_PCT", 0.20)
    lines = extras.compute_risk_lines(
        [{"symbol": "005930", "market": "KR", "avgPrice": 100.0, "currentPrice": 105.0}]
    )
    assert lines[0]["stop"] == pytest.approx(90.0)
    assert lines[0]["take"] == pytest.approx(120.0)


def test_compute_alpha_excess_return() -> None:
    alpha = extras.compute_alpha([100.0, 110.0], [100.0, 105.0])
    assert alpha["portfolio_pct"] == pytest.approx(0.10)
    assert alpha["benchmark_pct"] == pytest.approx(0.05)
    assert alpha["alpha_pp"] == pytest.approx(0.05)


def test_compute_alpha_none_when_insufficient() -> None:
    assert extras.compute_alpha([100.0], [100.0, 105.0]) is None
    assert extras.compute_alpha([100.0, 110.0], []) is None


@pytest.mark.asyncio
async def test_compute_safety_usage_and_restricted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _realized(mode: str) -> int:
        return -5_000  # 오늘 5,000원 손실

    async def _ratio(symbol: str, mode: str) -> float:
        return 0.3

    async def _flags() -> dict:
        return {"emergency_stop": False, "kr_stop": True, "us_stop": False}

    monkeypatch.setattr(extras.db, "get_today_realized_pnl_krw", _realized)
    monkeypatch.setattr(extras.fund_manager, "get_position_ratio", _ratio)
    monkeypatch.setattr(extras.db, "get_control_flags", _flags)
    monkeypatch.setattr(extras.settings, "MAX_DAILY_LOSS_KRW", 50_000)

    holdings = [{"symbol": "005930", "market": "KR"}]
    prices_by_market = {"KR": {"000660": {"vi_triggered": True}, "005930": {}}}
    result = await extras.compute_safety(holdings, prices_by_market, "SIMULATION")

    assert result["daily_loss"] == 5_000
    assert result["daily_usage"] == pytest.approx(0.1)
    assert result["positions"][0]["ratio"] == 0.3
    assert result["restricted"] == ["000660"]
    assert result["flags"]["kr_stop"] is True


@pytest.mark.asyncio
async def test_compute_ai_summary_counts_today(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)

    async def _fetch_all(table, filters=None, **kwargs) -> list[dict]:
        return [
            {"decision": {"action": "SELL", "symbol": "000660", "confidence": 0.7,
                          "reason": "과매수"}, "created_at": now},
            {"decision": {"action": "BUY", "symbol": "NVDA", "confidence": 0.6,
                          "reason": "수요 강세"}, "created_at": now - timedelta(hours=1)},
            {"decision": {"action": "HOLD", "symbol": "005930", "confidence": 0.5,
                          "reason": "관망"}, "created_at": now - timedelta(days=3)},  # 오늘 아님
        ]

    async def _today_usage() -> dict:
        return {"cost_krw": 1_200, "call_count": 5}

    async def _month_usage() -> dict:
        return {"cost_krw": 18_000, "call_count": 90}

    monkeypatch.setattr(extras.db, "fetch_all", _fetch_all)
    monkeypatch.setattr(extras.db, "get_api_usage_today_summary", _today_usage)
    monkeypatch.setattr(extras.db, "get_api_usage_month_summary", _month_usage)

    result = await extras.compute_ai_summary()

    assert result["today_counts"] == {"BUY": 1, "HOLD": 0, "SELL": 1}
    assert result["latest"]["action"] == "SELL"
    assert result["api_calls_today"] == 5
    assert result["api_cost_month_krw"] == 18_000


@pytest.mark.asyncio
async def test_compute_calendar_per_market(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _open(market: str) -> bool:
        return market == "KR"

    async def _regular(market: str) -> bool:
        return market == "KR"

    monkeypatch.setattr(extras.toss_market, "is_market_open", _open)
    monkeypatch.setattr(extras.toss_market, "is_regular_session", _regular)

    result = await extras.compute_calendar(["KR", "US"])
    assert result["KR"] == {"open": True, "regular": True}
    assert result["US"] == {"open": False, "regular": False}


@pytest.mark.asyncio
async def test_compute_timeline_merges_and_sorts(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)

    async def _today_trades(mode: str, market: str) -> list[dict]:
        if market == "KR":
            return [{"symbol": "005930", "action": "SELL", "quantity": 1,
                     "fill_price": 78_000, "pnl_krw": 4_500, "created_at": now}]
        return [{"symbol": "NVDA", "action": "BUY", "quantity": 3, "fill_price": 158.0,
                 "pnl_krw": None, "created_at": now - timedelta(hours=2)}]

    monkeypatch.setattr(extras.db, "get_today_trades", _today_trades)

    result = await extras.compute_timeline(["KR", "US"], "SIMULATION")
    assert [e["symbol"] for e in result] == ["005930", "NVDA"]  # 최신순


@pytest.mark.asyncio
async def test_gather_report_extras_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _realized(mode: str) -> int:
        return 0

    async def _ratio(symbol: str, mode: str) -> float:
        return 0.2

    async def _flags() -> dict:
        return {"emergency_stop": False, "kr_stop": False, "us_stop": False}

    async def _fetch_all(table, filters=None, **kwargs) -> list[dict]:
        return []

    async def _usage() -> dict:
        return {"cost_krw": 0, "call_count": 0}

    async def _open(market: str) -> bool:
        return True

    async def _trades(mode: str, market: str) -> list[dict]:
        return []

    async def _snaps(limit: int = 30) -> list[dict]:
        return [{"total_value_krw": 500_000}, {"total_value_krw": 520_000}]

    monkeypatch.setattr(extras.db, "get_today_realized_pnl_krw", _realized)
    monkeypatch.setattr(extras.fund_manager, "get_position_ratio", _ratio)
    monkeypatch.setattr(extras.db, "get_control_flags", _flags)
    monkeypatch.setattr(extras.db, "fetch_all", _fetch_all)
    monkeypatch.setattr(extras.db, "get_api_usage_today_summary", _usage)
    monkeypatch.setattr(extras.db, "get_api_usage_month_summary", _usage)
    monkeypatch.setattr(extras.toss_market, "is_market_open", _open)
    monkeypatch.setattr(extras.toss_market, "is_regular_session", _open)
    monkeypatch.setattr(extras.db, "get_today_trades", _trades)
    monkeypatch.setattr(extras.db, "get_recent_simulation_snapshots", _snaps)

    portfolio = {
        "holdings": [{"symbol": "005930", "market": "KR", "quantity": 1,
                      "avgPrice": 74_000.0, "currentPrice": 78_400.0, "pnlPct": 0.06}],
    }
    snapshots = {"KR": {"prices": {"005930": {"bb_upper": 80_000, "bb_lower": 76_000,
                                              "price": 78_400}}, "exchange_rate_krw_usd": 1_384.5}}

    result = await extras.gather_report_extras(
        ["KR"], snapshots, portfolio, "SIMULATION", benchmark_values=[100.0, 103.0]
    )

    assert result["unrealized"]["total_krw"] == 4_400
    assert result["alpha"]["alpha_pp"] == pytest.approx(0.04 - 0.03)
    assert result["bands"][0]["symbol"] == "005930"
    assert result["safety"]["daily_usage"] == 0.0
    assert result["calendar"]["KR"]["open"] is True
