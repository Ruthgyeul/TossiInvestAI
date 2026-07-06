"""모의투자 모드 — 전략 개발 중 실제 자금 없이 신호 정확도를 검증한다.

core/simulation/portfolio.py(SIMULATION 모드, 실전과 100% 동일한 리허설)와 달리, 이 모듈은
Safety Gate·가상 체결·자금 배분 없이 전략이 내는 신호 자체만 `paper_trades`에 기록한다 —
개발 중인 전략을 트레이딩 루프에 연결하기 전 신호 발생 빈도·정확도를 가볍게 확인하는 용도다.
"""

from core.db import store as db
from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy


class PaperTradingRunner:
    def __init__(self, strategy: BaseStrategy) -> None:
        self.strategy = strategy

    async def step(self, state: StateSnapshot) -> Decision | None:
        """전략 신호를 생성하고(주문 없이) `paper_trades`에 기록한다."""
        decision = await self.strategy.generate_signal(state)
        if decision is not None:
            await db.insert(
                "paper_trades",
                {
                    "symbol": decision.symbol,
                    "strategy_version": self.strategy.version,
                    "pnl_krw": None,
                },
            )
        return decision
