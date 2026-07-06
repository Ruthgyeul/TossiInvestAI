"""US 모멘텀 전략 — 정규장 추세 돌파 기반."""

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    version = "v1.0.0"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        raise NotImplementedError
