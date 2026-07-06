"""Claude API 직접 호출 — 1순위 AI Gateway. Prompt Caching L1(1h)·L2(5m) 적용 (docs/BIN.md)."""

import anthropic

from core.config import settings
from core.db import store as db
from core.fund.manager import fund_manager
from core.gateway.base import (
    AIGateway,
    build_portfolio_block,
    build_realtime_block,
    load_system_prompt,
    parse_decision_json,
)
from core.models import Decision, StateSnapshot

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


class ClaudeGateway(AIGateway):
    async def decide(self, state: StateSnapshot) -> Decision:
        response = await _call_claude(
            system_prompt=load_system_prompt(state.market),
            long_term_memory=await _load_long_term_memory(state),
            realtime_market=build_realtime_block(state),
            portfolio_snapshot=build_portfolio_block(state),
        )
        await _record_usage(response.usage)
        return _parse_decision(_extract_text(response))

    async def summarize_news(self, articles: list[str]) -> str:
        """뉴스 요약은 Gemini Gateway 전담 — Claude는 매매 결정만 담당 (docs/BIN.md)."""
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


async def _load_long_term_memory(state: StateSnapshot) -> str:
    """L2 — 장 시작 시 DB에서 조회, 장중 불변 (docs/BIN.md)."""
    memory = await db.get_long_term_memory(state.market)

    lines = [
        f"최근 30일 거래: {memory.get('trade_count', 0)}건 "
        f"(승률 {memory.get('win_rate', 0):.1%})",
        f"최근 자기평가 요약: {memory.get('reflection_summary', '없음')}",
    ]
    for symbol, stats in memory.get("symbol_stats", {}).items():
        lines.append(
            f"{symbol}: 누적 손익 {stats.get('pnl_krw', 0):,} KRW "
            f"({stats.get('trade_count', 0)}회 거래)"
        )
    return "\n".join(lines)


async def _record_usage(usage: anthropic.types.Usage) -> None:
    """core/fund/manager.py FundManager.record_api_usage 로 위임한다."""
    await fund_manager.record_api_usage(
        model=settings.CLAUDE_MODEL,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
        cache_write_tokens=usage.cache_creation_input_tokens or 0,
    )


def _extract_text(response: anthropic.types.Message) -> str:
    block = response.content[0]
    if not isinstance(block, anthropic.types.TextBlock):
        raise ValueError(f"Claude 응답이 텍스트 블록이 아님: {type(block).__name__}")
    return block.text


def _parse_decision(text: str) -> Decision:
    return parse_decision_json(text)


claude_gateway = ClaudeGateway()
