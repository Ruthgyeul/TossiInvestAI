"""LIVE/SIMULATION 주문 실행 분기 단위 테스트 (docs/BIN.md, docs/SAFETY.md).

Safety Gate·DB·토스 API·Redis 발행 등 협력 객체는 모두 monkeypatch로 격리한다.
"""

from pathlib import Path

import pytest

from core.models import Decision, GateResult, RunMode
from core.trading import executor


def _make_decision(*, action: str = "BUY", price: float | None = None) -> Decision:
    return Decision(
        decision_id="decision-1",
        action=action,  # type: ignore[arg-type]
        symbol="005930",
        quantity=2,
        order_type="LIMIT" if price is not None else "MARKET",
        price=price,
        confidence=0.9,
        reason="테스트 사유",
        risk_level="LOW",
    )


@pytest.fixture(autouse=True)
def _isolate_log_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """실행 로그가 실제 저장소의 logs/ 디렉터리를 오염시키지 않도록 격리한다."""
    monkeypatch.setattr(executor, "_TRADING_LOG_DIR", tmp_path / "trading")
    monkeypatch.setattr(executor, "_ERROR_LOG_DIR", tmp_path / "errors")


@pytest.fixture(autouse=True)
def _reset_simulation_portfolio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor, "_simulation_portfolio", None)


@pytest.mark.asyncio
async def test_hold_decision_skips_safety_gate_and_returns_unfilled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _check_should_not_be_called(order, mode):  # noqa: ANN001
        raise AssertionError("HOLD 결정은 Safety Gate를 호출하지 않아야 한다")

    monkeypatch.setattr(executor.safety_gate, "check", _check_should_not_be_called)

    result = await executor.execute(_make_decision(action="HOLD"), RunMode(mode="LIVE", market="KR"))

    assert result.filled is False
    assert result.reason == "HOLD — 주문 없음"


@pytest.mark.asyncio
async def test_rejected_order_records_and_publishes_without_placing_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted: list[tuple[str, dict]] = []
    published: list[tuple[str, dict]] = []

    async def _reject(order, mode):  # noqa: ANN001
        return GateResult.reject("일일 손실 한도 초과")

    async def _insert(table, values):  # noqa: ANN001
        inserted.append((table, values))
        return values

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        published.append((event_type, payload))

    async def _place_should_not_be_called(order):  # noqa: ANN001
        raise AssertionError("거부된 주문은 토스 API로 전송되면 안 된다")

    monkeypatch.setattr(executor.safety_gate, "check", _reject)
    monkeypatch.setattr(executor.db, "insert", _insert)
    monkeypatch.setattr(executor, "publish_event", _publish)
    monkeypatch.setattr(executor.toss_order, "place", _place_should_not_be_called)

    decision = _make_decision(price=74_800)
    result = await executor.execute(decision, RunMode(mode="LIVE", market="KR"))

    assert result.filled is False
    assert result.reason == "일일 손실 한도 초과"
    assert inserted[0] == (
        "safety_rejections",
        {"symbol": "005930", "market": "KR", "reason": "일일 손실 한도 초과", "mode": "LIVE"},
    )
    assert published[0][0] == "safety_rejection"


@pytest.mark.asyncio
async def test_simulation_buy_fills_at_current_price_and_updates_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied_buys: list[tuple] = []
    inserted: list[tuple[str, dict]] = []
    published: list[tuple[str, dict]] = []

    class _FakePortfolio:
        async def apply_buy(self, symbol, qty, fill_price, commission, market):  # noqa: ANN001
            applied_buys.append((symbol, qty, fill_price, commission, market))

    async def _approve(order, mode):  # noqa: ANN001
        return GateResult.approve()

    async def _get_price(symbol):  # noqa: ANN001
        return {"price": 75_000}

    async def _get_commissions(market):  # noqa: ANN001
        return {"rate": 0.001}

    async def _insert(table, values):  # noqa: ANN001
        inserted.append((table, values))
        return values

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        published.append((event_type, payload))

    async def _get_portfolio():
        return _FakePortfolio()

    monkeypatch.setattr(executor.safety_gate, "check", _approve)
    monkeypatch.setattr(executor.toss_market, "get_price", _get_price)
    monkeypatch.setattr(executor.toss_account, "get_commissions", _get_commissions)
    monkeypatch.setattr(executor.db, "insert", _insert)
    monkeypatch.setattr(executor, "publish_event", _publish)
    monkeypatch.setattr(executor, "_get_simulation_portfolio", _get_portfolio)

    decision = _make_decision(action="BUY")  # price=None → 시장가, 현재가로 체결
    result = await executor.execute(decision, RunMode(mode="SIMULATION", market="KR"))

    assert result.filled is True
    assert result.fill_price == 75_000
    assert applied_buys == [("005930", 2, 75_000, 150, "KR")]
    assert inserted[0][0] == "simulation_trades"
    assert inserted[0][1]["pnl_krw"] is None
    assert published[0][0] == "trade_executed"
    assert published[0][1]["fillPrice"] == 75_000


@pytest.mark.asyncio
async def test_dry_run_execution_never_touches_portfolio_or_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/SAFETY.md "DRY_RUN: DB 기록 최소화(영구 보존 데이터 생성 안 함)" — SIMULATION 리허설의
    simulation_positions/simulation_trades를 DRY_RUN 테스트 실행이 오염시키면 안 된다."""
    inserted: list[tuple[str, dict]] = []
    published: list[tuple[str, dict]] = []

    def _portfolio_should_not_be_loaded():
        raise AssertionError("DRY_RUN은 가상 포트폴리오를 로드/갱신하면 안 된다")

    async def _approve(order, mode):  # noqa: ANN001
        return GateResult.approve()

    async def _get_price(symbol):  # noqa: ANN001
        return {"price": 75_000}

    async def _get_commissions(market):  # noqa: ANN001
        return {"rate": 0.001}

    async def _insert(table, values):  # noqa: ANN001
        inserted.append((table, values))
        return values

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        published.append((event_type, payload))

    monkeypatch.setattr(executor.safety_gate, "check", _approve)
    monkeypatch.setattr(executor.toss_market, "get_price", _get_price)
    monkeypatch.setattr(executor.toss_account, "get_commissions", _get_commissions)
    monkeypatch.setattr(executor.db, "insert", _insert)
    monkeypatch.setattr(executor, "publish_event", _publish)
    monkeypatch.setattr(executor, "_get_simulation_portfolio", _portfolio_should_not_be_loaded)

    decision = _make_decision(action="BUY")
    result = await executor.execute(decision, RunMode(mode="DRY_RUN", market="KR"))

    assert result.filled is True
    assert result.order_id is not None and result.order_id.startswith("DRY-")
    assert inserted == []
    assert published[0][0] == "trade_executed"
    assert published[0][1]["pnlKrw"] is None


@pytest.mark.asyncio
async def test_live_execution_places_order_via_toss_and_records_trade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted: list[tuple[str, dict]] = []
    published: list[tuple[str, dict]] = []

    async def _approve(order, mode):  # noqa: ANN001
        return GateResult.approve()

    async def _place(order):  # noqa: ANN001
        return {"orderId": "TOSS-1", "fillPrice": 74_800}

    async def _get_commissions(market):  # noqa: ANN001
        return {"rate": 0.001}

    async def _insert(table, values):  # noqa: ANN001
        inserted.append((table, values))
        return values

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        published.append((event_type, payload))

    monkeypatch.setattr(executor.safety_gate, "check", _approve)
    monkeypatch.setattr(executor.toss_order, "place", _place)
    monkeypatch.setattr(executor.toss_account, "get_commissions", _get_commissions)
    monkeypatch.setattr(executor.db, "insert", _insert)
    monkeypatch.setattr(executor, "publish_event", _publish)

    decision = _make_decision(price=74_800)
    result = await executor.execute(decision, RunMode(mode="LIVE", market="KR"))

    assert result.filled is True
    assert result.order_id == "TOSS-1"
    assert result.fill_price == 74_800
    assert inserted[0][0] == "orders"
    assert inserted[0][1]["symbol"] == "005930"
    assert inserted[0][1]["action"] == "BUY"
    assert inserted[0][1]["quantity"] == 2
    assert inserted[0][1]["price"] == 74_800
    assert inserted[0][1]["status"] == "FILLED"
    assert inserted[1] == (
        "trades",
        {
            "symbol": "005930",
            "market": "KR",
            "action": "BUY",
            "quantity": 2,
            "fill_price": 74_800.0,
            "commission_krw": 150,
            "decision_id": "decision-1",
            "order_id": "TOSS-1",
        },
    )
    assert published[0][0] == "trade_executed"


@pytest.mark.asyncio
async def test_trade_log_includes_logging_md_required_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """docs/LOGGING.md "거래 로그 형식" 필드(종목명·주문사유·Decision ID·전략/프롬프트 버전 등)."""

    async def _approve(order, mode):  # noqa: ANN001
        return GateResult.approve()

    async def _place(order):  # noqa: ANN001
        return {"orderId": "TOSS-1", "fillPrice": 74_800}

    async def _get_commissions(market):  # noqa: ANN001
        return {"rate": 0.001}

    async def _insert(table, values):  # noqa: ANN001
        return values

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        pass

    monkeypatch.setattr(executor.safety_gate, "check", _approve)
    monkeypatch.setattr(executor.toss_order, "place", _place)
    monkeypatch.setattr(executor.toss_account, "get_commissions", _get_commissions)
    monkeypatch.setattr(executor.db, "insert", _insert)
    monkeypatch.setattr(executor, "publish_event", _publish)

    decision = _make_decision(price=74_800)
    await executor.execute(
        decision,
        RunMode(mode="LIVE", market="KR"),
        strategy_version="v1.2.0",
        prompt_version="system_kr_v3",
    )

    log_file = next((tmp_path / "trading").glob("*.log"))
    content = log_file.read_text(encoding="utf-8")

    assert "종목명" in content
    assert "주문 사유       테스트 사유" in content
    assert "Claude Decision ID  decision-1" in content
    assert "Toss Order ID       TOSS-1" in content
    assert "전략 버전       v1.2.0" in content
    assert "프롬프트 버전   system_kr_v3" in content
    assert "실현 손익       해당 없음 (신규 매수)" in content
