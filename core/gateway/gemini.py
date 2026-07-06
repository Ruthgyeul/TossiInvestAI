"""Gemini Free Tier — 2순위 AI Gateway. 뉴스 요약·보조 분석 전용 (docs/BIN.md)."""

import google.generativeai as genai

from core.config import settings
from core.gateway.base import AIGateway
from core.models import Decision, StateSnapshot

genai.configure(api_key=settings.GEMINI_API_KEY)

_SUMMARY_PROMPT = (
    "너는 빈(Bin)의 뉴스 요약 보조 AI다. 아래 기사들을 투자 판단에 참고할 수 있도록 "
    "핵심 사실과 시장에 미칠 영향 위주로 한국어 두세 문장으로 요약하라."
)


class GeminiGateway(AIGateway):
    async def decide(self, state: StateSnapshot) -> Decision:
        """Gemini는 매매 결정을 내리지 않는다 — 뉴스 요약·보조 분석 전용 (docs/BIN.md)."""
        raise NotImplementedError

    async def summarize_news(self, articles: list[str]) -> str:
        if not articles:
            return ""

        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        articles_block = "\n\n".join(f"- {article}" for article in articles)
        response = await model.generate_content_async(
            f"{_SUMMARY_PROMPT}\n\n{articles_block}"
        )
        return response.text.strip()


gemini_gateway = GeminiGateway()
