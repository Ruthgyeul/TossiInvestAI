"""AI Gateway 호출 진입점. 이 모듈만이 매매 결정을 위해 Claude를 호출한다 (CLAUDE.md 절대 규칙 5)."""

import anthropic
import structlog

from core.gateway.claude import claude_gateway
from core.gateway.deepseek import deepseek_gateway
from core.models import Decision, Market, StateSnapshot
from core.strategy.base import BaseStrategy
from core.strategy.kr.mean_reversion import MeanReversionStrategy
from core.strategy.kr.momentum import MomentumStrategy as KRMomentumStrategy
from core.strategy.us.momentum import MomentumStrategy as USMomentumStrategy
from core.strategy.us.overnight import OvernightStrategy

log = structlog.get_logger(__name__)

# 시장별 규칙 기반 전략 목록. 앞의 전략이 신호를 내면 뒤는 평가하지 않는다
# (CODING_RULES.md 확장성 원칙 — 새 전략은 core/strategy/{market}/*.py에 BaseStrategy를
# 상속해 추가하고 이 목록에 등록한다).
_STRATEGIES_BY_MARKET: dict[Market, list[BaseStrategy]] = {
    "KR": [MeanReversionStrategy(), KRMomentumStrategy()],
    "US": [OvernightStrategy(), USMomentumStrategy()],
}


def get_registered_strategies(market: Market) -> list[BaseStrategy]:
    """core/trading/self_improvement.py가 백테스트 검증 대상 전략을 조회할 때 사용한다."""
    return _STRATEGIES_BY_MARKET.get(market, [])


async def rule_based_filter(state: StateSnapshot) -> Decision | None:
    """시장별로 등록된 전략을 순서대로 시도해 규칙 기반으로 처리 가능한 신호를 즉시 반환한다.

    어떤 전략도 신호를 내지 않으면 None을 반환해 Claude 호출로 넘긴다.
    """
    for strategy in _STRATEGIES_BY_MARKET.get(state.market, []):
        if signal := await strategy.generate_signal(state):
            return signal
    return None


def _constrain_to_known_symbols(decision: Decision, state: StateSnapshot) -> Decision:
    """AI 결정의 종목을 이번 루프에서 실제로 분석한 종목(state.prices)·보유 종목으로 제한한다.

    모델 입력에는 외부에서 조작 가능한 데이터(뉴스 헤드라인 등)가 섞이므로, 프롬프트 주입으로
    모델이 임의의 종목 매매를 지시하더라도 여기서 HOLD로 강등해 주문이 나가지 않게 한다.
    Discord `/buy`·`/sell` 수동 주문은 이 함수를 거치지 않으므로 영향이 없다.
    """
    if decision.action == "HOLD":
        return decision

    held_symbols = {h.get("symbol") for h in state.portfolio.get("holdings", [])}
    if decision.symbol in state.prices or decision.symbol in held_symbols:
        return decision

    log.warning(
        "decision_symbol_not_in_state",
        symbol=decision.symbol,
        action=decision.action,
        market=state.market,
    )
    return Decision(
        decision_id=decision.decision_id,
        action="HOLD",
        symbol=decision.symbol,
        quantity=0,
        order_type="MARKET",
        price=None,
        confidence=decision.confidence,
        reason=f"분석 대상이 아닌 종목({decision.symbol}) 결정 차단 — HOLD로 대체",
        risk_level="HIGH",
    )


async def get_decision(state: StateSnapshot) -> Decision:
    """1. 규칙 기반 필터 → 2. Claude 직접 호출 → 3. 실패 시 DeepSeek 폴백."""
    if signal := await rule_based_filter(state):
        return signal

    try:
        return _constrain_to_known_symbols(await claude_gateway.decide(state), state)
    except (anthropic.APIStatusError, anthropic.APITimeoutError) as e:
        log.error("claude_failed", error=str(e))

    log.warning("fallback_to_deepseek")
    return _constrain_to_known_symbols(await deepseek_gateway.decide(state), state)
