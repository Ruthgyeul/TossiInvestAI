"""core/api/server.py의 라우트 핸들러. 엔드포인트 스펙은 docs/INTERNAL_API.md 참고."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from aiohttp import web

from core.api.monitor_snapshot import build_monitor_snapshot
from core.config import settings
from core.db import store as db
from core.db.redis import get_redis
from core.events.publisher import publish_event
from core.fund.manager import fund_manager
from core.market_data import indicators
from core.market_data import watchlist as watchlist_store
from core.models import Decision, Market, Mode, RunMode
from core.monitoring.health import HEALTH_REDIS_KEY
from core.report.generator import generate_and_publish
from core.simulation.portfolio import SimulationPortfolio
from core.strategy.backtest import BacktestEngine
from core.strategy.kr.mean_reversion import MeanReversionStrategy
from core.strategy.kr.momentum import MomentumStrategy as KRMomentumStrategy
from core.strategy.us.momentum import MomentumStrategy as USMomentumStrategy
from core.strategy.us.overnight import OvernightStrategy
from core.toss import market as toss_market
from core.toss import order as toss_order
from core.trading.executor import execute

log = structlog.get_logger(__name__)


def _json(data: dict[str, Any], status: int = 200) -> web.Response:
    """모든 응답에 mode 필드를 포함한다 (docs/INTERNAL_API.md "요청/응답 공통 규칙")."""
    return web.json_response({"mode": settings.run_mode, **data}, status=status)


def _current_mode() -> Mode:
    return "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"


def _infer_market(symbol: str) -> Market:
    """숫자 종목코드는 KR, 알파벳 티커는 US (docs/INTERNAL_API.md 참고)."""
    return "KR" if symbol.isdigit() else "US"


async def get_status(request: web.Request) -> web.Response:
    """GET /api/v1/status?market=KR|US -> {live: PortfolioStatus|null, simulation: PortfolioStatus}"""
    market = request.query.get("market")
    live = await fund_manager.get_portfolio_status("LIVE", market) if settings.run_mode == "LIVE" else None
    simulation = await fund_manager.get_portfolio_status("SIMULATION", market)
    return _json({"live": live, "simulation": simulation})


async def get_holdings(request: web.Request) -> web.Response:
    """GET /api/v1/holdings?market=KR|US -> {holdings: Holding[]}"""
    market = request.query.get("market")
    status = await fund_manager.get_portfolio_status(_current_mode(), market)
    return _json({"holdings": status["holdings"]})


async def get_orders(request: web.Request) -> web.Response:
    """GET /api/v1/orders -> {orders: Order[]} (docs/INTERNAL_API.md)."""
    rows = await db.fetch_all("orders", order_by="created_at", descending=True, limit=50)
    orders = [
        {
            "orderId": row["client_order_id"],
            "symbol": row["symbol"],
            "market": row["market"],
            "action": row["action"],
            "quantity": row["quantity"],
            "price": float(row["price"]) if row["price"] is not None else None,
            "status": row["status"],
            "createdAt": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return _json({"orders": orders})


async def _place_manual_order(request: web.Request, action: str) -> web.Response:
    try:
        body = await request.json()
        symbol = str(body["symbol"])
        quantity = int(body["quantity"])
        price = body.get("price")
        price = float(price) if price is not None else None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _json({"approved": False, "reason": "잘못된 요청 형식"}, status=400)

    # amount_krw(price * quantity)가 Safety Gate 5번 조건(1회 주문 금액 상한)의 판단
    # 기준이다 — 0 이하 값은 "amount_krw > MAX_SINGLE_ORDER_KRW"를 항상 통과시켜
    # 한도를 무력화하고, SimulationPortfolio(core/simulation/portfolio.py)의 수량
    # 가감 로직도 음수 입력을 전제하지 않으므로 여기서 먼저 거부한다.
    if quantity <= 0:
        return _json({"approved": False, "reason": "수량은 1 이상이어야 합니다"}, status=400)
    if price is not None and price <= 0:
        return _json({"approved": False, "reason": "가격은 0보다 커야 합니다"}, status=400)

    market = _infer_market(symbol)

    decision = Decision(
        decision_id=str(uuid.uuid4()),
        action=action,  # type: ignore[arg-type]
        symbol=symbol,
        quantity=quantity,
        order_type="LIMIT" if price is not None else "MARKET",
        price=float(price) if price is not None else None,
        confidence=1.0,
        reason="Discord 수동 주문",
        risk_level="LOW",
    )
    result = await execute(decision, RunMode(mode=settings.run_mode, market=market))
    return _json(
        {
            "approved": result.filled,
            "reason": result.reason,
            "orderId": result.order_id,
            "fillPrice": result.fill_price,
        }
    )


async def post_buy_order(request: web.Request) -> web.Response:
    """POST /api/v1/orders/buy {symbol, quantity, price?} -> {approved, reason?, orderId?, fillPrice?}"""
    return await _place_manual_order(request, "BUY")


async def post_sell_order(request: web.Request) -> web.Response:
    """POST /api/v1/orders/sell {symbol, quantity, price?} -> {approved, reason?, orderId?, fillPrice?}"""
    return await _place_manual_order(request, "SELL")


async def cancel_order(request: web.Request) -> web.Response:
    """POST /api/v1/orders/{orderId}/cancel -> {success, reason?}"""
    order_id = request.match_info["orderId"]
    if settings.run_mode != "LIVE":
        return _json({"success": False, "reason": "시뮬레이션/DRY_RUN 모드에는 취소할 실제 주문이 없다"})

    try:
        await toss_order.cancel(order_id)
        return _json({"success": True})
    except Exception as e:  # noqa: BLE001 — 토스 API 오류를 그대로 실패 사유로 전달한다
        return _json({"success": False, "reason": str(e)})


_CONTROL_FLAGS_REDIS_KEY = "control:flags"


async def _persist_control_flags() -> None:
    """EMERGENCY_STOP/KR_STOP/US_STOP을 DB + Redis에 즉시 반영한다 (docs/SAFETY.md "긴급 정지").

    프로세스가 재시작돼도(systemd 자동 재시작 등) core/main.py가 부팅 시 DB에서
    복원하므로 긴급 정지 상태가 소리 없이 풀리지 않는다.
    """
    await db.set_control_flags(
        emergency_stop=settings.EMERGENCY_STOP,
        kr_stop=settings.KR_STOP,
        us_stop=settings.US_STOP,
    )
    redis = get_redis()
    await redis.set(
        _CONTROL_FLAGS_REDIS_KEY,
        json.dumps(
            {
                "emergencyStop": settings.EMERGENCY_STOP,
                "krStop": settings.KR_STOP,
                "usStop": settings.US_STOP,
            }
        ),
    )


async def _cancel_open_orders(market: str | None) -> list[dict]:
    """긴급 정지 시 미체결 주문 취소를 시도한다 (docs/SAFETY.md "실전: 모든 미체결 주문 취소 시도").

    SIMULATION/DRY_RUN은 executor가 주문을 동기적으로 즉시 체결시켜 대기 상태로
    남는 가상 주문이 존재하지 않으므로(core/trading/executor.py `_execute_simulation`)
    취소 대상이 없다 — LIVE에서만 실제 취소를 시도한다.
    """
    if settings.run_mode != "LIVE":
        return []

    markets = [market] if market in ("KR", "US") else ["KR", "US"]
    try:
        pending = await toss_order.get_orders(status="PENDING")
    except Exception as e:  # noqa: BLE001 — 조회 실패는 취소 시도를 막지 않고 빈 목록으로 진행
        log.warning("cancel_open_orders_fetch_failed", error=str(e))
        return []

    cancelled: list[dict] = []
    for o in pending:
        if o.get("market") not in markets:
            continue
        order_id = o.get("orderId")
        if order_id is None:
            continue
        try:
            await toss_order.cancel(order_id)
            cancelled.append({"orderId": order_id, "symbol": o.get("symbol")})
        except Exception as e:  # noqa: BLE001 — 개별 취소 실패는 나머지 주문 취소를 막지 않는다
            log.warning("cancel_open_order_failed", order_id=order_id, error=str(e))
    return cancelled


async def post_stop(request: web.Request) -> web.Response:
    """POST /api/v1/control/stop {market?} -> {success, emergencyStop, krStop, usStop, cancelledOrders}"""
    body = await request.json() if request.can_read_body else {}
    market = body.get("market")

    if market == "KR":
        settings.KR_STOP = True
    elif market == "US":
        settings.US_STOP = True
    else:
        settings.EMERGENCY_STOP = True

    await _persist_control_flags()
    cancelled_orders = await _cancel_open_orders(market)

    await publish_event(
        "emergency_stop",
        mode=settings.run_mode,
        market=market,
        payload={
            "emergencyStop": settings.EMERGENCY_STOP,
            "krStop": settings.KR_STOP,
            "usStop": settings.US_STOP,
            "cancelledOrders": cancelled_orders,
        },
    )
    return _json(
        {
            "success": True,
            "emergencyStop": settings.EMERGENCY_STOP,
            "krStop": settings.KR_STOP,
            "usStop": settings.US_STOP,
            "cancelledOrders": cancelled_orders,
        }
    )


async def post_resume(request: web.Request) -> web.Response:
    """POST /api/v1/control/resume {} -> {success}"""
    settings.EMERGENCY_STOP = False
    settings.KR_STOP = False
    settings.US_STOP = False
    await _persist_control_flags()
    return _json({"success": True})


_MIN_SIMULATION_DAYS = 14


async def post_simulate(request: web.Request) -> web.Response:
    """POST /api/v1/control/simulate {state: on|off} -> {success, simulation, reason?}

    off(=LIVE 전환)는 docs/SAFETY.md·CLAUDE.md 절대 규칙 11 "실전 전환 전 SIMULATION 모드
    최소 2주 이상 필수"를 만족해야 한다 — 미달 시 거부하고 SIMULATION 상태를 유지한다.
    """
    body = await request.json()
    turn_on = body["state"] == "on"

    if turn_on:
        if not settings.SIMULATION:
            await db.set_simulation_started_at(datetime.now(UTC))
        settings.SIMULATION = True
        return _json({"success": True, "simulation": True})

    if settings.SIMULATION:
        started_at = await db.get_simulation_started_at()
        elapsed_days = (
            (datetime.now(UTC) - started_at).total_seconds() / 86400
            if started_at is not None
            else 0.0
        )
        if elapsed_days < _MIN_SIMULATION_DAYS:
            return _json(
                {
                    "success": False,
                    "simulation": True,
                    "reason": (
                        f"SIMULATION 최소 {_MIN_SIMULATION_DAYS}일 필요 "
                        f"(현재 {elapsed_days:.1f}일 경과)"
                    ),
                }
            )

    settings.SIMULATION = False
    return _json({"success": True, "simulation": False})


async def post_dryrun(request: web.Request) -> web.Response:
    """POST /api/v1/control/dryrun {state: on|off} -> {success, dryRun}"""
    body = await request.json()
    settings.DRY_RUN = body["state"] == "on"
    return _json({"success": True, "dryRun": settings.DRY_RUN})


def _average_holding_days(trades: list[dict]) -> float:
    """docs/FUND_MANAGER.md `/simstatus` 예시 "평균 보유 2.3일" — 계산은
    core/market_data/indicators.py로 이전해 core/report/generator.py 주간 리포트와 공유한다."""
    return indicators.calculate_avg_holding_days(trades)


async def get_simstatus(request: web.Request) -> web.Response:
    """GET /api/v1/simstatus -> 시뮬레이션 누적 성과 (docs/FUND_MANAGER.md `/simstatus` 예시와 동일 필드)."""
    trades = await db.fetch_all("simulation_trades")
    sells = [t for t in trades if t["action"] == "SELL"]
    win_count = sum(1 for t in sells if (t["pnl_krw"] or 0) > 0)

    snapshots = await db.fetch_all("simulation_portfolio_snapshots", order_by="snapshot_at")
    values = [float(s["total_value_krw"]) for s in snapshots]

    portfolio = await SimulationPortfolio.load()
    current_prices = {
        symbol: (await toss_market.get_price(symbol))["price"] for symbol in portfolio.positions
    }
    total_value = portfolio.get_total_value(current_prices)
    rejections = await db.fetch_all("safety_rejections", {"mode": "SIMULATION"})
    api_usage = await db.get_api_usage_month_summary()

    return _json(
        {
            "startedAt": snapshots[0]["snapshot_at"].isoformat() if snapshots else None,
            "seedKrw": settings.INITIAL_SEED_KRW,
            "totalValueKrw": int(total_value),
            "cumulativeReturnPct": portfolio.get_return_rate(current_prices),
            "mdd": indicators.calculate_max_drawdown_pct(values),
            "sharpeRatio": indicators.calculate_sharpe_ratio(values),
            "tradeCount": len(trades),
            "winRate": win_count / len(sells) if sells else 0.0,
            "avgHoldingDays": _average_holding_days(trades),
            "rejectionCount": len(rejections),
            "apiCostKrw": api_usage["cost_krw"],
            "apiCallCount": api_usage["call_count"],
        }
    )


async def post_report_generate(request: web.Request) -> web.Response:
    """POST /api/v1/reports/generate {market?} -> 202 {jobId} (완료 시 report_ready pub/sub 이벤트)"""
    body = await request.json() if request.can_read_body else {}
    market = body.get("market", "ALL")
    job_id = str(uuid.uuid4())

    asyncio.create_task(generate_and_publish(market, "on_demand", correlation_id=job_id))
    return _json({"jobId": job_id}, status=202)


async def get_fund(request: web.Request) -> web.Response:
    """GET /api/v1/fund -> {operatingFundsKrw, cashBufferKrw, cumulativeReturnPct, positionRatios}"""
    status = await fund_manager.get_portfolio_status(_current_mode())
    operating_funds = await fund_manager.get_operating_funds_krw(_current_mode())

    position_ratios = [
        {
            "symbol": h["symbol"],
            "ratio": (h["quantity"] * h["currentPrice"]) / operating_funds if operating_funds else 0.0,
        }
        for h in status["holdings"]
    ]

    return _json(
        {
            "operatingFundsKrw": int(operating_funds),
            "cashBufferKrw": status["cashBufferKrw"],
            "cumulativeReturnPct": status["cumulativePnlPct"],
            "positionRatios": position_ratios,
        }
    )


async def get_fund_apicost(request: web.Request) -> web.Response:
    """GET /api/v1/fund/apicost -> {monthCostKrw, monthCostUsd, callCount}"""
    summary = await db.get_api_usage_month_summary()
    return _json(
        {
            "monthCostKrw": summary["cost_krw"],
            "monthCostUsd": round(summary["cost_usd"], 2),
            "callCount": summary["call_count"],
        }
    )


async def get_watchlist(request: web.Request) -> web.Response:
    """GET /api/v1/watchlist?market= -> {items: {symbol, market, priority}[]}"""
    market = request.query.get("market")
    items = await watchlist_store.get_watchlist(market)
    return _json(
        {
            "items": [
                {"symbol": i["symbol"], "market": i["market"], "priority": i["priority"]}
                for i in items
            ]
        }
    )


async def post_watchlist(request: web.Request) -> web.Response:
    """POST /api/v1/watchlist {symbol, market} -> {success}"""
    body = await request.json()
    await watchlist_store.add_symbol(body["symbol"], body["market"])
    return _json({"success": True})


async def delete_watchlist(request: web.Request) -> web.Response:
    """DELETE /api/v1/watchlist/{symbol} -> {success}"""
    await watchlist_store.remove_symbol(request.match_info["symbol"])
    return _json({"success": True})


_BACKTEST_STRATEGIES: dict[str, tuple[Any, Market]] = {
    "kr_mean_reversion": (MeanReversionStrategy(), "KR"),
    "kr_momentum": (KRMomentumStrategy(), "KR"),
    "us_momentum": (USMomentumStrategy(), "US"),
    "us_overnight": (OvernightStrategy(), "US"),
}

_BACKTEST_INITIAL_CAPITAL_KRW = 500_000


async def post_backtest(request: web.Request) -> web.Response:
    """POST /api/v1/backtest {strategy, period} -> 202 {jobId} (완료 시 backtest_complete 이벤트).

    `strategy`는 `_BACKTEST_STRATEGIES`에 등록된 이름(kr_mean_reversion·kr_momentum·
    us_momentum·us_overnight) 중 하나여야 한다.
    """
    body = await request.json()
    strategy_name = body["strategy"]
    period = body["period"]
    job_id = str(uuid.uuid4())

    entry = _BACKTEST_STRATEGIES.get(strategy_name)

    async def _run() -> None:
        if entry is None:
            await publish_event(
                "backtest_complete",
                mode=settings.run_mode,
                market=None,
                correlation_id=job_id,
                payload={
                    "error": (
                        f"알 수 없는 전략: {strategy_name} "
                        f"(사용 가능: {', '.join(_BACKTEST_STRATEGIES)})"
                    )
                },
            )
            return

        strategy, market = entry
        result = await BacktestEngine.run(
            strategy=strategy,
            market=market,
            period=period,
            initial_capital=_BACKTEST_INITIAL_CAPITAL_KRW,
        )
        await publish_event(
            "backtest_complete",
            mode=settings.run_mode,
            market=market,
            correlation_id=job_id,
            payload={
                "winRate": result.win_rate,
                "avgReturn": result.avg_return,
                "mdd": result.mdd,
                "sharpeRatio": result.sharpe_ratio,
                "profitFactor": result.profit_factor,
            },
        )

    asyncio.create_task(_run())
    return _json({"jobId": job_id}, status=202)


async def get_health(request: web.Request) -> web.Response:
    """GET /api/v1/health -> Redis `health:latest` 스냅샷을 그대로 반환 (신규 수집 없음)"""
    redis = get_redis()
    cached = await redis.get(HEALTH_REDIS_KEY)
    if cached is None:
        return _json(
            {
                "cpuPct": 0.0,
                "memoryPct": 0.0,
                "diskPct": 0.0,
                "tempC": 0.0,
                "tossApiReachable": False,
                "collectedAt": None,
            }
        )

    snapshot = json.loads(cached)
    return _json(
        {
            "cpuPct": snapshot["cpu_pct"],
            "memoryPct": snapshot["memory_pct"],
            "diskPct": snapshot["disk_pct"],
            "tempC": snapshot["temp_c"],
            "tossApiReachable": snapshot["toss_api_reachable"],
            # .get(): 배포 직후 아직 갱신되지 않은 이전 포맷 캐시(collected_at 없음)와도
            # 호환되도록 — 다음 5분 헬스체크 사이클이 지나면 자연히 채워진다.
            "collectedAt": snapshot.get("collected_at"),
        }
    )


async def get_monitor_snapshot(request: web.Request) -> web.Response:
    """GET /api/v1/monitor/snapshot -> monitor/(Next.js 키오스크) 대시보드 전용 집계
    (docs/MONITOR.md "데이터 흐름"). 여러 엔드포인트를 조합하지 않고 이 하나로 화면 전체를 채운다."""
    return _json(await build_monitor_snapshot())


async def get_version(request: web.Request) -> web.Response:
    """GET /api/v1/version -> {strategyVersion, promptVersion, deployedAt}

    docs/SELF_IMPROVEMENT.md "approved_by가 비어 있는 레코드는 미승인 상태로 간주한다" —
    승인·배포된(approved_by가 채워진) 레코드만 "현재 버전"으로 취급한다.
    """
    row = await db.get_latest_deployed_strategy_version()
    if row is None:
        return _json({"strategyVersion": "v1.0.0", "promptVersion": "system_kr_v1", "deployedAt": None})

    return _json(
        {
            "strategyVersion": row["strategy_version"],
            "promptVersion": row["prompt_version"],
            "deployedAt": row["deployed_at"].isoformat(),
        }
    )


def _candidate_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "market": row["market"],
        "strategyVersion": row["strategy_version"],
        "promptVersion": row["prompt_version"],
        "basedOn": row["based_on"],
        "changeSummary": row["change_summary"],
        "backtestResult": row["backtest_result"],
        "proposedAt": row["proposed_at"].isoformat(),
    }


async def get_version_candidates(request: web.Request) -> web.Response:
    """GET /api/v1/version/candidates -> {candidates: VersionCandidate[]} — 승인 대기 후보 목록."""
    rows = await db.get_pending_strategy_candidates()
    return _json({"candidates": [_candidate_json(row) for row in rows]})


async def post_version_approve(request: web.Request) -> web.Response:
    """POST /api/v1/version/{id}/approve {approvedBy} -> {success, reason?}

    후보를 승인·배포 상태로 전환한다(docs/SELF_IMPROVEMENT.md "개발자 승인").
    """
    version_id = int(request.match_info["id"])
    body = await request.json()
    approved_by = body["approvedBy"]

    row = await db.approve_strategy_version(version_id, approved_by)
    if row is None:
        return _json({"success": False, "reason": "후보를 찾을 수 없습니다"})
    return _json({"success": True})


async def post_version_reject(request: web.Request) -> web.Response:
    """POST /api/v1/version/{id}/reject -> {success, reason?} — 승인 대기 후보를 폐기한다."""
    version_id = int(request.match_info["id"])

    row = await db.fetch_one("strategy_versions", {"id": version_id})
    if row is None:
        return _json({"success": False, "reason": "후보를 찾을 수 없습니다"})
    if row["approved_by"] is not None:
        return _json({"success": False, "reason": "이미 승인·배포된 버전은 반려할 수 없습니다"})

    await db.delete("strategy_versions", {"id": version_id})
    return _json({"success": True})


async def post_version_rollback(request: web.Request) -> web.Response:
    """POST /api/v1/version/rollback {strategyVersion, approvedBy} -> {success, reason?}

    과거에 승인·배포된 이력이 있는 버전으로 즉시 되돌린다(docs/SELF_IMPROVEMENT.md "버전 관리
    및 롤백") — 기존 이력을 지우지 않고, 그 버전을 새 배포로 다시 기록해 감사 추적을 유지한다.
    """
    body = await request.json()
    target_version = body["strategyVersion"]
    approved_by = body["approvedBy"]

    target = await db.get_deployed_strategy_version_by_name(target_version)
    if target is None:
        return _json({"success": False, "reason": f"배포 이력이 없는 버전입니다: {target_version}"})

    current = await db.get_latest_deployed_strategy_version(target["market"])
    await db.insert(
        "strategy_versions",
        {
            "market": target["market"],
            "strategy_version": target["strategy_version"],
            "prompt_version": target["prompt_version"],
            "based_on": current["strategy_version"] if current else None,
            "change_summary": f"롤백: {target['strategy_version']}로 복귀",
            "backtest_result": target["backtest_result"],
            "approved_by": approved_by,
            "proposed_at": datetime.now(UTC),
            "deployed_at": datetime.now(UTC),
        },
    )
    return _json({"success": True})


def register_routes(app: web.Application) -> None:
    app.add_routes(
        [
            web.get("/api/v1/status", get_status),
            web.get("/api/v1/holdings", get_holdings),
            web.get("/api/v1/orders", get_orders),
            web.post("/api/v1/orders/buy", post_buy_order),
            web.post("/api/v1/orders/sell", post_sell_order),
            web.post("/api/v1/orders/{orderId}/cancel", cancel_order),
            web.post("/api/v1/control/stop", post_stop),
            web.post("/api/v1/control/resume", post_resume),
            web.post("/api/v1/control/simulate", post_simulate),
            web.post("/api/v1/control/dryrun", post_dryrun),
            web.get("/api/v1/simstatus", get_simstatus),
            web.post("/api/v1/reports/generate", post_report_generate),
            web.get("/api/v1/fund", get_fund),
            web.get("/api/v1/fund/apicost", get_fund_apicost),
            web.get("/api/v1/watchlist", get_watchlist),
            web.post("/api/v1/watchlist", post_watchlist),
            web.delete("/api/v1/watchlist/{symbol}", delete_watchlist),
            web.post("/api/v1/backtest", post_backtest),
            web.get("/api/v1/health", get_health),
            web.get("/api/v1/monitor/snapshot", get_monitor_snapshot),
            web.get("/api/v1/version", get_version),
            web.get("/api/v1/version/candidates", get_version_candidates),
            web.post("/api/v1/version/{id}/approve", post_version_approve),
            web.post("/api/v1/version/{id}/reject", post_version_reject),
            web.post("/api/v1/version/rollback", post_version_rollback),
        ]
    )
