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

    async def _get_last_rebalance(mode=None):  # noqa: ANN001
        return {"reinvested_krw": 186_000, "created_at": datetime.now(UTC)}

    async def _fetch_all(table, filters=None, *, order_by=None, descending=False, limit=None):  # noqa: ANN001
        return []

    async def _get_latest_deployed_strategy_version(market=None):  # noqa: ANN001
        return {"strategy_version": "v1.4", "prompt_version": "system_kr_v3.2"}

    async def _get_pending_strategy_candidates(market=None):  # noqa: ANN001
        return []

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

    async def _get_recent_live_snapshots(limit=30):  # noqa: ANN001
        return []

    async def _get_recent_simulation_snapshots(limit=30):  # noqa: ANN001
        return []

    monkeypatch.setattr(toss_market, "get_exchange_rate", _get_exchange_rate)
    monkeypatch.setattr(toss_market, "is_market_open", _is_market_open)
    monkeypatch.setattr(fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(fund_manager, "get_last_rebalance", _get_last_rebalance)
    monkeypatch.setattr(ms.db, "fetch_all", _fetch_all)
    monkeypatch.setattr(ms.db, "get_latest_deployed_strategy_version", _get_latest_deployed_strategy_version)
    monkeypatch.setattr(ms.db, "get_pending_strategy_candidates", _get_pending_strategy_candidates)
    monkeypatch.setattr(ms.db, "get_operation_days", _get_operation_days)
    monkeypatch.setattr(ms.db, "get_api_usage_today_summary", _get_api_usage_today_summary)
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


@pytest.mark.asyncio
async def test_total_assets_breakdown_splits_kr_us_and_converts_usd(fake_redis) -> None:  # noqa: ANN001
    snapshot = await ms.build_monitor_snapshot()
    breakdown = snapshot["totalAssets"]["breakdown"]

    assert breakdown["cashKrw"] == 8_120_000
    assert breakdown["krInvestedKrw"] == 30 * 73_200
    # US 보유는 환율(1391.2)을 곱해 원화로 환산돼야 한다.
    assert breakdown["usInvestedKrw"] == pytest.approx(6 * 132.8 * 1391.2, rel=1e-6)
    assert snapshot["totalAssets"]["operatingDays"] == 58
    assert snapshot["totalAssets"]["liveDays"] == 44
    assert snapshot["totalAssets"]["apiModel"] == "Sonnet"


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


def test_next_rebalance_days_counts_to_next_monday() -> None:
    monday_morning = datetime(2026, 7, 6, 7, 0, tzinfo=UTC)  # 월요일 08시 이전
    assert ms._next_rebalance_days(monday_morning) == 0

    monday_afternoon = datetime(2026, 7, 6, 9, 0, tzinfo=UTC)  # 월요일 08시 이후 — 이미 실행됨
    assert ms._next_rebalance_days(monday_afternoon) == 7

    wednesday = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    assert ms._next_rebalance_days(wednesday) == 5


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


@pytest.mark.asyncio
async def test_build_chart_derives_daily_deltas_from_snapshots(monkeypatch: pytest.MonkeyPatch, fake_redis) -> None:  # noqa: ANN001
    base = datetime(2026, 7, 1, tzinfo=UTC)
    snapshots = [
        {"total_value_krw": 50_000_000, "cash_krw": 0, "snapshot_at": base},
        {"total_value_krw": 50_500_000, "cash_krw": 0, "snapshot_at": base + timedelta(days=1)},
        {"total_value_krw": 50_200_000, "cash_krw": 0, "snapshot_at": base + timedelta(days=2)},
    ]

    async def _get_recent_simulation_snapshots(limit=30):  # noqa: ANN001
        return snapshots

    monkeypatch.setattr(ms.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots)

    chart = await ms._build_chart("SIMULATION")

    assert chart["bars"] == [500_000, -300_000]
    assert chart["upDays"] == 1
    assert chart["downDays"] == 1
    assert chart["netKrw"] == 200_000
