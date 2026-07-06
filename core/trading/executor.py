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


def _append_trade_log(
    decision: Decision,
    order: Order,
    mode: RunMode,
    fill_price: float,
    *,
    order_id: str,
    commission_krw: int,
    realized_pnl_krw: float | None,
    balance_change_krw: float | None,
    strategy_version: str,
    prompt_version: str,
) -> None:
    """docs/LOGGING.md "거래 로그 형식" — LIVE/SIMULATION 필드 구성이 다르다."""
    now = datetime.now(_KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    is_live = mode.mode == "LIVE"
    action_kr = "매수" if order.action == "BUY" else "매도"
    virtual_tag = "" if is_live else " [가상 체결]"

    order_price = f"{order.price:,.0f}원 (지정가)" if order.price is not None else "시장가"

    if order.action == "BUY":
        pnl_str = "해당 없음 (신규 매수)"
    elif realized_pnl_krw is not None:
        pnl_str = f"{realized_pnl_krw:+,} KRW"
    else:
        pnl_str = "해당 없음"

    lines = [
        "=" * 80,
        f"[{_log_prefix(mode)}][거래] {now}",
        "-" * 80,
        f"종목명          {order.symbol}",
        f"심볼            {order.symbol}",
        f"시장            {order.market}",
        f"매수/매도       {action_kr} ({order.action}){virtual_tag}",
        f"수량            {order.quantity}주",
        f"주문 가격       {order_price}",
        f"{'체결 평균단가' if is_live else '가상 체결단가  '}   {fill_price:,.0f}원",
        f"수수료          {commission_krw:,}원",
        f"실현 손익       {pnl_str}",
    ]
    if not is_live and balance_change_krw is not None:
        lines.append(f"가상 잔고 변화  {balance_change_krw:+,.0f}원")
    lines += [
        f"주문 사유       {decision.reason}",
        f"Claude Decision ID  {decision.decision_id}",
        f"Toss Order ID       {order_id}",
        f"전략 버전       {strategy_version}",
        f"프롬프트 버전   {prompt_version}",
        "=" * 80,
    ]
    _append_log(_TRADING_LOG_DIR, "\n".join(lines))


def _append_rejection_log(order: Order, mode: RunMode, reason: str) -> None:
    """docs/LOGGING.md "에러 로그 형식" — 실전/시뮬레이션 모두 조치(취소·알림 발송)를 명시한다."""
    now = datetime.now(_KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    is_live = mode.mode == "LIVE"
    virtual_tag = "" if is_live else " [가상]"
    action_taken = (
        "주문 취소, Discord #stock-error 알림 발송"
        if is_live
        else "가상 주문 취소, Discord #stock-error 알림 발송 [시뮬레이션]"
    )
    block = (
        "=" * 80 + "\n"
        f"[{_log_prefix(mode)}][에러] {now}  SAFETY_GATE_REJECTION\n" + "-" * 80 + "\n"
        f"종목           {order.symbol}\n"
        f"시도 행위      {order.action} {order.quantity}주 ({order.amount_krw:,} KRW){virtual_tag}\n"
        f"거부 사유      {reason}\n"
        f"조치           {action_taken}\n" + "=" * 80
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


async def _execute_live(
    decision: Decision, order: Order, mode: RunMode, *, strategy_version: str, prompt_version: str
) -> OrderResult:
    response = await toss_order.place(order)
    fill_price = float(response.get("fillPrice", order.price or 0))
    result = OrderResult(filled=True, order_id=response.get("orderId"), fill_price=fill_price)

    # GET /api/v1/orders(docs/INTERNAL_API.md)가 조회하는 주문 이력 — Safety Gate를 통과해
    # 실제로 접수된 주문만 기록한다 (거부된 주문은 _handle_rejection이 별도로 처리).
    await db.insert(
        "orders",
        {
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "market": order.market,
            "action": order.action,
            "quantity": order.quantity,
            "price": order.price,
            "status": "FILLED" if result.filled else "PENDING",
        },
    )

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
    # LIVE 실현 손익은 포지션 평균단가 추적이 아직 없어 계산할 수 없다 — None으로 남긴다.
    _append_trade_log(
        decision,
        order,
        mode,
        fill_price,
        order_id=result.order_id or "-",
        commission_krw=commission,
        realized_pnl_krw=None,
        balance_change_krw=None,
        strategy_version=strategy_version,
        prompt_version=prompt_version,
    )
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


async def _execute_simulation(
    decision: Decision, order: Order, mode: RunMode, *, strategy_version: str, prompt_version: str
) -> OrderResult:
    """SIMULATION은 가상 포트폴리오에 영구 반영한다. DRY_RUN은 개발용 최소 테스트이므로
    docs/SAFETY.md "DB 기록 최소화 (영구 보존 데이터 생성 안 함)"에 따라 가상 포트폴리오·DB·
    거래 로그 어디에도 흔적을 남기지 않고 체결가만 계산해 반환한다 — SIMULATION 리허설의
    `simulation_positions` 상태를 DRY_RUN 테스트 실행이 오염시키지 않도록 한다.
    """
    fill_price = order.price or (await toss_market.get_price(order.symbol))["price"]
    commission = await _commission_krw(order.market, fill_price * order.quantity)
    prefix = "DRY" if mode.mode == "DRY_RUN" else "SIM"
    order_id = f"{prefix}-{datetime.now(_KST):%Y%m%d}-{order.market}-{toss_order.generate_client_order_id(order.market)[-6:]}"

    notional = fill_price * order.quantity
    if mode.mode == "DRY_RUN":
        pnl_krw = None
        balance_change_krw = -(notional + commission) if order.action == "BUY" else notional - commission
        result = OrderResult(filled=True, order_id=order_id, fill_price=fill_price)
    else:
        portfolio = await _get_simulation_portfolio()
        if order.action == "BUY":
            await portfolio.apply_buy(order.symbol, order.quantity, fill_price, commission, order.market)
            pnl_krw = None
            balance_change_krw = -(notional + commission)
        else:
            pnl_krw = await portfolio.apply_sell(order.symbol, order.quantity, fill_price, commission)
            balance_change_krw = notional - commission

        result = OrderResult(filled=True, order_id=order_id, fill_price=fill_price)

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
        _append_trade_log(
            decision,
            order,
            mode,
            fill_price,
            order_id=order_id,
            commission_krw=commission,
            realized_pnl_krw=pnl_krw,
            balance_change_krw=balance_change_krw,
            strategy_version=strategy_version,
            prompt_version=prompt_version,
        )

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


async def execute(
    decision: Decision,
    mode: RunMode,
    *,
    strategy_version: str = "manual",
    prompt_version: str = "manual",
) -> OrderResult:
    """Safety Gate 통과 후 모드에 따라 실제 주문 또는 가상 체결을 수행한다.

    체결·거부 결과는 Redis `pubsub:events`로 발행해 discord-bot이 구독한다
    (docs/INTERNAL_API.md의 `trade_executed`/`safety_rejection` 이벤트).

    strategy_version/prompt_version은 AI 결정 루프(core/trading/loop.py)가 StateSnapshot에서
    전달한다 — Discord `/buy`·`/sell` 수동 주문처럼 AI 결정을 거치지 않은 경우 "manual"을 사용한다.
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
        return await _execute_live(
            decision, order, mode, strategy_version=strategy_version, prompt_version=prompt_version
        )
    return await _execute_simulation(
        decision, order, mode, strategy_version=strategy_version, prompt_version=prompt_version
    )
