"""모의투자 모드 — 전략 개발 중 실제 자금 없이 신호 정확도를 검증한다."""

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy


class PaperTradingRunner:
    def __init__(self, strategy: BaseStrategy) -> None:
        self.strategy = strategy

    async def step(self, state: StateSnapshot) -> Decision | None:
        raise NotImplementedError
