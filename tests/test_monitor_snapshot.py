"""core/api/monitor_snapshot.py 단위 테스트 — monitor/(Next.js) 대시보드 집계 로직.

DB·토스 API·FundManager는 monkeypatch로 격리한다 (tests/test_routes.py와 동일 패턴).
"""

import json as json_lib
from datetime import UTC, datetime, timedelta

import pytest

from core.api import monitor_snapshot as ms
from core.fund.manager import fund_manager
from core.monitoring.health import HEALTH_REDIS_KEY
from core.toss import market as toss_market


def _portfolio(**overrides) -> dict:
    base = {
        "totalValueKrw": 52_384_050,
        "todayPnlKrw": 842_150,
        "todayPnlPct": 0.0163,
        "cumulativePnlKrw": 2_384_050,
        "cumulativePnlPct": 0.0477,
        "cashBufferKrw": 7_857_608,
        "cashKrw": 8_120_000,
        "holdings": [
            {
                "symbol": "005930",
                "market": "KR",
                "quantity": 30,
                "avgPrice": 70_000.0,
                "currentPrice": 73_200.0,
                "pnlPct": 0.0457,
            },
            {
                "symbol": "NVDA",
                "market": "US",
                "quantity": 6,
                "avgPrice": 120.0,
                "currentPrice": 132.8,
                "pnlPct": 0.1067,
            },
        ],
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_exchange_rate() -> float:
        return 1391.2

    async def _is_market_open(market: str) -> bool:
        return market == "KR"

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return _portfolio()

    async def _fetch_all(table, filters=None, *, order_by=None, descending=False, limit=None):  # noqa: ANN001
        return []

    async def _get_latest_deployed_strategy_version(market=None):  # noqa: ANN001
        return {"strategy_version": "v1.4", "prompt_version": "system_kr_v3.2"}

    async def _get_operation_days() -> dict:
        return {"total_days": 58, "live_days": 44}

    async def _get_api_usage_today_summary() -> dict:
        return {
            "cost_krw": 6706,
            "cost_usd": 4.82,
            "call_count": 47,
            "input_tokens": 128_400,
            "output_tokens": 22_100,
            "model": "claude-sonnet-4-6",
        }

    async def _get_api_usage_month_summary() -> dict:
        return {
            "cost_krw": 201_180,
            "cost_usd": 144.60,
            "call_count": 1410,
            "input_tokens": 3_012_000,
            "output_tokens": 512_000,
        }

    async def _get_recent_live_snapshots(limit=30):  # noqa: ANN001
        return []

    async def _get_recent_simulation_snapshots(limit=30):  # noqa: ANN001
        return []

    monkeypatch.setattr(toss_market, "get_exchange_rate", _get_exchange_rate)
    monkeypatch.setattr(toss_market, "is_market_open", _is_market_open)
    monkeypatch.setattr(fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(ms.db, "fetch_all", _fetch_all)
    monkeypatch.setattr(ms.db, "get_latest_deployed_strategy_version", _get_latest_deployed_strategy_version)
    monkeypatch.setattr(ms.db, "get_operation_days", _get_operation_days)
    monkeypatch.setattr(ms.db, "get_api_usage_today_summary", _get_api_usage_today_summary)
    monkeypatch.setattr(ms.db, "get_api_usage_month_summary", _get_api_usage_month_summary)
    monkeypatch.setattr(ms.db, "get_recent_live_snapshots", _get_recent_live_snapshots)
    monkeypatch.setattr(ms.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots)


@pytest.mark.asyncio
async def test_build_monitor_snapshot_smoke(fake_redis) -> None:  # noqa: ANN001
    """모든 협력 객체가 비어 있어도 예외 없이 전체 스냅샷 형태를 만든다."""
    snapshot = await ms.build_monitor_snapshot()

    assert set(snapshot.keys()) == {
        "generatedAt",
        "header",
        "subStrip",
        "totalAssets",
        "chart",
        "systemHealth",
        "positions",
        "aiDecisions",
        "aiDecisionsCountToday",
        "news",
        "events",
    }
    assert snapshot["header"]["usdKrw"] == 1391.2
    assert snapshot["header"]["krMarketStatus"] == "장중"
    assert snapshot["header"]["usMarketStatus"] == "장마감"
    assert snapshot["header"]["strategyVersion"] == "v1.4"

    # 관심 종목·스냅샷 이력이 없으면 성과 회전 카드는 "데이터 수집 중" 플레이스홀더로 대체된다.
    placeholder = {"label": "성과", "value": "데이터 수집 중", "tone": "neutral"}
    assert snapshot["subStrip"]["perfStats"] == [placeholder]
    # 집중도는 보유 종목만 있으면 계산되므로(과거 이력 불필요) 리스크 카드는 항상 채워진다.
    assert snapshot["subStrip"]["riskStats"][0]["label"] == "집중도"
    assert len(snapshot["chart"]["periods"]) == 3
    assert [p["label"] for p in snapshot["chart"]["periods"]] == ["전체", "최근 15일", "일일"]


@pytest.mark.asyncio
async def test_total_assets_breakdown_splits_kr_us_and_converts_usd(fake_redis) -> None:  # noqa: ANN001
    snapshot = await ms.build_monitor_snapshot()
    total_assets = snapshot["totalAssets"]
    breakdown = total_assets["breakdown"]

    assert breakdown["cashKrw"] == 8_120_000
    assert breakdown["krInvestedKrw"] == 30 * 73_200
    # US 보유는 환율(1391.2)을 곱해 원화로 환산돼야 한다.
    assert breakdown["usInvestedKrw"] == pytest.approx(6 * 132.8 * 1391.2, rel=1e-6)
    assert total_assets["operatingDays"] == 58
    assert total_assets["liveDays"] == 44
    assert total_assets["apiModel"] == "Sonnet"
    assert total_assets["seedKrw"] == ms.settings.INITIAL_SEED_KRW
    assert total_assets["apiCallsMonthly"] == 1410
    assert total_assets["apiCostMonthlyUsd"] == pytest.approx(144.60)
    assert total_assets["apiCostMonthlyKrw"] == 201_180
    assert total_assets["monthlyTokensInK"] == pytest.approx(3012.0)
    assert total_assets["monthlyTokensOutK"] == pytest.approx(512.0)
    assert "weeklyRebalanceDaysUntil" not in total_assets
    assert "lastReinvestmentKrw" not in total_assets


@pytest.mark.asyncio
async def test_positions_sorted_by_return_desc(fake_redis) -> None:  # noqa: ANN001
    snapshot = await ms.build_monitor_snapshot()
    positions = snapshot["positions"]

    assert [p["symbol"] for p in positions] == ["NVDA", "005930"]
    assert positions[0]["returnPct"] == pytest.approx(10.7, rel=1e-3)


def test_fear_greed_label_buckets() -> None:
    assert ms._fear_greed_label(None) == "데이터 없음"
    assert ms._fear_greed_label(10) == "극도의 공포"
    assert ms._fear_greed_label(40) == "공포"
    assert ms._fear_greed_label(50) == "중립"
    assert ms._fear_greed_label(70) == "탐욕"
    assert ms._fear_greed_label(90) == "극도의 탐욕"


def test_short_model_name() -> None:
    assert ms._short_model_name("claude-sonnet-4-6") == "Sonnet"
    assert ms._short_model_name("claude-opus-4-8") == "Opus"
    assert ms._short_model_name(None) == ms.settings.CLAUDE_MODEL


def test_format_log_time_relative_labels() -> None:
    now = datetime.now(UTC)
    assert ":" in ms._format_log_time(now)
    assert ms._format_log_time(now - timedelta(days=1)).startswith("어제 ")
    assert ms._format_log_time(now - timedelta(days=2)).startswith("그제 ")


@pytest.mark.asyncio
async def test_build_system_health_uses_cached_heartbeat(fake_redis) -> None:  # noqa: ANN001
    collected_at = (datetime.now(UTC) - timedelta(seconds=42)).isoformat()
    await fake_redis.set(
        HEALTH_REDIS_KEY,
        json_lib.dumps(
            {
                "cpu_pct": 10.0,
                "memory_pct": 20.0,
                "disk_pct": 30.0,
                "temp_c": 40.0,
                "toss_api_reachable": True,
                "collected_at": collected_at,
            }
        ),
    )

    snapshot = await ms.build_monitor_snapshot()
    health = snapshot["systemHealth"]

    assert health["lastHeartbeatSecondsAgo"] >= 42
    assert any("하트비트" in log["message"] for log in health["logs"])
    assert health["safetyGate"]["passRateLabel"] == "11/11 통과"
    assert {svc["name"] for svc in health["services"]} >= {"Toss API", "매매 판단 모델 API"}


# ---------- 손익 차트: 다중 기간 + 벤치마크 ----------


@pytest.mark.asyncio
async def test_build_chart_derives_daily_deltas_from_snapshots() -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    snapshots = [
        {"total_value_krw": 50_000_000, "cash_krw": 0, "snapshot_at": base},
        {"total_value_krw": 50_500_000, "cash_krw": 0, "snapshot_at": base + timedelta(days=1)},
        {"total_value_krw": 50_200_000, "cash_krw": 0, "snapshot_at": base + timedelta(days=2)},
    ]
    daily_last = ms._daily_last_values(snapshots)
    days_sorted = sorted(daily_last.keys())

    chart = await ms._build_chart(_portfolio(), snapshots, daily_last, days_sorted, None, None)
    full = chart["periods"][0]

    assert full["bars"] == [500_000, -300_000]
    assert chart["upDays"] == 1
    assert chart["downDays"] == 1
    assert chart["netKrw"] == 200_000
    # 관심 종목 프록시 수익률이 없으면 벤치마크 라인은 그리지 않는다(지어내지 않는다).
    assert full["benchmarkBars"] == []


@pytest.mark.asyncio
async def test_build_chart_blends_benchmark_by_market_weight() -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    snapshots = [
        {"total_value_krw": 50_000_000, "cash_krw": 0, "snapshot_at": base},
        {"total_value_krw": 50_500_000, "cash_krw": 0, "snapshot_at": base + timedelta(days=1)},
    ]
    daily_last = ms._daily_last_values(snapshots)
    days_sorted = sorted(daily_last.keys())
    # 포트폴리오는 전액 KR 보유 → 벤치마크는 KR 프록시 수익률만 반영해야 한다.
    portfolio = _portfolio(holdings=[_portfolio()["holdings"][0]])

    chart = await ms._build_chart(portfolio, snapshots, daily_last, days_sorted, [0.02], [0.5])
    full = chart["periods"][0]

    assert full["benchmarkBars"] == [round(0.02 * portfolio["totalValueKrw"])]


@pytest.mark.asyncio
async def test_build_chart_hourly_period_uses_todays_intraday_snapshots() -> None:
    # 시(hour) 경계에 맞춰 구성 — 임의의 분(minute) 오프셋을 쓰면 테스트를 실행하는 실제
    # 시각에 따라 두 스냅샷이 우연히 같은/다른 시간 버킷에 떨어져 결과가 들쭉날쭉해진다.
    # `current_hour`는 항상 "지금"보다 이르거나 같아 미래 스냅샷이 되지 않는다.
    current_hour = datetime.now(ms._KST).replace(minute=0, second=0, microsecond=0)
    two_hours_ago = current_hour - timedelta(hours=2)
    snapshots = [
        {"total_value_krw": 50_000_000, "cash_krw": 0, "snapshot_at": two_hours_ago},
        {"total_value_krw": 50_100_000, "cash_krw": 0, "snapshot_at": two_hours_ago + timedelta(minutes=15)},
        {"total_value_krw": 50_150_000, "cash_krw": 0, "snapshot_at": current_hour},
    ]
    daily_last = ms._daily_last_values(snapshots)
    days_sorted = sorted(daily_last.keys())

    chart = await ms._build_chart(_portfolio(), snapshots, daily_last, days_sorted, None, None)
    hourly = chart["periods"][2]

    assert hourly["label"] == "일일"
    # 시간대별 버킷은 그 시간의 "마지막" 스냅샷만 남기므로, 첫 시간대의 값은 두 번째
    # 스냅샷(50,100,000)으로 덮어써진다 — 델타는 50,150,000 - 50,100,000.
    assert hourly["bars"] == [50_000]


def test_bars_from_values() -> None:
    assert ms._bars_from_values([100.0, 150.0, 120.0]) == [50, -30]
    assert ms._bars_from_values([100.0]) == []


def test_win_rate_pct() -> None:
    assert ms._win_rate_pct([]) == 0
    assert ms._win_rate_pct([10, -5, 20, -1]) == 50


def test_compound_return() -> None:
    assert ms._compound_return([]) == 0.0
    assert ms._compound_return([0.1, 0.1]) == pytest.approx(0.21)


def test_day_labels_marks_every_third_bar_and_last_as_today() -> None:
    days = [ms.date(2026, 7, d) for d in range(1, 6)]
    labels = ms._day_labels(days)
    assert labels[-1] == "오늘"
    assert labels[0] == "7/1"
    assert labels[1] == ""


def test_hour_labels_marks_last_as_now() -> None:
    hours = [datetime(2026, 7, 1, h, tzinfo=UTC) for h in range(9, 13)]
    labels = ms._hour_labels(hours)
    assert labels[-1] == "지금"


# ---------- 서브 스트립: 성과/리스크 회전 카드 ----------


def test_concentration_stat_flags_hard_cap_breach() -> None:
    holdings = [
        {"symbol": "NVDA", "market": "US", "quantity": 10, "currentPrice": 100.0},
        {"symbol": "AAPL", "market": "US", "quantity": 1, "currentPrice": 10.0},
    ]
    stat = ms._concentration_stat(holdings, exchange_rate=1.0)
    assert stat is not None
    assert stat["tone"] == "bad"
    assert "NVDA" in stat["value"]


def test_concentration_stat_none_when_no_holdings() -> None:
    assert ms._concentration_stat([], exchange_rate=1.0) is None


def test_mdd_stat_matches_max_drawdown_helper() -> None:
    values = [100.0, 120.0, 90.0, 110.0]
    stat = ms._mdd_stat(values)
    assert stat is not None
    expected = ms.indicators.calculate_max_drawdown_pct(values) * 100
    assert f"{expected:.1f}%" in stat["value"]


def test_var_stat_requires_minimum_sample() -> None:
    assert ms._var_stat([1, 2, 3]) is None
    bars = [-100, -80, -50, -10, 0, 10, 20, 30, 40, 50]
    stat = ms._var_stat(bars)
    assert stat is not None
    assert stat["tone"] == "bad"


def test_win_streak_stat_counts_trailing_positive_days() -> None:
    assert ms._win_streak_stat([10, -5, 20, 30])["value"] == "2일 · 진행 중"
    assert ms._win_streak_stat([10, -5])["value"] == "0일 · 없음"


def test_profit_factor_and_win_rate() -> None:
    trades = [{"pnl_krw": 100}, {"pnl_krw": -50}, {"pnl_krw": 200}]
    win_rate, profit_factor = ms._profit_factor_and_win_rate(trades)
    assert win_rate["value"].startswith("67%")
    assert profit_factor["value"].startswith("6.0")


def test_profit_factor_none_when_no_losses() -> None:
    trades = [{"pnl_krw": 100}]
    _, profit_factor = ms._profit_factor_and_win_rate(trades)
    assert profit_factor["value"].startswith("999.0")


def test_fill_rate_stat_combines_trades_and_rejections() -> None:
    trades = [{"pnl_krw": 1}] * 9
    rejections = [{}] * 1
    stat = ms._fill_rate_stat(trades, rejections)
    assert stat["value"] == "90% · 9/10건"


def test_alpha_stat_skips_when_no_holdings_in_market() -> None:
    assert ms._alpha_stat("KOSPI", [], "KR", [0.01]) is None


def test_alpha_stat_computes_percentage_point_gap() -> None:
    holdings = [{"symbol": "005930", "market": "KR", "quantity": 10, "currentPrice": 100.0, "pnlPct": 0.10}]
    # 프록시가 하루 0.1%씩(20일 복리 ~2%) 움직였다면, 포트폴리오 10% 대비 알파는 양수여야 한다.
    stat = ms._alpha_stat("KOSPI", holdings, "KR", [0.001] * ms._ALPHA_WINDOW_DAYS)
    assert stat is not None
    assert stat["tone"] == "positive"
    assert "KOSPI" in stat["value"]
