"""공유 Redis 클라이언트 싱글턴 (docs/ARCHITECTURE.md Redis 키 표 참고).

토큰 캐시(`token:toss`)·Rate Limit 카운터(`ratelimit:{group}`)·시세 캐시(`price:{symbol}` 등)에서
동일한 커넥션 풀을 공유한다.
"""

from redis.asyncio import Redis

from core.config import settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis
