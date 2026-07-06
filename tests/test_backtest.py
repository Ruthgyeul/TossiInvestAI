"""BacktestEngine 승률·MDD·샤프 지수·수익 팩터 계산 테스트 (docs/BIN.md)."""

import pytest

from core.models import Decision, StateSnapshot
from core.strategy.backtest import BacktestEngine
from core.strategy.base import BaseStrategy


class _FixedThresholdStrategy(BaseStrategy):
    """테스트 전용 — 실제 지표 대신 가격 임계값으로만 매수/매도를 결정한다."""

    version = "test-v1"

    def __init__(self, buy_at_or_below: float, sell_at_or_above: float) -> None:
        self.buy_at_or_below = buy_at_or_below
        self.sell_at_or_above = sell_at_or_above

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        symbol, data = next(iter(state.prices.items()))
        held = bool(state.portfolio.get("holdings"))
        price = data["price"]

        if not held and price <= self.buy_at_or_below:
            return self.make_decision(symbol=symbol, action="BUY", quantity=1, price=None, reason="test-buy")
        if held and price >= self.sell_at_or_above:
            return self.make_decision(symbol=symbol, action="SELL", quantity=1, price=None, reason="test-sell")
        return None


def _flat_then_move_candles(flat_days: int, moves: list[float]) -> list[dict]:
    closes = [100.0] * flat_days + moves
    return [{"close": c, "volume": 1_000} for c in closes]


@pytest.mark.asyncio
async def test_backtest_computes_metrics_for_one_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = _flat_then_move_candles(60, [90.0, 120.0])  # day60=매수가, day61=매도가

    async def _get_watchlist(market):  # noqa: ANN001
        return [{"symbol": "TEST"}]

    async def _get_candles(symbol, timeframe):  # noqa: ANN001
        return candles

    import core.strategy.backtest as backtest_module

    monkeypatch.setattr(backtest_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(backtest_module.toss_market, "get_candles", _get_candles)

    result = await BacktestEngine.run(
        strategy=_FixedThresholdStrategy(buy_at_or_below=95.0, sell_at_or_above=110.0),
        market="KR",
        period="1Y",
        initial_capital=500_000,
    )

    assert result.win_rate == 1.0
    assert result.avg_return == pytest.approx((120.0 - 90.0) / 90.0)
    assert result.profit_factor == 999.0  # 손실 거래가 없어 유한한 상한값
    assert result.mdd == 0.0


@pytest.mark.asyncio
async def test_backtest_returns_zeroed_result_when_watchlist_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_watchlist(market):  # noqa: ANN001
        return []

    import core.strategy.backtest as backtest_module

    monkeypatch.setattr(backtest_module, "get_watchlist", _get_watchlist)

    result = await BacktestEngine.run(
        strategy=_FixedThresholdStrategy(buy_at_or_below=95.0, sell_at_or_above=110.0),
        market="KR",
        period="1Y",
        initial_capital=500_000,
    )

    assert result.win_rate == 0.0
    assert result.mdd == 0.0
    assert result.sharpe_ratio == 0.0
    assert result.profit_factor == 0.0


@pytest.mark.asyncio
async def test_backtest_skips_symbols_with_insufficient_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_watchlist(market):  # noqa: ANN001
        return [{"symbol": "TOO_SHORT"}]

    async def _get_candles(symbol, timeframe):  # noqa: ANN001
        return [{"close": 100.0, "volume": 1_000}] * 10  # 60일 워밍업에 못 미침

    import core.strategy.backtest as backtest_module

    monkeypatch.setattr(backtest_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(backtest_module.toss_market, "get_candles", _get_candles)

    result = await BacktestEngine.run(
        strategy=_FixedThresholdStrategy(buy_at_or_below=95.0, sell_at_or_above=110.0),
        market="KR",
        period="1Y",
        initial_capital=500_000,
    )

    assert result.win_rate == 0.0
    assert result.avg_return == 0.0


@pytest.mark.asyncio
async def test_backtest_no_completed_trades_still_reports_mdd_and_sharpe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = _flat_then_move_candles(60, [200.0, 200.0])  # 매수 임계값 미달 — 신호 없음

    async def _get_watchlist(market):  # noqa: ANN001
        return [{"symbol": "TEST"}]

    async def _get_candles(symbol, timeframe):  # noqa: ANN001
        return candles

    import core.strategy.backtest as backtest_module

    monkeypatch.setattr(backtest_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(backtest_module.toss_market, "get_candles", _get_candles)

    result = await BacktestEngine.run(
        strategy=_FixedThresholdStrategy(buy_at_or_below=95.0, sell_at_or_above=110.0),
        market="KR",
        period="1Y",
        initial_capital=500_000,
    )

    assert result.win_rate == 0.0
    assert result.profit_factor == 0.0
