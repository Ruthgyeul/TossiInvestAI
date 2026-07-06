"""DeepSeek Free Tier — 3순위 AI Gateway. Claude 장애 시에만 폴백 호출한다 (docs/BIN.md)."""

import openai

from core.config import settings
from core.gateway.base import AIGateway
from core.models import Decision, StateSnapshot

_client = openai.AsyncOpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


class DeepSeekGateway(AIGateway):
    async def decide(self, state: StateSnapshot) -> Decision:
        raise NotImplementedError

    async def summarize_news(self, articles: list[str]) -> str:
        raise NotImplementedError


deepseek_gateway = DeepSeekGateway()
