"""백테스트 엔진 — 1Y·3Y·5Y 과거 데이터로 전략 성과를 검증한다 (docs/BIN.md).

토스증권 API에는 기간(연 단위) 지정 캔들 조회 파라미터가 없다(docs/TOSS_API.md) — 대신
`get_candles(symbol, "1d")`가 반환하는 전체 일봉 히스토리 중 최근 N거래일(1Y=252·3Y=756·
5Y=1260)만 사용한다. 실제 보유 데이터가 요청 기간보다 짧으면 있는 만큼만 사용한다.

관심 종목별로 초기 자금을 균등 배분해 독립적으로 시뮬레이션하고, 일별 총자산을
합산해 MDD·샤프 지수를 계산한다. 체결가는 단순화를 위해 신호가 나온 날의 종가를 사용한다
(실제 슬리피지·체결 지연은 반영하지 않는다).
"""

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from core.market_data import indicators
from core.market_data.watchlist import get_watchlist
from core.models import StateSnapshot
from core.strategy.base import BaseStrategy
from core.toss import market as toss_market

_PERIOD_TRADING_DAYS: dict[str, int] = {"1Y": 252, "3Y": 756, "5Y": 1260}
_WARMUP_DAYS = 60  # EMA60 계산에 필요한 최소 과거 데이터


@dataclass
class BacktestResult:
    win_rate: float
    avg_return: float
    mdd: float
    sharpe_ratio: float
    profit_factor: float


@dataclass
class _ClosedTrade:
    pnl: float
    return_pct: float


_EMPTY_RESULT = BacktestResult(win_rate=0.0, avg_return=0.0, mdd=0.0, sharpe_ratio=0.0, profit_factor=0.0)


class BacktestEngine:
    @staticmethod
    async def run(
        strategy: BaseStrategy,
        market: Literal["KR", "US"],
        period: Literal["1Y", "3Y", "5Y"],
        initial_capital: int,
    ) -> BacktestResult:
        watchlist_items = await get_watchlist(market)
        symbols = [item["symbol"] for item in watchlist_items]
        if not symbols:
            return _EMPTY_RESULT

        requested_days = _PERIOD_TRADING_DAYS[period]
        histories: dict[str, tuple[list[float], list[float]]] = {}
        for symbol in symbols:
            candles = await toss_market.get_candles(symbol, "1d")
            closes = [c["close"] for c in candles]
            volumes = [c.get("volume", 0) for c in candles]
            if len(closes) >= _WARMUP_DAYS + 2:
                histories[symbol] = (closes[-requested_days:], volumes[-requested_days:])

        if not histories:
            return _EMPTY_RESULT

        common_days = min(len(closes) for closes, _ in histories.values())

        capital_per_symbol = initial_capital / len(histories)
        cash = {symbol: capital_per_symbol for symbol in histories}
        qty = {symbol: 0 for symbol in histories}
        avg_price = {symbol: 0.0 for symbol in histories}

        trades: list[_ClosedTrade] = []
        equity_curve: list[float] = []

        for day in range(_WARMUP_DAYS, common_days):
            for symbol, (closes, volumes) in histories.items():
                price = closes[day]
                window = pd.Series(closes[: day + 1])

                data: dict = {
                    "price": price,
                    "rsi_14": indicators.calculate_rsi(window),
                    "ema_20": indicators.calculate_ema(window, 20),
                    "ema_60": indicators.calculate_ema(window, 60),
                    "volume_ratio": indicators.calculate_volume_ratio(volumes[day], volumes[day - 1]),
                }
                data["macd"], data["macd_signal"] = indicators.calculate_macd(window)
                data["bb_upper"], data["bb_lower"] = indicators.calculate_bollinger_bands(window)

                holdings = (
                    [{"symbol": symbol, "quantity": qty[symbol], "avg_price": avg_price[symbol]}]
                    if qty[symbol] > 0
                    else []
                )
                state = StateSnapshot(
                    bot="Bin",
                    market=market,  # type: ignore[arg-type]
                    mode="SIMULATION",
                    strategy_version=strategy.version,
                    prompt_version="backtest",
                    timestamp=f"backtest-day-{day}",
                    exchange_rate_krw_usd=1.0,
                    prices={symbol: data},
                    portfolio={"holdings": holdings},
                )

                signal = await strategy.generate_signal(state)
                if signal is not None and signal.action == "BUY" and qty[symbol] == 0:
                    buy_qty = int(cash[symbol] // price) if price > 0 else 0
                    if buy_qty > 0:
                        cash[symbol] -= buy_qty * price
                        qty[symbol] = buy_qty
                        avg_price[symbol] = price
                elif signal is not None and signal.action == "SELL" and qty[symbol] > 0:
                    proceeds = qty[symbol] * price
                    cost = qty[symbol] * avg_price[symbol]
                    trades.append(
                        _ClosedTrade(pnl=proceeds - cost, return_pct=(price - avg_price[symbol]) / avg_price[symbol])
                    )
                    cash[symbol] += proceeds
                    qty[symbol] = 0
                    avg_price[symbol] = 0.0

            total_equity = sum(
                cash[symbol] + qty[symbol] * histories[symbol][0][day] for symbol in histories
            )
            equity_curve.append(total_equity)

        if not trades:
            return BacktestResult(
                win_rate=0.0,
                avg_return=0.0,
                mdd=indicators.calculate_max_drawdown_pct(equity_curve),
                sharpe_ratio=indicators.calculate_sharpe_ratio(equity_curve),
                profit_factor=0.0,
            )

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))

        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        else:
            # 손실 거래가 없으면 비율이 정의되지 않는다 — JSON(Infinity는 유효하지 않다)으로
            # 안전하게 전달할 수 있는 유한한 상한값으로 표기한다.
            profit_factor = 999.0 if gross_profit > 0 else 0.0

        return BacktestResult(
            win_rate=len(wins) / len(trades),
            avg_return=sum(t.return_pct for t in trades) / len(trades),
            mdd=indicators.calculate_max_drawdown_pct(equity_curve),
            sharpe_ratio=indicators.calculate_sharpe_ratio(equity_curve),
            profit_factor=profit_factor,
        )
