"""Toss API 클라이언트 Rate Limit·인증·재시도 단위 테스트 (docs/TOSS_API.md)."""

from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pytest
from aioresponses import aioresponses

from core.toss import auth, client

_BASE_URL = "https://openapi.tossinvest.com"
_KST = ZoneInfo("Asia/Seoul")


@pytest.mark.asyncio
async def test_token_refresh_before_expiry(fake_redis) -> None:
    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/oauth2/token",
            payload={"access_token": "token-1", "expires_in": 3600},
        )
        token = await auth.get_access_token()

    assert token == "token-1"

    ttl = await fake_redis.ttl(auth.TOKEN_CACHE_KEY)
    assert ttl == pytest.approx(3600 - auth.REFRESH_MARGIN_SECONDS, abs=5)

    # 캐시가 유효한 동안에는 재발급 없이 캐시된 토큰을 반환한다 (HTTP 목업 없이 호출).
    with aioresponses():
        cached_token = await auth.get_access_token()
    assert cached_token == "token-1"


@pytest.mark.asyncio
async def test_rate_limit_backoff_on_429(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def _fake_token() -> str:
        return "test-token"

    monkeypatch.setattr(client.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(client, "get_access_token", _fake_token)

    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/prices?symbol=005930",
            status=429,
            headers={"Retry-After": "1"},
        )
        mocked.get(
            f"{_BASE_URL}/api/v1/prices?symbol=005930",
            payload={"symbol": "005930", "price": 74800},
        )

        result = await client.request(
            "GET", "/api/v1/prices", "MARKET_DATA", params={"symbol": "005930"}
        )

    assert result == {"symbol": "005930", "price": 74800}
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 1.0


@pytest.mark.asyncio
async def test_peak_time_order_requests_enforce_400ms_spacing(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """docs/TOSS_API.md "피크 시간 주문: 최소 400ms 간격 유지"."""
    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def _fake_token() -> str:
        return "test-token"

    peak_now = datetime.combine(datetime.now(_KST).date(), dtime(9, 5), tzinfo=_KST)
    monkeypatch.setattr(client, "_is_peak_time", lambda now=None: True)
    monkeypatch.setattr(client.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(client, "get_access_token", _fake_token)

    # 직전 주문 요청이 100ms 전에 있었던 것으로 시뮬레이션 → 300ms를 더 기다려야 한다.
    await fake_redis.set(
        "ratelimit:peak_last:ORDER", str(peak_now.timestamp() - 0.1)
    )

    monkeypatch.setattr(client.time, "time", lambda: peak_now.timestamp())

    with aioresponses() as mocked:
        mocked.post(f"{_BASE_URL}/api/v1/orders", payload={"orderId": "o-1"})
        await client.request("POST", "/api/v1/orders", "ORDER", json={"symbol": "005930"})

    assert any(0.29 <= s <= 0.31 for s in sleep_calls)


@pytest.mark.asyncio
async def test_already_canceled_order_treated_as_success(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """docs/TOSS_API.md 409 `already-canceled` → 무시(성공으로 간주)."""

    async def _fake_token() -> str:
        return "test-token"

    monkeypatch.setattr(client, "get_access_token", _fake_token)

    with aioresponses() as mocked:
        mocked.post(
            f"{_BASE_URL}/api/v1/orders/order-1/cancel",
            status=409,
            payload={"code": "already-canceled", "message": "이미 취소됨"},
        )
        result = await client.request(
            "POST", "/api/v1/orders/order-1/cancel", "ORDER", account_required=True
        )

    assert result == {"code": "already-canceled", "alreadyDone": True, "message": "이미 취소됨"}


@pytest.mark.asyncio
async def test_expired_token_triggers_refresh_and_retry(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """docs/TOSS_API.md 401 `expired-token` → 재발급 후 재시도."""
    tokens = iter(["stale-token", "fresh-token"])

    async def _fake_token() -> str:
        return next(tokens)

    invalidated: list[bool] = []

    async def _fake_invalidate() -> None:
        invalidated.append(True)

    monkeypatch.setattr(client, "get_access_token", _fake_token)
    monkeypatch.setattr(client, "invalidate_token", _fake_invalidate)

    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/prices?symbol=005930",
            status=401,
            payload={"code": "expired-token", "message": "토큰 만료"},
        )
        mocked.get(
            f"{_BASE_URL}/api/v1/prices?symbol=005930",
            payload={"symbol": "005930", "price": 74800},
        )
        result = await client.request(
            "GET", "/api/v1/prices", "MARKET_DATA", params={"symbol": "005930"}
        )

    assert result == {"symbol": "005930", "price": 74800}
    assert invalidated == [True]


@pytest.mark.asyncio
async def test_maintenance_alerts_discord_and_raises(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """docs/TOSS_API.md 500 `maintenance` → Discord 알림 후 예외."""

    async def _fake_token() -> str:
        return "test-token"

    monkeypatch.setattr(client, "get_access_token", _fake_token)

    published: dict = {}

    async def _fake_publish_event(event_type: str, **kwargs):
        published["event_type"] = event_type
        published.update(kwargs)

    import core.events.publisher as publisher_module

    monkeypatch.setattr(publisher_module, "publish_event", _fake_publish_event)

    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/prices?symbol=005930",
            status=500,
            payload={"code": "maintenance", "message": "시스템 점검 중입니다"},
        )
        with pytest.raises(client.TossApiError, match="maintenance"):
            await client.request(
                "GET", "/api/v1/prices", "MARKET_DATA", params={"symbol": "005930"}
            )

    assert published["event_type"] == "health_alert"
    assert "점검" in published["payload"]["warnings"][0]
