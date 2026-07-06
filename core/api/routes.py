"""core/api/server.py의 라우트 핸들러. 엔드포인트 스펙은 docs/INTERNAL_API.md 참고."""

from aiohttp import web


async def get_status(request: web.Request) -> web.Response:
    """GET /api/v1/status?market=KR|US -> {live: PortfolioStatus|null, simulation: PortfolioStatus}"""
    raise NotImplementedError


async def get_holdings(request: web.Request) -> web.Response:
    """GET /api/v1/holdings?market=KR|US -> {holdings: Holding[]}"""
    raise NotImplementedError


async def get_orders(request: web.Request) -> web.Response:
    """GET /api/v1/orders -> {orders: Order[]}"""
    raise NotImplementedError


async def post_buy_order(request: web.Request) -> web.Response:
    """POST /api/v1/orders/buy {symbol, quantity, price?} -> {approved, reason?, orderId?, fillPrice?}"""
    raise NotImplementedError


async def post_sell_order(request: web.Request) -> web.Response:
    """POST /api/v1/orders/sell {symbol, quantity, price?} -> {approved, reason?, orderId?, fillPrice?}"""
    raise NotImplementedError


async def cancel_order(request: web.Request) -> web.Response:
    """POST /api/v1/orders/{orderId}/cancel -> {success, reason?}"""
    raise NotImplementedError


async def post_stop(request: web.Request) -> web.Response:
    """POST /api/v1/control/stop {market?} -> {success, emergencyStop, krStop, usStop}"""
    raise NotImplementedError


async def post_resume(request: web.Request) -> web.Response:
    """POST /api/v1/control/resume {} -> {success}"""
    raise NotImplementedError


async def post_simulate(request: web.Request) -> web.Response:
    """POST /api/v1/control/simulate {state: on|off} -> {success, simulation}"""
    raise NotImplementedError


async def post_dryrun(request: web.Request) -> web.Response:
    """POST /api/v1/control/dryrun {state: on|off} -> {success, dryRun}"""
    raise NotImplementedError


async def get_simstatus(request: web.Request) -> web.Response:
    """GET /api/v1/simstatus -> 시뮬레이션 누적 성과 (docs/FUND_MANAGER.md /simstatus 예시와 동일 필드)"""
    raise NotImplementedError


async def post_report_generate(request: web.Request) -> web.Response:
    """POST /api/v1/reports/generate {market?} -> 202 {jobId} (완료 시 report_ready pub/sub 이벤트)"""
    raise NotImplementedError


async def get_fund(request: web.Request) -> web.Response:
    """GET /api/v1/fund -> {operatingFundsKrw, cashBufferKrw, cumulativeReturnPct, positionRatios}"""
    raise NotImplementedError


async def get_fund_apicost(request: web.Request) -> web.Response:
    """GET /api/v1/fund/apicost -> {monthCostKrw, monthCostUsd, callCount}"""
    raise NotImplementedError


async def get_watchlist(request: web.Request) -> web.Response:
    """GET /api/v1/watchlist?market= -> {items: {symbol, market, priority}[]}"""
    raise NotImplementedError


async def post_watchlist(request: web.Request) -> web.Response:
    """POST /api/v1/watchlist {symbol, market} -> {success}"""
    raise NotImplementedError


async def delete_watchlist(request: web.Request) -> web.Response:
    """DELETE /api/v1/watchlist/{symbol} -> {success}"""
    raise NotImplementedError


async def post_backtest(request: web.Request) -> web.Response:
    """POST /api/v1/backtest {strategy, period} -> 202 {jobId} (완료 시 backtest_complete pub/sub 이벤트)"""
    raise NotImplementedError


async def get_health(request: web.Request) -> web.Response:
    """GET /api/v1/health -> Redis `health:latest` 스냅샷을 그대로 반환 (신규 수집 없음)"""
    raise NotImplementedError


async def get_version(request: web.Request) -> web.Response:
    """GET /api/v1/version -> {strategyVersion, promptVersion, deployedAt}"""
    raise NotImplementedError


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
