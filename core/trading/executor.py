"""LIVE/SIMULATION 분기 주문 실행 (docs/BIN.md, docs/SAFETY.md)."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

from core.db import store as db
from core.events.publisher import publish_event
from core.models import Decision, Order, OrderResult, RunMode
from core.safety.gate import safety_gate
from core.simulation.portfolio import SimulationPortfolio
from core.toss import account as toss_account
from core.toss import market as toss_market
from core.toss import order as toss_order

log = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_TRADING_LOG_DIR = Path("logs/trading")
_ERROR_LOG_DIR = Path("logs/errors")

# SIMULATION 모드는 KR·US가 하나의 가상 자금 풀을 공유한다 (docs/FUND_MANAGER.md).
_simulation_portfolio: SimulationPortfolio | None = None


async def _get_simulation_portfolio() -> SimulationPortfolio:
    global _simulation_portfolio
    if _simulation_portfolio is None:
        _simulation_portfolio = await SimulationPortfolio.load()
    return _simulation_portfolio


def _append_log(directory: Path, block: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    filename = directory / f"{datetime.now(_KST):%Y-%m-%d}.log"
    with filename.open("a", encoding="utf-8") as f:
        f.write(block + "\n")


def _log_prefix(mode: RunMode) -> str:
    return "LIVE" if mode.mode == "LIVE" else "SIM"


def _append_trade_log(decision: Decision, order: Order, mode: RunMode, fill_price: float) -> None:
    now = datetime.now(_KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    block = (
        "=" * 80 + "\n"
        f"[{_log_prefix(mode)}][거래] {now}\n" + "-" * 80 + "\n"
        f"심볼            {order.symbol}\n"
        f"시장            {order.market}\n"
        f"매수/매도       {order.action}\n"
        f"수량            {order.quantity}주\n"
        f"체결가          {fill_price:,}\n"
        f"판단 사유       {decision.reason}\n"
        f"Decision ID     {decision.decision_id}\n"
        f"Order ID        {order.client_order_id}\n" + "=" * 80
    )
    _append_log(_TRADING_LOG_DIR, block)


def _append_rejection_log(order: Order, mode: RunMode, reason: str) -> None:
    now = datetime.now(_KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    block = (
        "=" * 80 + "\n"
        f"[{_log_prefix(mode)}][에러] {now}  SAFETY_GATE_REJECTION\n" + "-" * 80 + "\n"
        f"종목           {order.symbol}\n"
        f"시도 행위      {order.action} {order.quantity}주 ({order.amount_krw:,} KRW)\n"
        f"거부 사유      {reason}\n" + "=" * 80
    )
    _append_log(_ERROR_LOG_DIR, block)


async def _handle_rejection(order: Order, mode: RunMode, reason: str) -> None:
    _append_rejection_log(order, mode, reason)
    await db.insert(
        "safety_rejections",
        {
            "symbol": order.symbol,
            "market": order.market,
            "reason": reason,
            "mode": mode.mode,
        },
    )
    await publish_event(
        "safety_rejection",
        mode=mode.mode,
        market=order.market,
        payload={"symbol": order.symbol, "action": order.action, "reason": reason},
    )


async def _commission_krw(market: str, amount_krw: float) -> int:
    commission = await toss_account.get_commissions(market)
    rate = float(commission.get("rate", 0.0))
    return round(amount_krw * rate)


async def _execute_live(decision: Decision, order: Order, mode: RunMode) -> OrderResult:
    response = await toss_order.place(order)
    fill_price = float(response.get("fillPrice", order.price or 0))
    result = OrderResult(filled=True, order_id=response.get("orderId"), fill_price=fill_price)

    commission = await _commission_krw(order.market, fill_price * order.quantity)
    await db.insert(
        "trades",
        {
            "symbol": order.symbol,
            "market": order.market,
            "action": order.action,
            "quantity": order.quantity,
            "fill_price": fill_price,
            "commission_krw": commission,
            "decision_id": decision.decision_id,
            "order_id": result.order_id,
        },
    )
    _append_trade_log(decision, order, mode, fill_price)
    await publish_event(
        "trade_executed",
        mode=mode.mode,
        market=order.market,
        payload={
            "symbol": order.symbol,
            "action": order.action,
            "quantity": order.quantity,
            "fillPrice": fill_price,
            "commissionKrw": commission,
            "reason": decision.reason,
            "decisionId": decision.decision_id,
            "orderId": result.order_id,
        },
    )
    return result


async def _execute_simulation(decision: Decision, order: Order, mode: RunMode) -> OrderResult:
    fill_price = order.price or (await toss_market.get_price(order.symbol))["price"]
    commission = await _commission_krw(order.market, fill_price * order.quantity)
    portfolio = await _get_simulation_portfolio()
    order_id = f"SIM-{datetime.now(_KST):%Y%m%d}-{order.market}-{toss_order.generate_client_order_id(order.market)[-6:]}"

    if order.action == "BUY":
        await portfolio.apply_buy(order.symbol, order.quantity, fill_price, commission, order.market)
        pnl_krw = None
    else:
        pnl_krw = await portfolio.apply_sell(order.symbol, order.quantity, fill_price, commission)

    result = OrderResult(filled=True, order_id=order_id, fill_price=fill_price)

    if mode.mode != "DRY_RUN":
        await db.insert(
            "simulation_trades",
            {
                "symbol": order.symbol,
                "market": order.market,
                "action": order.action,
                "quantity": order.quantity,
                "fill_price": fill_price,
                "commission_krw": commission,
                "pnl_krw": pnl_krw,
            },
        )
        _append_trade_log(decision, order, mode, fill_price)

    await publish_event(
        "trade_executed",
        mode=mode.mode,
        market=order.market,
        payload={
            "symbol": order.symbol,
            "action": order.action,
            "quantity": order.quantity,
            "fillPrice": fill_price,
            "commissionKrw": commission,
            "pnlKrw": pnl_krw,
            "reason": decision.reason,
            "decisionId": decision.decision_id,
            "orderId": order_id,
        },
    )
    return result


async def execute(decision: Decision, mode: RunMode) -> OrderResult:
    """Safety Gate 통과 후 모드에 따라 실제 주문 또는 가상 체결을 수행한다.

    체결·거부 결과는 Redis `pubsub:events`로 발행해 discord-bot이 구독한다
    (docs/INTERNAL_API.md의 `trade_executed`/`safety_rejection` 이벤트).
    """
    if decision.action == "HOLD":
        return OrderResult(filled=False, reason="HOLD — 주문 없음")

    client_order_id = toss_order.generate_client_order_id(mode.market)
    reference_price = decision.price
    if reference_price is None:
        price_data = await toss_market.get_price(decision.symbol)
        reference_price = price_data["price"]

    order = decision.to_order(mode.market, client_order_id, reference_price=reference_price)

    gate_result = await safety_gate.check(order, mode)
    if not gate_result.approved:
        reason = gate_result.reason or "알 수 없는 사유"
        await _handle_rejection(order, mode, reason)
        return OrderResult.rejected(reason)

    if mode.mode == "LIVE":
        return await _execute_live(decision, order, mode)
    return await _execute_simulation(decision, order, mode)
