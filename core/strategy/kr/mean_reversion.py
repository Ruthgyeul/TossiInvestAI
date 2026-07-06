"""KR 평균회귀 전략 — RSI 과매수/과매도 반등 기반 (docs/BIN.md STEP 3 규칙 기반 필터와 연동)."""

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    version = "v1.0.0"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        raise NotImplementedError
