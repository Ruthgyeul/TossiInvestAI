"""주문 생성·정정·취소 (docs/TOSS_API.md). Safety Gate를 통과한 Order만 여기로 전달되어야 한다."""

import uuid

from core.models import Market, Order


def generate_client_order_id(market: Market) -> str:
    return f"BIN-{market}-{uuid.uuid4().hex[:12].upper()}"


async def place(order: Order) -> dict:
    """POST /api/v1/orders."""
    raise NotImplementedError


async def modify(order_id: str, **changes) -> dict:
    """POST /api/v1/orders/{orderId}/modify."""
    raise NotImplementedError


async def cancel(order_id: str) -> dict:
    """POST /api/v1/orders/{orderId}/cancel."""
    raise NotImplementedError


async def get_orders(status: str | None = None) -> list[dict]:
    """GET /api/v1/orders — 대기중/종료 목록."""
    raise NotImplementedError


async def get_order(order_id: str) -> dict:
    """GET /api/v1/orders/{orderId}."""
    raise NotImplementedError
