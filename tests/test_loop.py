"""KR·US 트레이딩 루프 오케스트레이션 단위 테스트 (docs/BIN.md STEP 1~8).

시장 데이터 수집·AI 판단·주문 실행 등 실제 협력 객체는 monkeypatch로 격리하고,
run_loop()이 올바른 순서로 이들을 호출/스킵하는지만 검증한다.
"""

import pytest

import core.toss.market as toss_market_module
from core.config import settings
from core.models import Decision, OrderResult, StateSnapshot
from core.trading import loop


def _make_state() -> StateSnapshot:
    return StateSnapshot(
        bot="Bin",
        market="KR",
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices={"005930": {"price": 75_000, "rsi_14": 50.0}},
        portfolio={"holdings": []},
    )


@pytest.fixture(autouse=True)
def _reset_stop_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    monkeypatch.setattr(settings, "KR_STOP", False)
    monkeypatch.setattr(settings, "US_STOP", False)


@pytest.mark.asyncio
async def test_build_state_snapshot_wires_popular_and_fear_greed_from_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/BIN.md StateSnapshot의 toss_popular_top10/fear_greed_index가 collector 결과로
    실제로 채워져야 한다 (예전에는 항상 빈 값이었다)."""

    async def _get_watchlist(market):  # noqa: ANN001
        return [{"symbol": "005930", "market": "KR", "priority": 0}]

    async def _collect_market_snapshot(market, symbols):  # noqa: ANN001
        return {
            "prices": {"005930": {"price": 75_000}},
            "holdings": [],
            "buying_power": 100_000,
            "exchange_rate_krw_usd": 1382.5,
            "toss_popular_top10": ["005930", "000660"],
            "fear_greed_index": 62,
        }

    async def _get_events_today(market):  # noqa: ANN001
        return []

    async def _get_portfolio_status(mode):  # noqa: ANN001
        return {"totalValueKrw": 500_000, "cashBufferKrw": 75_000, "todayPnlKrw": 0}

    async def _get_operating_funds_krw(mode):  # noqa: ANN001
        return 425_000.0

    async def _estimated_api_cost_krw():
        return 0.0

    monkeypatch.setattr(loop, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(loop, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(loop.calendar, "get_events_today", _get_events_today)
    monkeypatch.setattr(loop.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(loop.fund_manager, "get_operating_funds_krw", _get_operating_funds_krw)
    monkeypatch.setattr(loop.fund_manager, "estimated_api_cost_krw", _estimated_api_cost_krw)

    state = await loop._build_state_snapshot("KR")

    assert state.toss_popular_top10 == ["005930", "000660"]
    assert state.fear_greed_index == 62


@pytest.mark.asyncio
async def test_publish_status_update_records_live_snapshot_when_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """core/report/generator.py의 LIVE 자산 추이 차트가 동작하려면 live_portfolio_snapshots가
    LIVE 모드에서도 적재되어야 한다 (예전에는 simulation_portfolio_snapshots만 있었다)."""
    monkeypatch.setattr(settings, "SIMULATION", False)
    monkeypatch.setattr(settings, "DRY_RUN", False)  # run_mode == "LIVE"

    async def _get_portfolio_status(mode):  # noqa: ANN001
        return {"totalValueKrw": 600_000, "cashKrw": 50_000}

    inserted: list[tuple[str, dict]] = []

    async def _insert(table, values):  # noqa: ANN001
        inserted.append((table, values))
        return values

    async def _publish_event(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        pass

    monkeypatch.setattr(loop.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(loop.db, "insert", _insert)
    monkeypatch.setattr(loop, "publish_event", _publish_event)

    await loop.publish_status_update()

    tables = [table for table, _ in inserted]
    assert "simulation_portfolio_snapshots" in tables
    assert "live_portfolio_snapshots" in tables
    live_row = next(values for table, values in inserted if table == "live_portfolio_snapshots")
    assert live_row["total_value_krw"] == 600_000
    assert live_row["cash_krw"] == 50_000


@pytest.mark.asyncio
async def test_publish_status_update_skips_live_snapshot_in_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SIMULATION", True)
    monkeypatch.setattr(settings, "DRY_RUN", False)

    async def _get_portfolio_status(mode):  # noqa: ANN001
        return {"totalValueKrw": 500_000, "cashKrw": 75_000}

    inserted: list[tuple[str, dict]] = []

    async def _insert(table, values):  # noqa: ANN001
        inserted.append((table, values))
        return values

    async def _publish_event(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        pass

    monkeypatch.setattr(loop.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(loop.db, "insert", _insert)
    monkeypatch.setattr(loop, "publish_event", _publish_event)

    await loop.publish_status_update()

    tables = [table for table, _ in inserted]
    assert tables == ["simulation_portfolio_snapshots"]


@pytest.mark.asyncio
async def test_run_loop_skips_when_emergency_stop_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMERGENCY_STOP", True)

    async def _is_open_should_not_be_called(market):  # noqa: ANN001
        raise AssertionError("긴급 정지 상태에서는 장 운영 여부를 조회하지 않아야 한다")

    monkeypatch.setattr(toss_market_module, "is_market_open", _is_open_should_not_be_called)

    await loop.run_loop("KR")


@pytest.mark.asyncio
@pytest.mark.parametrize("market,flag", [("KR", "KR_STOP"), ("US", "US_STOP")])
async def test_run_loop_skips_when_market_specific_stop_active(
    monkeypatch: pytest.MonkeyPatch, market: str, flag: str
) -> None:
    monkeypatch.setattr(settings, flag, True)

    async def _is_open_should_not_be_called(m):  # noqa: ANN001
        raise AssertionError("시장별 정지 상태에서는 장 운영 여부를 조회하지 않아야 한다")

    monkeypatch.setattr(toss_market_module, "is_market_open", _is_open_should_not_be_called)

    await loop.run_loop(market)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_loop_skips_when_market_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _is_closed(market):  # noqa: ANN001
        return False

    async def _build_state_should_not_be_called(market):  # noqa: ANN001
        raise AssertionError("장 마감이면 StateSnapshot을 구성하지 않아야 한다")

    monkeypatch.setattr(toss_market_module, "is_market_open", _is_closed)
    monkeypatch.setattr(loop, "_build_state_snapshot", _build_state_should_not_be_called)

    await loop.run_loop("KR")


@pytest.mark.asyncio
async def test_run_loop_executes_non_hold_decision_and_publishes_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_decisions: list[Decision] = []
    executed: list[Decision] = []
    status_published = {"called": False}

    async def _is_open(market):  # noqa: ANN001
        return True

    async def _build_state(market):  # noqa: ANN001
        return _make_state()

    decision = Decision(
        decision_id="d1",
        action="BUY",
        symbol="005930",
        quantity=1,
        order_type="MARKET",
        price=None,
        confidence=0.8,
        reason="RSI 반등",
        risk_level="LOW",
    )

    async def _get_decision(state):  # noqa: ANN001
        return decision

    async def _record_decision(state, decision_arg):  # noqa: ANN001
        recorded_decisions.append(decision_arg)

    async def _execute(decision_arg, mode, *, strategy_version=None, prompt_version=None):  # noqa: ANN001
        executed.append(decision_arg)
        return OrderResult(filled=True, order_id="SIM-1", fill_price=75_000)

    async def _publish_status_update():
        status_published["called"] = True

    monkeypatch.setattr(toss_market_module, "is_market_open", _is_open)
    monkeypatch.setattr(loop, "_build_state_snapshot", _build_state)
    monkeypatch.setattr(loop, "get_decision", _get_decision)
    monkeypatch.setattr(loop, "_record_decision", _record_decision)
    monkeypatch.setattr(loop, "execute", _execute)
    monkeypatch.setattr(loop, "publish_status_update", _publish_status_update)

    await loop.run_loop("KR")

    assert recorded_decisions == [decision]
    assert executed == [decision]
    assert status_published["called"] is True


@pytest.mark.asyncio
async def test_run_loop_skips_execution_for_hold_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _is_open(market):  # noqa: ANN001
        return True

    async def _build_state(market):  # noqa: ANN001
        return _make_state()

    hold_decision = Decision(
        decision_id="d2",
        action="HOLD",
        symbol="005930",
        quantity=0,
        order_type="MARKET",
        price=None,
        confidence=0.3,
        reason="관망",
        risk_level="LOW",
    )

    async def _get_decision(state):  # noqa: ANN001
        return hold_decision

    async def _record_decision(state, decision_arg):  # noqa: ANN001
        pass

    async def _execute_should_not_be_called(decision_arg, mode):  # noqa: ANN001
        raise AssertionError("HOLD 결정은 executor.execute를 호출하지 않아야 한다")

    async def _publish_status_update():
        pass

    monkeypatch.setattr(toss_market_module, "is_market_open", _is_open)
    monkeypatch.setattr(loop, "_build_state_snapshot", _build_state)
    monkeypatch.setattr(loop, "get_decision", _get_decision)
    monkeypatch.setattr(loop, "_record_decision", _record_decision)
    monkeypatch.setattr(loop, "execute", _execute_should_not_be_called)
    monkeypatch.setattr(loop, "publish_status_update", _publish_status_update)

    await loop.run_loop("KR")
