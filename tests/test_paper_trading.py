"""PaperTradingRunner 단위 테스트 — 신호 생성·기록만 하고 실제 주문은 하지 않는다."""

import pytest

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy
from core.strategy.paper_trading import PaperTradingRunner


class _AlwaysBuyStrategy(BaseStrategy):
    version = "paper-v1"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        return self.make_decision(symbol="005930", action="BUY", quantity=1, price=None, reason="test")


class _NeverSignalsStrategy(BaseStrategy):
    version = "paper-v1"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        return None


def _make_state() -> StateSnapshot:
    return StateSnapshot(
        bot="Bin",
        market="KR",
        mode="SIMULATION",
        strategy_version="paper-v1",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices={"005930": {"price": 75_000}},
        portfolio={"holdings": []},
    )


@pytest.mark.asyncio
async def test_step_records_signal_to_paper_trades(monkeypatch: pytest.MonkeyPatch) -> None:
    inserted: list[tuple[str, dict]] = []

    async def _insert(table: str, values: dict) -> dict:
        inserted.append((table, values))
        return values

    import core.strategy.paper_trading as paper_trading_module

    monkeypatch.setattr(paper_trading_module.db, "insert", _insert)

    runner = PaperTradingRunner(_AlwaysBuyStrategy())
    decision = await runner.step(_make_state())

    assert decision is not None
    assert decision.action == "BUY"
    assert inserted == [
        ("paper_trades", {"symbol": "005930", "strategy_version": "paper-v1", "pnl_krw": None})
    ]


@pytest.mark.asyncio
async def test_step_records_nothing_when_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _insert_should_not_be_called(table: str, values: dict) -> dict:
        raise AssertionError("신호가 없으면 paper_trades에 기록하면 안 된다")

    import core.strategy.paper_trading as paper_trading_module

    monkeypatch.setattr(paper_trading_module.db, "insert", _insert_should_not_be_called)

    runner = PaperTradingRunner(_NeverSignalsStrategy())
    decision = await runner.step(_make_state())

    assert decision is None
