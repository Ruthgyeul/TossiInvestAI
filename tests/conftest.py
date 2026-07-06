"""pytest 공용 설정 — Settings 필수 필드 테스트 기본값, 공유 fixture."""

import os

_TEST_ENV_DEFAULTS = {
    "TOSS_CLIENT_ID": "test-client-id",
    "TOSS_CLIENT_SECRET": "test-client-secret",
    "TOSS_ACCOUNT_SEQ": "test-account-seq",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "GEMINI_API_KEY": "test-gemini-key",
    "DEEPSEEK_API_KEY": "test-deepseek-key",
    "DATABASE_URL": "postgresql+asyncpg://bin:changeme@localhost:5432/bin_trading_test",
    "REDIS_URL": "redis://localhost:6379/1",
    "CORE_INTERNAL_API_TOKEN": "test-internal-token",
}
for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402

import core.db.redis as redis_module  # noqa: E402


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> fakeredis.aioredis.FakeRedis:
    """core.db.redis.get_redis()가 실제 Redis 대신 반환하도록 패치한 인메모리 Redis."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_redis", fake)
    return fake
