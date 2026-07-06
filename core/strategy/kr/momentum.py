"""KR 모멘텀 전략 — 거래량 급증 + 추세 돌파 기반 (docs/BIN.md STEP 3 규칙 기반 필터와 연동)."""

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    version = "v1.0.0"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        raise NotImplementedError
