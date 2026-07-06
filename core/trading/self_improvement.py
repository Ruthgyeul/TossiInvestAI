"""자기개선 파이프라인 핵심 — 개선 후보 제안 → 백테스트 검증 → Discord 게시 (docs/SELF_IMPROVEMENT.md).

이 모듈은 "제안(propose)"까지만 자동화한다 — 배포는 항상 Discord `/version approve`를 통한
개발자 승인이 필요하다(원칙 1). 하루 1회 Reflection 호출 결과를 재사용할 뿐, 별도의 상시
Claude 호출을 만들지 않는다(하드 금지 사항 마지막 항목).
"""

from datetime import datetime, timezone
from typing import Literal

import structlog

from core.config import settings
from core.db import store as db
from core.events.publisher import publish_event
from core.models import Market
from core.strategy.backtest import BacktestEngine, BacktestResult

log = structlog.get_logger(__name__)

_BACKTEST_PERIOD: Literal["1Y"] = "1Y"
_BACKTEST_CAPITAL_KRW = 500_000


def _regressed(candidate: BacktestResult, baseline: dict) -> bool:
    """승률·샤프 지수·MDD 중 하나라도 기존 배포 버전 대비 악화되면 True
    (docs/SELF_IMPROVEMENT.md "1. 백테스트 — 기존 버전 대비 승률·샤프 지수·MDD 열화 없음").

    MDD는 항상 0 이하(음수)로 표현되므로 "더 작다(더 음수) = 낙폭이 더 크다 = 악화"이다.
    """
    return (
        candidate.win_rate < baseline.get("win_rate", 0.0)
        or candidate.sharpe_ratio < baseline.get("sharpe_ratio", 0.0)
        or candidate.mdd < baseline.get("mdd", 0.0)
    )


async def propose_candidate(market: Market, proposed_change: str) -> dict | None:
    """Reflection이 추출한 개선안을 백테스트로 검증하고, 통과하면 승인 대기 후보로 등록한다.

    검증에 실패(기존 대비 열화)하면 후보를 폐기하고 None을 반환한다 — 아무것도 저장·배포되지
    않는다(docs/SELF_IMPROVEMENT.md "실패 시: 후보 폐기").
    """
    from core.trading.decision import get_registered_strategies

    strategies = get_registered_strategies(market)
    if not strategies:
        return None

    # 여러 전략이 등록된 시장(KR)에서는 대표(첫 번째 등록) 전략으로 검증한다 — decision.py의
    # 전략 디스패치 순서가 이미 우선순위를 반영하므로 동일한 순서를 대표성 기준으로 삼는다.
    strategy = strategies[0]

    result = await BacktestEngine.run(
        strategy=strategy,
        market=market,
        period=_BACKTEST_PERIOD,
        initial_capital=_BACKTEST_CAPITAL_KRW,
    )

    baseline = await db.get_latest_deployed_strategy_version(market)
    if baseline is not None and baseline.get("backtest_result") and _regressed(result, baseline["backtest_result"]):
        log.info(
            "self_improvement_candidate_discarded",
            market=market,
            reason="backtest_regression",
            candidate_win_rate=result.win_rate,
            baseline_win_rate=baseline["backtest_result"].get("win_rate"),
        )
        return None

    backtest_result_payload = {
        "win_rate": result.win_rate,
        "avg_return": result.avg_return,
        "mdd": result.mdd,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
    }

    row = await db.insert(
        "strategy_versions",
        {
            "market": market,
            "strategy_version": strategy.version,
            "prompt_version": baseline["prompt_version"] if baseline else f"system_{market.lower()}_v1",
            "based_on": baseline["strategy_version"] if baseline else None,
            "change_summary": proposed_change,
            "backtest_result": backtest_result_payload,
            "approved_by": None,
            "proposed_at": datetime.now(timezone.utc),
            "deployed_at": None,
        },
    )

    log.info("self_improvement_candidate_proposed", market=market, candidate_id=row["id"])
    await publish_event(
        "version_candidate_ready",
        mode=settings.run_mode,
        market=market,
        payload={
            "id": row["id"],
            "market": market,
            "strategyVersion": row["strategy_version"],
            "changeSummary": proposed_change,
            "backtestResult": backtest_result_payload,
        },
    )
    return row
