"""core/api/server.py의 라우트 핸들러. 엔드포인트 스펙은 docs/INTERNAL_API.md 참고."""

import asyncio
import json
import statistics
import uuid
from typing import Any

import structlog
from aiohttp import web

from core.config import settings
from core.db import store as db
from core.db.redis import get_redis
from core.events.publisher import publish_event
from core.fund.manager import fund_manager
from core.market_data import watchlist as watchlist_store
from core.models import Decision, Market, Mode, RunMode
from core.monitoring.health import HEALTH_REDIS_KEY
from core.report.generator import generate_and_publish
from core.simulation.portfolio import SimulationPortfolio
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
    """GET /api/v1/orders -> {orders: Order[]}"""
    rows = await db.fetch_all("orders", order_by="created_at", descending=True, limit=50)
    orders = [
        {
            "orderId": row["client_order_id"],
            "symbol": row["symbol"],
            "market": row["market"],
            "status": row["status"],
            "createdAt": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return _json({"orders": orders})


async def _place_manual_order(request: web.Request, action: str) -> web.Response:
    body = await request.json()
    symbol = body["symbol"]
    quantity = int(body["quantity"])
    price = body.get("price")
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


async def post_stop(request: web.Request) -> web.Response:
    """POST /api/v1/control/stop {market?} -> {success, emergencyStop, krStop, usStop}"""
    body = await request.json() if request.can_read_body else {}
    market = body.get("market")

    if market == "KR":
        settings.KR_STOP = True
    elif market == "US":
        settings.US_STOP = True
    else:
        settings.EMERGENCY_STOP = True

    await publish_event(
        "emergency_stop",
        mode=settings.run_mode,
        market=market,
        payload={
            "emergencyStop": settings.EMERGENCY_STOP,
            "krStop": settings.KR_STOP,
            "usStop": settings.US_STOP,
        },
    )
    return _json(
        {
            "success": True,
            "emergencyStop": settings.EMERGENCY_STOP,
            "krStop": settings.KR_STOP,
            "usStop": settings.US_STOP,
        }
    )


async def post_resume(request: web.Request) -> web.Response:
    """POST /api/v1/control/resume {} -> {success}"""
    settings.EMERGENCY_STOP = False
    settings.KR_STOP = False
    settings.US_STOP = False
    return _json({"success": True})


async def post_simulate(request: web.Request) -> web.Response:
    """POST /api/v1/control/simulate {state: on|off} -> {success, simulation}"""
    body = await request.json()
    settings.SIMULATION = body["state"] == "on"
    return _json({"success": True, "simulation": settings.SIMULATION})


async def post_dryrun(request: web.Request) -> web.Response:
    """POST /api/v1/control/dryrun {state: on|off} -> {success, dryRun}"""
    body = await request.json()
    settings.DRY_RUN = body["state"] == "on"
    return _json({"success": True, "dryRun": settings.DRY_RUN})


def _max_drawdown_pct(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value - peak) / peak)
    return max_dd


def _sharpe_ratio(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    returns = [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]
    if len(returns) < 2:
        return 0.0
    stdev = statistics.pstdev(returns)
    if stdev == 0:
        return 0.0
    return statistics.mean(returns) / stdev * (252 ** 0.5)


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
            "mdd": _max_drawdown_pct(values),
            "sharpeRatio": _sharpe_ratio(values),
            "tradeCount": len(trades),
            "winRate": win_count / len(sells) if sells else 0.0,
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
    operating_funds = await fund_manager.get_operating_funds_krw()

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


async def post_backtest(request: web.Request) -> web.Response:
    """POST /api/v1/backtest {strategy, period} -> 202 {jobId} (완료 시 backtest_complete 이벤트)

    strategy/backtest.py의 실제 엔진은 Phase 5에서 구현한다(tests/test_backtest.py 참고) —
    지금은 접수만 하고 미구현 상태임을 backtest_complete 이벤트로 알린다.
    """
    job_id = str(uuid.uuid4())

    async def _not_yet_available() -> None:
        await publish_event(
            "backtest_complete",
            mode=settings.run_mode,
            market=None,
            correlation_id=job_id,
            payload={"error": "백테스트 엔진은 아직 구현되지 않았습니다 (Phase 5 예정)"},
        )

    asyncio.create_task(_not_yet_available())
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
        }
    )


async def get_version(request: web.Request) -> web.Response:
    """GET /api/v1/version -> {strategyVersion, promptVersion, deployedAt}"""
    rows = await db.fetch_all(
        "strategy_versions", order_by="deployed_at", descending=True, limit=1
    )
    if not rows:
        return _json({"strategyVersion": "v1.0.0", "promptVersion": "system_kr_v1", "deployedAt": None})

    row = rows[0]
    return _json(
        {
            "strategyVersion": row["strategy_version"],
            "promptVersion": row["prompt_version"],
            "deployedAt": row["deployed_at"].isoformat(),
        }
    )


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
            web.get("/api/v1/version", get_version),
        ]
    )
