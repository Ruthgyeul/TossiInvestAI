"""Claude API 직접 호출 — 1순위 AI Gateway. Prompt Caching L1(1h)·L2(5m) 적용 (docs/BIN.md)."""

import anthropic

from core.config import settings
from core.gateway.base import AIGateway
from core.models import Decision, StateSnapshot

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


class ClaudeGateway(AIGateway):
    async def decide(self, state: StateSnapshot) -> Decision:
        response = await _call_claude(
            system_prompt=_load_system_prompt(state.market),
            long_term_memory=_load_long_term_memory(state),
            realtime_market=_build_realtime_block(state),
            portfolio_snapshot=_build_portfolio_block(state),
        )
        _record_usage(response.usage)
        return _parse_decision(response.content[0].text)

    async def summarize_news(self, articles: list[str]) -> str:
        raise NotImplementedError


async def _call_claude(
    system_prompt: str,      # L1 — prompts/system_kr.md 또는 system_us.md
    long_term_memory: str,   # L2 — 장 시작 시 조회, 장중 불변
    realtime_market: str,    # L3 — 매 루프 갱신
    portfolio_snapshot: str, # L4 — 매 루프 갱신
) -> anthropic.types.Message:
    return await _client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=settings.CLAUDE_MAX_TOKENS,
        # L1 — 1h 캐시
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }],
        messages=[{
            "role": "user",
            "content": [
                # L2 — 5m 캐시
                {
                    "type": "text",
                    "text": f"[장기 기억]\n{long_term_memory}",
                    "cache_control": {"type": "ephemeral"},
                },
                # L3 — 캐시 없음
                {
                    "type": "text",
                    "text": f"[실시간 시장 데이터]\n{realtime_market}",
                },
                # L4 — 캐시 없음
                {
                    "type": "text",
                    "text": f"[포트폴리오]\n{portfolio_snapshot}\n\n위 데이터를 분석해 매매 결정을 JSON으로 출력하라.",
                },
            ],
        }],
    )


def _load_system_prompt(market: str) -> str:
    raise NotImplementedError


def _load_long_term_memory(state: StateSnapshot) -> str:
    raise NotImplementedError


def _build_realtime_block(state: StateSnapshot) -> str:
    raise NotImplementedError


def _build_portfolio_block(state: StateSnapshot) -> str:
    raise NotImplementedError


def _record_usage(usage: anthropic.types.Usage) -> None:
    """core/fund/manager.py FundManager.record_api_usage 로 위임한다."""
    raise NotImplementedError


def _parse_decision(text: str) -> Decision:
    raise NotImplementedError


claude_gateway = ClaudeGateway()
