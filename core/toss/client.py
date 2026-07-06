"""토스증권 API 공통 HTTP 클라이언트. Rate Limit 선제 제어 + 429 지수 백오프 (docs/TOSS_API.md)."""

from typing import Any, Literal

RateLimitGroup = Literal[
    "AUTH", "ACCOUNT", "ASSET", "STOCK",
    "MARKET_INFO", "MARKET_DATA", "MARKET_DATA_CHART",
    "ORDER", "ORDER_HISTORY", "ORDER_INFO",
]


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
    raise NotImplementedError
