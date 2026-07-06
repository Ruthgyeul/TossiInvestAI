"""AIGateway 추상 인터페이스. 모든 AI 호출은 core/gateway/ 모듈에서만 수행한다 (CODING_RULES.md)."""

from abc import ABC, abstractmethod

from core.models import Decision, StateSnapshot


class AIGateway(ABC):
    @abstractmethod
    async def decide(self, state: StateSnapshot) -> Decision: ...

    @abstractmethod
    async def summarize_news(self, articles: list[str]) -> str: ...
