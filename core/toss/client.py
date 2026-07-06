"""토스증권 API 공통 HTTP 클라이언트. Rate Limit 선제 제어 + 429 지수 백오프 (docs/TOSS_API.md)."""

import asyncio
import random
from datetime import datetime, time as dtime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import aiohttp

from core.config import settings
from core.db.redis import get_redis
from core.toss.auth import get_access_token

RateLimitGroup = Literal[
    "AUTH",
    "ACCOUNT",
    "ASSET",
    "STOCK",
    "MARKET_INFO",
    "MARKET_DATA",
    "MARKET_DATA_CHART",
    "ORDER",
    "ORDER_HISTORY",
    "ORDER_INFO",
]

_RATE_LIMITS: dict[str, int] = {
    "AUTH": 5,
    "ACCOUNT": 1,
    "ASSET": 5,
    "STOCK": 5,
    "MARKET_INFO": 3,
    "MARKET_DATA": 10,
    "MARKET_DATA_CHART": 5,
    "ORDER": 6,
    "ORDER_HISTORY": 5,
    "ORDER_INFO": 6,
}
# 피크 시간(09:00~09:10 KST)에는 주문 관련 그룹만 한도가 축소된다.
_PEAK_RATE_LIMITS: dict[str, int] = {"ORDER": 3, "ORDER_INFO": 3}
_KST = ZoneInfo("Asia/Seoul")

_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0


def _is_peak_time(now: datetime | None = None) -> bool:
    current = (now or datetime.now(_KST)).astimezone(_KST).time()
    return dtime(9, 0) <= current < dtime(9, 10)


def _limit_for(group: RateLimitGroup) -> int:
    if group in _PEAK_RATE_LIMITS and _is_peak_time():
        return _PEAK_RATE_LIMITS[group]
    return _RATE_LIMITS[group]


async def _acquire_slot(group: RateLimitGroup) -> None:
    """Redis `ratelimit:{group}` 1초 윈도우 카운터로 선제 제어."""
    redis = get_redis()
    key = f"ratelimit:{group}"
    limit = _limit_for(group)
    while True:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 1)
        if count <= limit:
            return
        await asyncio.sleep(1)


async def request(
    method: Literal["GET", "POST"],
    path: str,
    group: RateLimitGroup,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    account_required: bool = False,
) -> dict[str, Any]:
    """Redis `ratelimit:{group}` 카운터로 선제 제어 후 요청.

    429 수신 시 Retry-After 대기 → 1s/2s/4s 지수 백오프 + jitter.
    """
    backoff = _INITIAL_BACKOFF_SECONDS

    for attempt in range(_MAX_RETRIES + 1):
        await _acquire_slot(group)

        headers = {"Authorization": f"Bearer {await get_access_token()}"}
        if account_required:
            headers["X-Tossinvest-Account"] = settings.TOSS_ACCOUNT_SEQ

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                f"{settings.TOSS_BASE_URL}{path}",
                params=params,
                json=json,
                headers=headers,
            ) as resp:
                if resp.status == 429 and attempt < _MAX_RETRIES:
                    retry_after = float(resp.headers.get("Retry-After", backoff))
                    await asyncio.sleep(retry_after + random.uniform(0, 0.5))
                    backoff = min(backoff * 2, 4.0)
                    continue
                resp.raise_for_status()
                return await resp.json()  # type: ignore[no-any-return]

    raise aiohttp.ClientError(f"rate-limit-exceeded: {group} {path}")
