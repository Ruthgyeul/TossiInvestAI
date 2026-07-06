"""백테스트 엔진 — 1Y·3Y·5Y 과거 데이터로 전략 성과를 검증한다 (docs/BIN.md)."""

from dataclasses import dataclass
from typing import Literal

from core.strategy.base import BaseStrategy


@dataclass
class BacktestResult:
    win_rate: float
    avg_return: float
    mdd: float
    sharpe_ratio: float
    profit_factor: float


class BacktestEngine:
    @staticmethod
    async def run(
        strategy: BaseStrategy,
        market: Literal["KR", "US"],
        period: Literal["1Y", "3Y", "5Y"],
        initial_capital: int,
    ) -> BacktestResult:
        raise NotImplementedError
