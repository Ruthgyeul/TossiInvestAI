"""DeepSeek Free Tier — 3순위 AI Gateway. Claude 장애 시에만 폴백 호출한다 (docs/BIN.md)."""

import openai

from core.config import settings
from core.gateway.base import (
    AIGateway,
    build_portfolio_block,
    build_realtime_block,
    load_system_prompt,
    parse_decision_json,
)
from core.models import Decision, StateSnapshot

_client = openai.AsyncOpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


class DeepSeekGateway(AIGateway):
    async def decide(self, state: StateSnapshot) -> Decision:
        """Claude 장애 시 폴백 — L2 장기 기억 없이 L1·L3·L4만으로 판단한다 (docs/BIN.md)."""
        response = await _client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.DEEPSEEK_MAX_TOKENS,
            messages=[
                {"role": "system", "content": load_system_prompt(state.market)},
                {
                    "role": "user",
                    "content": (
                        f"[실시간 시장 데이터]\n{build_realtime_block(state)}\n\n"
                        f"[포트폴리오]\n{build_portfolio_block(state)}\n\n"
                        "위 데이터를 분석해 매매 결정을 JSON으로 출력하라."
                    ),
                },
            ],
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("DeepSeek 응답에 content가 없음")
        return parse_decision_json(content)

    async def summarize_news(self, articles: list[str]) -> str:
        """뉴스 요약은 Gemini Gateway 전담 — DeepSeek은 Claude 폴백 전용 (docs/BIN.md)."""
        raise NotImplementedError


deepseek_gateway = DeepSeekGateway()
