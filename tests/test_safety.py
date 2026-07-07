"""SafetyGate 통과·거부 조건 단위 테스트 (docs/SAFETY.md 11개 조건, KR·US 시나리오).

check()의 오케스트레이션 로직만 검증한다. DB·토스 API·FundManager 등 실제 협력 객체는
private 헬퍼(`_get_daily_loss` 등)를 monkeypatch로 대체해 격리한다.
"""

import pytest

from core.config import settings
from core.models import Order, RunMode
from core.safety.gate import SafetyGate


@pytest.fixture
def gate() -> SafetyGate:
    return SafetyGate()


def _make_order(
    *,
    market: str = "KR",
    symbol: str = "005930",
    order_type: str = "LIMIT",
    amount_krw: int = 50_000,
    client_order_id: str = "BIN-KR-TEST",
) -> Order:
    return Order(
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        action="BUY",
        quantity=1,
        order_type=order_type,  # type: ignore[arg-type]
        price=None,
        amount_krw=amount_krw,
        client_order_id=client_order_id,
    )


@pytest.fixture(autouse=True)
def _stub_all_pass(gate: SafetyGate, monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 조건을 통과시키는 기본 상태. 각 테스트가 특정 조건만 실패하도록 덮어쓴다."""

    async def _daily_loss(mode: RunMode) -> int:
        return 0

    async def _position_ratio(symbol: str, mode: RunMode) -> float:
        return 0.1

    async def _cash_buffer(mode: RunMode) -> float:
        return settings.INITIAL_SEED_KRW * 0.15

    async def _stock_warnings(symbol: str) -> dict:
        return {"has_restriction": False}

    async def _market_open(market: str) -> bool:
        return True

    async def _regular_session(market: str) -> bool:
        return True

    async def _order_id_exists(client_order_id: str) -> bool:
        return False

    async def _high_risk_event() -> bool:
        return False

    monkeypatch.setattr(gate, "_get_daily_loss", _daily_loss)
    monkeypatch.setattr(gate, "_get_position_ratio", _position_ratio)
    monkeypatch.setattr(gate, "_get_cash_buffer", _cash_buffer)
    monkeypatch.setattr(gate, "_get_stock_warnings", _stock_warnings)
    monkeypatch.setattr(gate, "_is_market_open", _market_open)
    monkeypatch.setattr(gate, "_is_regular_session", _regular_session)
    monkeypatch.setattr(gate, "_order_id_exists", _order_id_exists)
    monkeypatch.setattr(gate, "_has_high_risk_event_today", _high_risk_event)

    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    monkeypatch.setattr(settings, "KR_STOP", False)
    monkeypatch.setattr(settings, "US_STOP", False)


@pytest.mark.asyncio
async def test_all_conditions_pass_approves_order(gate: SafetyGate) -> None:
    result = await gate.check(
        _make_order(market="KR"), RunMode(mode="SIMULATION", market="KR")
    )
    assert result.approved is True


@pytest.mark.asyncio
@pytest.mark.parametrize("market", ["KR", "US"])
async def test_emergency_stop_rejects_all_orders(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch, market: str
) -> None:
    monkeypatch.setattr(settings, "EMERGENCY_STOP", True)

    result = await gate.check(
        _make_order(market=market), RunMode(mode="LIVE", market=market)
    )

    assert result.approved is False
    assert result.reason == "EMERGENCY_STOP 활성화"


@pytest.mark.asyncio
async def test_kr_stop_rejects_kr_orders_only(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "KR_STOP", True)

    kr_result = await gate.check(
        _make_order(market="KR"), RunMode(mode="LIVE", market="KR")
    )
    us_result = await gate.check(
        _make_order(market="US", symbol="AAPL"), RunMode(mode="LIVE", market="US")
    )

    assert kr_result.approved is False
    assert kr_result.reason == "KR_STOP 활성화"
    assert us_result.approved is True


@pytest.mark.asyncio
async def test_us_stop_rejects_us_orders_only(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "US_STOP", True)

    us_result = await gate.check(
        _make_order(market="US", symbol="AAPL"), RunMode(mode="LIVE", market="US")
    )
    kr_result = await gate.check(
        _make_order(market="KR"), RunMode(mode="LIVE", market="KR")
    )

    assert us_result.approved is False
    assert us_result.reason == "US_STOP 활성화"
    assert kr_result.approved is True


@pytest.mark.asyncio
async def test_daily_loss_limit_exceeded_rejects_order(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _daily_loss(mode: RunMode) -> int:
        return settings.MAX_DAILY_LOSS_KRW

    monkeypatch.setattr(gate, "_get_daily_loss", _daily_loss)

    result = await gate.check(_make_order(), RunMode(mode="SIMULATION", market="KR"))

    assert result.approved is False
    assert "일일 손실 한도 초과" in result.reason


@pytest.mark.asyncio
async def test_max_position_ratio_rejects_oversized_order(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _position_ratio(symbol: str, mode: RunMode) -> float:
        return settings.MAX_POSITION_RATIO + 0.01

    monkeypatch.setattr(gate, "_get_position_ratio", _position_ratio)

    result = await gate.check(_make_order(), RunMode(mode="LIVE", market="KR"))

    assert result.approved is False
    assert "종목 비중 상한 초과" in result.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity,amount_krw", [(0, 50_000), (-1, 50_000), (1, 0), (1, -50_000)])
async def test_non_positive_quantity_or_amount_rejects_order(
    gate: SafetyGate, quantity: int, amount_krw: int
) -> None:
    """음수/0 수량·금액은 5번 조건(amount_krw > MAX_SINGLE_ORDER_KRW)을 무력화하므로
    다른 어떤 조건보다 먼저 거부해야 한다 (예: 수동 주문 API의 입력 검증 누락에도 대비)."""
    order = _make_order(amount_krw=amount_krw)
    order.quantity = quantity

    result = await gate.check(order, RunMode(mode="LIVE", market="KR"))

    assert result.approved is False
    assert "0보다 커야" in result.reason


@pytest.mark.asyncio
async def test_max_single_order_amount_rejects_order(gate: SafetyGate) -> None:
    order = _make_order(amount_krw=settings.MAX_SINGLE_ORDER_KRW + 1)

    result = await gate.check(order, RunMode(mode="LIVE", market="KR"))

    assert result.approved is False
    assert "주문 금액 초과" in result.reason


@pytest.mark.asyncio
async def test_cash_buffer_below_minimum_rejects_order(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _cash_buffer(mode: RunMode) -> float:
        return settings.INITIAL_SEED_KRW * 0.04

    monkeypatch.setattr(gate, "_get_cash_buffer", _cash_buffer)

    result = await gate.check(_make_order(), RunMode(mode="LIVE", market="KR"))

    assert result.approved is False
    assert "현금 버퍼 부족" in result.reason


@pytest.mark.asyncio
async def test_kr_stock_restriction_rejects_order(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _stock_warnings(symbol: str) -> dict:
        return {"has_restriction": True, "reason": "VI 발동"}

    monkeypatch.setattr(gate, "_get_stock_warnings", _stock_warnings)

    result = await gate.check(
        _make_order(market="KR"), RunMode(mode="LIVE", market="KR")
    )

    assert result.approved is False
    assert "거래 제한 종목" in result.reason
    assert "VI 발동" in result.reason


@pytest.mark.asyncio
async def test_us_orders_skip_kr_stock_restriction_check(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _stock_warnings(symbol: str) -> dict:
        raise AssertionError("US 주문은 KR 전용 경고 조회를 호출하지 않아야 한다")

    monkeypatch.setattr(gate, "_get_stock_warnings", _stock_warnings)

    result = await gate.check(
        _make_order(market="US", symbol="AAPL"), RunMode(mode="LIVE", market="US")
    )

    assert result.approved is True


@pytest.mark.asyncio
@pytest.mark.parametrize("market", ["KR", "US"])
async def test_market_closed_rejects_order(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch, market: str
) -> None:
    async def _market_open(m: str) -> bool:
        return False

    monkeypatch.setattr(gate, "_is_market_open", _market_open)

    result = await gate.check(
        _make_order(market=market, symbol="AAPL" if market == "US" else "005930"),
        RunMode(mode="LIVE", market=market),
    )

    assert result.approved is False
    assert result.reason == "장 마감 시간"


@pytest.mark.asyncio
async def test_us_amount_order_outside_regular_session_rejected(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _regular_session(market: str) -> bool:
        return False

    monkeypatch.setattr(gate, "_is_regular_session", _regular_session)

    order = _make_order(market="US", symbol="AAPL", order_type="AMOUNT")
    result = await gate.check(order, RunMode(mode="LIVE", market="US"))

    assert result.approved is False
    assert "금액 주문은 정규장만 허용" in result.reason


@pytest.mark.asyncio
async def test_us_limit_order_allowed_outside_regular_session(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _regular_session(market: str) -> bool:
        return False

    monkeypatch.setattr(gate, "_is_regular_session", _regular_session)

    order = _make_order(market="US", symbol="AAPL", order_type="LIMIT")
    result = await gate.check(order, RunMode(mode="LIVE", market="US"))

    assert result.approved is True


@pytest.mark.asyncio
async def test_duplicate_client_order_id_rejects_order(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _order_id_exists(client_order_id: str) -> bool:
        return True

    monkeypatch.setattr(gate, "_order_id_exists", _order_id_exists)

    result = await gate.check(_make_order(), RunMode(mode="LIVE", market="KR"))

    assert result.approved is False
    assert result.reason == "중복 주문 ID"


@pytest.mark.asyncio
async def test_high_risk_event_day_shrinks_order_limit(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _high_risk_event() -> bool:
        return True

    monkeypatch.setattr(gate, "_has_high_risk_event_today", _high_risk_event)

    reduced_limit = settings.MAX_SINGLE_ORDER_KRW * 0.5
    order = _make_order(amount_krw=int(reduced_limit) + 1)

    result = await gate.check(order, RunMode(mode="LIVE", market="KR"))

    assert result.approved is False
    assert "고위험 이벤트 당일 한도 초과" in result.reason


@pytest.mark.asyncio
async def test_high_risk_event_day_allows_order_within_reduced_limit(
    gate: SafetyGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _high_risk_event() -> bool:
        return True

    monkeypatch.setattr(gate, "_has_high_risk_event_today", _high_risk_event)

    reduced_limit = int(settings.MAX_SINGLE_ORDER_KRW * 0.5)
    order = _make_order(amount_krw=reduced_limit)

    result = await gate.check(order, RunMode(mode="LIVE", market="KR"))

    assert result.approved is True
