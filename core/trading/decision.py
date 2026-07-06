"""AI Gateway 호출 진입점. 이 모듈만이 매매 결정을 위해 Claude를 호출한다 (CLAUDE.md 절대 규칙 5)."""

import uuid

import anthropic
import structlog

from core.gateway.claude import claude_gateway
from core.gateway.deepseek import deepseek_gateway
from core.models import Decision, StateSnapshot

log = structlog.get_logger(__name__)

_RSI_OVERBOUGHT = 75
_RSI_OVERSOLD = 28
# 규칙 기반 매수는 소액만 즉시 진입시킨다 — 최종 한도는 Safety Gate가 검증한다 (docs/SAFETY.md).
_RULE_BASED_BUY_KRW = 50_000


def rule_based_filter(state: StateSnapshot) -> Decision | None:
    """규칙 기반으로 명확한 신호(RSI>75 매도, RSI<28 매수, VI 발동 제외 등)를 즉시 처리한다.

    처리 가능하면 Decision을, 모호하면 None을 반환해 Claude 호출로 넘긴다.
    """
    holdings = {h["symbol"]: h for h in state.portfolio.get("holdings", [])}

    for symbol, data in state.prices.items():
        rsi = data.get("rsi_14")
        if rsi is None:
            continue

        holding = holdings.get(symbol)

        if holding is not None and rsi > _RSI_OVERBOUGHT:
            return _rule_decision(
                symbol=symbol,
                action="SELL",
                quantity=holding["quantity"],
                price=None,
                reason=f"RSI {rsi:.1f} > {_RSI_OVERBOUGHT} 과매수 구간 — 보유 물량 매도",
            )

        if holding is None and rsi < _RSI_OVERSOLD:
            if state.market == "KR" and data.get("vi_triggered"):
                continue

            price = data.get("price")
            quantity = int(_RULE_BASED_BUY_KRW // price) if price else 0
            if quantity <= 0:
                continue

            return _rule_decision(
                symbol=symbol,
                action="BUY",
                quantity=quantity,
                price=None,
                reason=f"RSI {rsi:.1f} < {_RSI_OVERSOLD} 과매도 구간 — 소액 매수",
            )

    return None


def _rule_decision(
    *, symbol: str, action: str, quantity: int, price: float | None, reason: str
) -> Decision:
    return Decision(
        decision_id=str(uuid.uuid4()),
        action=action,  # type: ignore[arg-type]
        symbol=symbol,
        quantity=quantity,
        order_type="MARKET",
        price=price,
        confidence=1.0,
        reason=reason,
        risk_level="LOW",
    )


async def get_decision(state: StateSnapshot) -> Decision:
    """1. 규칙 기반 필터 → 2. Claude 직접 호출 → 3. 실패 시 DeepSeek 폴백."""
    if signal := rule_based_filter(state):
        return signal

    try:
        return await claude_gateway.decide(state)
    except (anthropic.APIStatusError, anthropic.APITimeoutError) as e:
        log.error("claude_failed", error=str(e))

    log.warning("fallback_to_deepseek")
    return await deepseek_gateway.decide(state)
