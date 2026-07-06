"""Toss API 클라이언트 Rate Limit·인증·재시도 단위 테스트 (docs/TOSS_API.md)."""

import pytest
from aioresponses import aioresponses

from core.toss import auth, client

_BASE_URL = "https://openapi.tossinvest.com"


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
