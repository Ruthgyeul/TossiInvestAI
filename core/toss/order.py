"""주문 생성·정정·취소 (docs/TOSS_API.md). Safety Gate를 통과한 Order만 여기로 전달되어야 한다."""

import uuid
from dataclasses import replace
from typing import Any

from core.models import Market, Order
from core.toss import client
from core.toss.client import TossApiError


def generate_client_order_id(market: Market) -> str:
    return f"BIN-{market}-{uuid.uuid4().hex[:12].upper()}"


def _order_payload(order: Order) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": order.symbol,
        "market": order.market,
        "side": order.action,
        "quantity": order.quantity,
        "orderType": order.order_type,
        "clientOrderId": order.client_order_id,
    }
    if order.price is not None:
        payload["price"] = order.price
    if order.order_type == "AMOUNT":
        payload["amountKrw"] = order.amount_krw
    return payload


async def place(order: Order) -> dict:
    """POST /api/v1/orders.

    409 `request-in-progress`(동일 clientOrderId 처리 중)는 새 clientOrderId로 1회 재시도한다
    (docs/TOSS_API.md "에러 코드 전체 목록").
    """
    try:
        return await client.request(
            "POST",
            "/api/v1/orders",
            "ORDER",
            json=_order_payload(order),
            account_required=True,
        )
    except TossApiError as e:
        if e.code != "request-in-progress":
            raise
        retried_order = replace(order, client_order_id=generate_client_order_id(order.market))
        return await client.request(
            "POST",
            "/api/v1/orders",
            "ORDER",
            json=_order_payload(retried_order),
            account_required=True,
        )


async def modify(order_id: str, **changes: Any) -> dict:
    """POST /api/v1/orders/{orderId}/modify."""
    return await client.request(
        "POST",
        f"/api/v1/orders/{order_id}/modify",
        "ORDER",
        json=changes,
        account_required=True,
    )


async def cancel(order_id: str) -> dict:
    """POST /api/v1/orders/{orderId}/cancel."""
    return await client.request(
        "POST",
        f"/api/v1/orders/{order_id}/cancel",
        "ORDER",
        account_required=True,
    )


async def get_orders(status: str | None = None) -> list[dict]:
    """GET /api/v1/orders — 대기중/종료 목록."""
    params = {"status": status} if status else None
    data = await client.request(
        "GET", "/api/v1/orders", "ORDER_HISTORY", params=params, account_required=True
    )
    return data["orders"]  # type: ignore[no-any-return]


async def get_order(order_id: str) -> dict:
    """GET /api/v1/orders/{orderId}."""
    return await client.request(
        "GET",
        f"/api/v1/orders/{order_id}",
        "ORDER_HISTORY",
        account_required=True,
    )
