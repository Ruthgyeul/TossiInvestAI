"""토스증권 API 공통 HTTP 클라이언트. Rate Limit 선제 제어 + 429 지수 백오프 (docs/TOSS_API.md)."""

import asyncio
import random
import time
from datetime import datetime, time as dtime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import aiohttp

from core.config import settings
from core.db.redis import get_redis
from core.toss.auth import get_access_token, invalidate_token

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
# 피크 시간 주문은 초당 요청 수 제한과 별개로 최소 400ms 간격을 둔다 (docs/TOSS_API.md).
_PEAK_MIN_INTERVAL_SECONDS = 0.4
_KST = ZoneInfo("Asia/Seoul")

_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0

# docs/TOSS_API.md "에러 코드 전체 목록" — 자동 처리가 안전한 코드만 여기서 분기하고,
# 나머지(가격 재조정·미체결 취소 후 재시도 등 업무 판단이 필요한 코드)는 TossApiError로
# 그대로 전달해 호출자가 code로 분기하도록 한다.
_IGNORE_AS_SUCCESS_CODES = {"already-filled", "already-canceled", "already-modified", "order-not-found"}
_TOKEN_REFRESH_CODES = {"invalid-token", "expired-token", "login-user-not-found"}
_WAIT_THEN_RETRY_SECONDS: dict[str, float] = {"already-processing": 1.0, "internal-error": 30.0}


class TossApiError(Exception):
    """토스 API가 반환한 구조화된 에러. `code`로 docs/TOSS_API.md 표와 대조해 분기할 수 있다."""

    def __init__(self, http_status: int, code: str | None, message: str) -> None:
        super().__init__(f"{http_status} {code}: {message}")
        self.http_status = http_status
        self.code = code
        self.message = message


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


async def _enforce_peak_spacing(group: RateLimitGroup) -> None:
    """피크 시간 ORDER/ORDER_INFO는 초당 요청 수 제한과 별개로 최소 400ms 간격을 보장한다
    (docs/TOSS_API.md "피크 시간 주문: 최소 400ms 간격 유지")."""
    if group not in _PEAK_RATE_LIMITS or not _is_peak_time():
        return

    redis = get_redis()
    key = f"ratelimit:peak_last:{group}"
    now = time.time()
    last_raw = await redis.get(key)
    if last_raw is not None:
        elapsed = now - float(last_raw)
        if elapsed < _PEAK_MIN_INTERVAL_SECONDS:
            await asyncio.sleep(_PEAK_MIN_INTERVAL_SECONDS - elapsed)

    await redis.set(key, str(time.time()), ex=5)


async def _read_error_body(resp: aiohttp.ClientResponse) -> tuple[str | None, str]:
    """에러 응답 바디에서 `code`/`message`를 추출한다. JSON이 아니면 code=None, 원문 텍스트를 반환."""
    try:
        body = await resp.json(content_type=None)
        return body.get("code"), body.get("message", "")
    except Exception:  # noqa: BLE001 — 바디 파싱 실패는 코드 없이 원문 텍스트로 대체한다
        return None, await resp.text()


async def _alert_maintenance(path: str, message: str) -> None:
    from core.events.publisher import publish_event

    await publish_event(
        "health_alert",
        mode=settings.run_mode,
        market=None,
        payload={"warnings": [f"토스증권 시스템 점검 중: {path} — {message}"]},
    )


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
    그 외 에러 코드는 docs/TOSS_API.md "에러 코드 전체 목록" 기준으로 분기한다:
    토큰 만료류는 재발급 후 재시도, 멱등 코드(이미 체결/취소/정정·주문 없음)는 성공으로 간주,
    일시 장애/처리 중은 대기 후 재시도, 점검 중은 Discord 알림 후 즉시 예외.
    """
    backoff = _INITIAL_BACKOFF_SECONDS

    for attempt in range(_MAX_RETRIES + 1):
        await _acquire_slot(group)
        await _enforce_peak_spacing(group)

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

                if resp.status >= 400:
                    code, message = await _read_error_body(resp)

                    if code in _IGNORE_AS_SUCCESS_CODES:
                        return {"code": code, "alreadyDone": True, "message": message}

                    if code == "maintenance":
                        await _alert_maintenance(path, message)
                        raise TossApiError(resp.status, code, message)

                    if code in _TOKEN_REFRESH_CODES and attempt < _MAX_RETRIES:
                        await invalidate_token()
                        continue

                    if code in _WAIT_THEN_RETRY_SECONDS and attempt < _MAX_RETRIES:
                        await asyncio.sleep(_WAIT_THEN_RETRY_SECONDS[code])
                        continue

                    raise TossApiError(resp.status, code, message)

                return await resp.json()  # type: ignore[no-any-return]

    raise aiohttp.ClientError(f"rate-limit-exceeded: {group} {path}")
