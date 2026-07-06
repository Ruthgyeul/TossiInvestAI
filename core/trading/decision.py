"""AI Gateway 호출 진입점. 이 모듈만이 매매 결정을 위해 Claude를 호출한다 (CLAUDE.md 절대 규칙 5)."""

from core.models import Decision, StateSnapshot


def rule_based_filter(state: StateSnapshot) -> Decision | None:
    """규칙 기반으로 명확한 신호(RSI>75 매도, RSI<28 매수, VI 발동 제외 등)를 즉시 처리한다.

    처리 가능하면 Decision을, 모호하면 None을 반환해 Claude 호출로 넘긴다.
    """
    raise NotImplementedError


async def get_decision(state: StateSnapshot) -> Decision:
    """1. 규칙 기반 필터 → 2. Claude 직접 호출 → 3. 실패 시 DeepSeek 폴백."""
    if signal := rule_based_filter(state):
        return signal

    raise NotImplementedError
