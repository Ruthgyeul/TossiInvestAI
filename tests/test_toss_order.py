"""주문 생성·정정·취소 단위 테스트 — DRY_RUN 모드 (docs/CODING_RULES.md Phase 2-9)."""

import pytest
from aioresponses import aioresponses

from core.config import settings
from core.models import Order
from core.toss import order

_BASE_URL = "https://openapi.tossinvest.com"


@pytest.fixture(autouse=True)
def _stub_token(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_token() -> str:
        return "test-token"

    monkeypatch.setattr(order.client, "get_access_token", _fake_token)


@pytest.fixture(autouse=True)
def _dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """toss/order.py는 DRY_RUN 모드에서도 동일한 HTTP 계약을 지킨다 (개발용 소액 테스트)."""
    monkeypatch.setattr(settings, "DRY_RUN", True)


def test_generate_client_order_id_format() -> None:
    client_order_id = order.generate_client_order_id("KR")
    assert client_order_id.startswith("BIN-KR-")
    assert len(client_order_id) == len("BIN-KR-") + 12


@pytest.mark.asyncio
async def test_place_limit_order_kr(fake_redis) -> None:
    kr_order = Order(
        symbol="005930",
        market="KR",
        action="BUY",
        quantity=2,
        order_type="LIMIT",
        price=74800.0,
        amount_krw=149_600,
        client_order_id=order.generate_client_order_id("KR"),
    )
    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/api/v1/orders",
            payload={"orderId": "order-1", "status": "PENDING"},
        )
        result = await order.place(kr_order)

    assert result == {"orderId": "order-1", "status": "PENDING"}


@pytest.mark.asyncio
async def test_place_retries_with_new_client_order_id_on_request_in_progress(
    fake_redis,
) -> None:
    """docs/TOSS_API.md 409 `request-in-progress` → 새 clientOrderId로 재시도."""
    kr_order = Order(
        symbol="005930",
        market="KR",
        action="BUY",
        quantity=2,
        order_type="LIMIT",
        price=74_800.0,
        amount_krw=149_600,
        client_order_id=order.generate_client_order_id("KR"),
    )
    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/api/v1/orders",
            status=409,
            payload={"code": "request-in-progress", "message": "동일 주문 처리 중"},
        )
        mocked.post(
            f"{_BASE_URL}/api/v1/orders",
            payload={"orderId": "order-retry", "status": "PENDING"},
        )
        result = await order.place(kr_order)

    assert result == {"orderId": "order-retry", "status": "PENDING"}


@pytest.mark.asyncio
async def test_place_amount_order_us(fake_redis) -> None:
    us_order = Order(
        symbol="AAPL",
        market="US",
        action="BUY",
        quantity=0,
        order_type="AMOUNT",
        price=None,
        amount_krw=100_000,
        client_order_id=order.generate_client_order_id("US"),
    )
    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/api/v1/orders",
            payload={"orderId": "order-2", "status": "PENDING"},
        )
        result = await order.place(us_order)

    assert result == {"orderId": "order-2", "status": "PENDING"}


@pytest.mark.asyncio
async def test_modify_order(fake_redis) -> None:
    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/api/v1/orders/order-1/modify",
            payload={"orderId": "order-1", "status": "MODIFIED"},
        )
        result = await order.modify("order-1", price=75000.0)

    assert result == {"orderId": "order-1", "status": "MODIFIED"}


@pytest.mark.asyncio
async def test_cancel_order(fake_redis) -> None:
    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/api/v1/orders/order-1/cancel",
            payload={"orderId": "order-1", "status": "CANCELED"},
        )
        result = await order.cancel("order-1")

    assert result == {"orderId": "order-1", "status": "CANCELED"}


@pytest.mark.asyncio
async def test_get_orders_filters_by_status(fake_redis) -> None:
    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/orders?status=PENDING",
            payload={"orders": [{"orderId": "order-1", "status": "PENDING"}]},
        )
        result = await order.get_orders(status="PENDING")

    assert result == [{"orderId": "order-1", "status": "PENDING"}]


@pytest.mark.asyncio
async def test_get_order(fake_redis) -> None:
    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/orders/order-1",
            payload={"orderId": "order-1", "status": "FILLED"},
        )
        result = await order.get_order("order-1")

    assert result == {"orderId": "order-1", "status": "FILLED"}
