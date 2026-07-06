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

    async def _execute(decision_arg, mode):  # noqa: ANN001
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
