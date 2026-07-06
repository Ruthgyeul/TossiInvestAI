"""Gemini Free Tier — 2순위 AI Gateway. 뉴스 요약·보조 분석 전용 (docs/BIN.md)."""

import google.generativeai as genai

from core.config import settings
from core.gateway.base import AIGateway
from core.models import Decision, StateSnapshot

genai.configure(api_key=settings.GEMINI_API_KEY)


class GeminiGateway(AIGateway):
    async def decide(self, state: StateSnapshot) -> Decision:
        raise NotImplementedError

    async def summarize_news(self, articles: list[str]) -> str:
        raise NotImplementedError


gemini_gateway = GeminiGateway()
