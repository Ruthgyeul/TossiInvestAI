"""US 오버나이트 전략 — 정규장 마감 보유 포지션의 익일 갭 대응."""

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy


class OvernightStrategy(BaseStrategy):
    version = "v1.0.0"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        raise NotImplementedError
