"""토스증권 OAuth2 토큰 발급·갱신. Redis `token:toss` 키로 캐시하고 만료 5분 전 자동 갱신 (docs/TOSS_API.md)."""

from typing import cast

import aiohttp

from core.config import settings
from core.db.redis import get_redis

TOKEN_CACHE_KEY = "token:toss"
REFRESH_MARGIN_SECONDS = 300


async def get_access_token() -> str:
    """캐시된 토큰이 유효하면 반환하고, 아니면 재발급한다."""
    redis = get_redis()
    cached = await redis.get(TOKEN_CACHE_KEY)
    if cached:
        # decode_responses=True로 생성된 클라이언트이므로 항상 str이다.
        return cast(str, cached)
    return await _issue_token()


async def _issue_token() -> str:
    """POST /oauth2/token — grant_type=client_credentials."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{settings.TOSS_BASE_URL}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.TOSS_CLIENT_ID,
                "client_secret": settings.TOSS_CLIENT_SECRET,
            },
        ) as resp:
            resp.raise_for_status()
            body = await resp.json()

    access_token: str = body["access_token"]
    expires_in = int(body["expires_in"])

    # 만료 5분 전 캐시가 먼저 소멸하도록 TTL을 짧게 잡아 재발급을 유도한다.
    ttl = max(expires_in - REFRESH_MARGIN_SECONDS, 60)
    await get_redis().set(TOKEN_CACHE_KEY, access_token, ex=ttl)
    return access_token
