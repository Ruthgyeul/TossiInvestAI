"""자기개선 파이프라인 핵심 — 개선 후보 제안·백테스트 게이트 단위 테스트 (docs/SELF_IMPROVEMENT.md)."""

import pytest

import core.trading.self_improvement as self_improvement_module
from core.strategy.backtest import BacktestResult
from core.strategy.base import BaseStrategy


class _DummyStrategy(BaseStrategy):
    version = "v1.1.0"

    async def generate_signal(self, state):  # noqa: ANN001
        return None


@pytest.fixture(autouse=True)
def _stub_registered_strategies(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.trading.decision as decision_module

    monkeypatch.setattr(
        decision_module, "get_registered_strategies", lambda market: [_DummyStrategy()]
    )


@pytest.mark.asyncio
async def test_propose_candidate_registers_first_ever_candidate_without_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run(strategy, market, period, initial_capital):  # noqa: ANN001
        return BacktestResult(win_rate=0.6, avg_return=0.05, mdd=-0.02, sharpe_ratio=1.5, profit_factor=1.8)

    async def _get_latest_deployed(market):  # noqa: ANN001
        return None

    inserted: list[dict] = []

    async def _insert(table, values):  # noqa: ANN001
        inserted.append(values)
        return {**values, "id": 1}

    published: list[tuple] = []

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        published.append((event_type, payload))

    monkeypatch.setattr(self_improvement_module.BacktestEngine, "run", staticmethod(_run))
    monkeypatch.setattr(self_improvement_module.db, "get_latest_deployed_strategy_version", _get_latest_deployed)
    monkeypatch.setattr(self_improvement_module.db, "insert", _insert)
    monkeypatch.setattr(self_improvement_module, "publish_event", _publish)

    row = await self_improvement_module.propose_candidate("KR", "RSI 임계값 조정")

    assert row is not None
    assert inserted[0]["approved_by"] is None
    assert inserted[0]["deployed_at"] is None
    assert inserted[0]["change_summary"] == "RSI 임계값 조정"
    assert inserted[0]["based_on"] is None
    assert published[0][0] == "version_candidate_ready"
    assert published[0][1]["backtestResult"]["win_rate"] == 0.6


@pytest.mark.asyncio
async def test_propose_candidate_discards_when_regressed_vs_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run(strategy, market, period, initial_capital):  # noqa: ANN001
        return BacktestResult(win_rate=0.4, avg_return=0.01, mdd=-0.10, sharpe_ratio=0.5, profit_factor=1.1)

    async def _get_latest_deployed(market):  # noqa: ANN001
        return {
            "strategy_version": "v1.0.0",
            "prompt_version": "system_kr_v1",
            "backtest_result": {"win_rate": 0.65, "sharpe_ratio": 1.7, "mdd": -0.03},
        }

    async def _insert_should_not_be_called(table, values):  # noqa: ANN001
        raise AssertionError("열화된 후보는 저장되면 안 된다")

    async def _publish_should_not_be_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("열화된 후보는 이벤트를 발행하면 안 된다")

    monkeypatch.setattr(self_improvement_module.BacktestEngine, "run", staticmethod(_run))
    monkeypatch.setattr(self_improvement_module.db, "get_latest_deployed_strategy_version", _get_latest_deployed)
    monkeypatch.setattr(self_improvement_module.db, "insert", _insert_should_not_be_called)
    monkeypatch.setattr(self_improvement_module, "publish_event", _publish_should_not_be_called)

    row = await self_improvement_module.propose_candidate("KR", "RSI 임계값 조정")

    assert row is None


@pytest.mark.asyncio
async def test_propose_candidate_passes_when_not_worse_than_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run(strategy, market, period, initial_capital):  # noqa: ANN001
        return BacktestResult(win_rate=0.65, avg_return=0.05, mdd=-0.03, sharpe_ratio=1.7, profit_factor=1.8)

    async def _get_latest_deployed(market):  # noqa: ANN001
        return {
            "strategy_version": "v1.0.0",
            "prompt_version": "system_kr_v1",
            "backtest_result": {"win_rate": 0.65, "sharpe_ratio": 1.7, "mdd": -0.03},
        }

    inserted: list[dict] = []

    async def _insert(table, values):  # noqa: ANN001
        inserted.append(values)
        return {**values, "id": 2}

    async def _publish(event_type, *, mode, market, payload, correlation_id=None):  # noqa: ANN001
        pass

    monkeypatch.setattr(self_improvement_module.BacktestEngine, "run", staticmethod(_run))
    monkeypatch.setattr(self_improvement_module.db, "get_latest_deployed_strategy_version", _get_latest_deployed)
    monkeypatch.setattr(self_improvement_module.db, "insert", _insert)
    monkeypatch.setattr(self_improvement_module, "publish_event", _publish)

    row = await self_improvement_module.propose_candidate("KR", "RSI 임계값 조정")

    assert row is not None
    assert inserted[0]["based_on"] == "v1.0.0"
    assert inserted[0]["prompt_version"] == "system_kr_v1"


@pytest.mark.asyncio
async def test_propose_candidate_returns_none_when_no_strategies_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.trading.decision as decision_module

    monkeypatch.setattr(decision_module, "get_registered_strategies", lambda market: [])

    row = await self_improvement_module.propose_candidate("KR", "변경 제안")

    assert row is None
