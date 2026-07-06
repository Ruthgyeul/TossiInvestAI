"""KR·US 트레이딩 루프 진입점. APScheduler가 시장별로 독립 실행한다 (docs/BIN.md)."""

from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import structlog

from core.config import settings
from core.db import store as db
from core.events import calendar
from core.events.publisher import publish_event
from core.fund.manager import fund_manager
from core.market_data.collector import collect_market_snapshot
from core.market_data.watchlist import get_watchlist
from core.models import Decision, Market, RunMode, StateSnapshot
from core.trading.decision import get_decision
from core.trading.executor import execute

log = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_STRATEGY_VERSION = "v1.0.0"


def _prompt_version(market: Market) -> str:
    return "system_kr_v1" if market == "KR" else "system_us_v1"


def _holding_entry(raw: dict) -> dict:
    return {
        "symbol": raw["symbol"],
        "quantity": raw["quantity"],
        "avg_price": raw.get("avgPrice", 0),
        "unrealized_pnl": raw.get("unrealizedPnl", 0),
    }


async def _build_state_snapshot(market: Market) -> StateSnapshot:
    """STEP 2·4 — 시장 데이터 수집 후 Claude에 주입할 StateSnapshot을 구성한다."""
    watchlist_items = await get_watchlist(market)
    symbols = [item["symbol"] for item in watchlist_items]
    snapshot = await collect_market_snapshot(market, symbols)
    events_today = await calendar.get_events_today(market)

    mode = "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
    portfolio_status = await fund_manager.get_portfolio_status(mode)  # type: ignore[arg-type]

    return StateSnapshot(
        bot="Bin",
        market=market,
        mode=settings.run_mode,
        strategy_version=_STRATEGY_VERSION,
        prompt_version=_prompt_version(market),
        timestamp=datetime.now(_KST).isoformat(),
        exchange_rate_krw_usd=snapshot["exchange_rate_krw_usd"],
        prices=snapshot["prices"],
        portfolio={
            "total_value_krw": portfolio_status["totalValueKrw"],
            "operating_funds_krw": await fund_manager.get_operating_funds_krw(mode),  # type: ignore[arg-type]
            "cash_buffer_krw": portfolio_status["cashBufferKrw"],
            "holdings": [_holding_entry(h) for h in snapshot["holdings"]],
            "open_orders": [],
            "today_realized_pnl_krw": portfolio_status["todayPnlKrw"],
            "api_cost_month_krw": await fund_manager.estimated_api_cost_krw(),
        },
        market_events_today=events_today,
    )


def _infer_model_used(decision: Decision) -> str:
    """rule_based_filter가 생성한 결정인지 추정한다 (decision.py `_rule_decision` 사유 문구 기준)."""
    if decision.confidence == 1.0 and "구간" in decision.reason:
        return "rule_based"
    return settings.CLAUDE_MODEL


async def _record_decision(state: StateSnapshot, decision: Decision) -> None:
    """AI 의사결정 히스토리 영구 저장 (docs/BIN.md "AI 의사결정 히스토리")."""
    await db.insert(
        "decisions",
        {
            "decision_id": decision.decision_id,
            "mode": state.mode,
            "market": state.market,
            "strategy_version": state.strategy_version,
            "prompt_version": state.prompt_version,
            "model_used": _infer_model_used(decision),
            "state_snapshot": asdict(state),
            "decision": {
                "action": decision.action,
                "symbol": decision.symbol,
                "quantity": decision.quantity,
                "reason": decision.reason,
                "confidence": decision.confidence,
            },
        },
    )


async def run_loop(market: Market) -> None:
    """매 15분 실행되는 단일 루프 사이클.

    STEP 1. 시장 캘린더 확인 — 장 마감이면 스킵
    STEP 2. 시장 데이터 수집 (Redis 캐시 우선)
    STEP 3. 규칙 기반 필터 (Claude 호출 없이 처리) — get_decision 내부에서 처리
    STEP 4. StateSnapshot 구성
    STEP 5. Claude API 직접 호출 — get_decision 내부에서 처리
    STEP 6. Safety Gate 검증 — executor.execute 내부에서 처리
    STEP 7. 주문 실행 / 가상 체결 — executor.execute 내부에서 처리
    STEP 8. 결과 기록 (DB·로그·Discord) — executor.execute 내부에서 처리
    """
    from core.toss import market as toss_market

    if settings.EMERGENCY_STOP:
        log.info("loop_skipped_emergency_stop", market=market)
        return
    if market == "KR" and settings.KR_STOP:
        log.info("loop_skipped_kr_stop", market=market)
        return
    if market == "US" and settings.US_STOP:
        log.info("loop_skipped_us_stop", market=market)
        return

    if not await toss_market.is_market_open(market):
        log.info("loop_skipped_market_closed", market=market)
        return

    state = await _build_state_snapshot(market)
    decision = await get_decision(state)
    await _record_decision(state, decision)

    if decision.action != "HOLD":
        mode = RunMode(mode=settings.run_mode, market=market)
        result = await execute(
            decision,
            mode,
            strategy_version=state.strategy_version,
            prompt_version=state.prompt_version,
        )
        log.info(
            "loop_decision_executed",
            market=market,
            action=decision.action,
            symbol=decision.symbol,
            filled=result.filled,
        )

    await publish_status_update()


async def publish_status_update() -> None:
    """#status 채널 고정 Embed 갱신용 이벤트 발행 (docs/DISCORD.md "지속 수정")."""
    live_status = await fund_manager.get_portfolio_status("LIVE") if settings.run_mode == "LIVE" else None
    simulation_status = await fund_manager.get_portfolio_status("SIMULATION")

    # /simstatus의 MDD·샤프 지수 계산용 시계열 스냅샷 (docs/FUND_MANAGER.md).
    # snapshot_at은 db.insert()의 created_at 자동 채움 대상이 아니므로 직접 지정해야 한다
    # (지정하지 않으면 NOT NULL 제약 위반으로 매 루프마다 실패한다).
    await db.insert(
        "simulation_portfolio_snapshots",
        {
            "total_value_krw": simulation_status["totalValueKrw"],
            "cash_krw": simulation_status["cashKrw"],
            "snapshot_at": datetime.now(timezone.utc),
        },
    )

    await publish_event(
        "status_update",
        mode=settings.run_mode,
        market=None,
        payload={"live": live_status, "simulation": simulation_status},
    )


def start_schedulers() -> None:
    """KR·US 루프를 APScheduler에 등록한다 (기동은 core/scheduler/tasks.py가 담당)."""
    from core.scheduler.tasks import scheduler

    scheduler.add_job(
        run_loop, "interval", minutes=15, args=["KR"], id="trading_loop_kr", replace_existing=True
    )
    scheduler.add_job(
        run_loop, "interval", minutes=15, args=["US"], id="trading_loop_us", replace_existing=True
    )
