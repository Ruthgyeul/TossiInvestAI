"""전략 확장 지점. 새 전략은 BaseStrategy를 상속한다 (CODING_RULES.md 확장성 원칙)."""

from abc import ABC, abstractmethod

from core.models import Decision, StateSnapshot


class BaseStrategy(ABC):
    version: str

    @abstractmethod
    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        """규칙 기반으로 판단 가능하면 Decision을, 모호하면 None을 반환한다."""
        ...
