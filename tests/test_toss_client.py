"""Toss API 클라이언트 Rate Limit·인증·재시도 단위 테스트 (docs/TOSS_API.md)."""

import pytest


@pytest.mark.asyncio
async def test_token_refresh_before_expiry() -> None:
    pytest.skip("TODO: Phase 1 — toss/auth.py 구현 후 작성")


@pytest.mark.asyncio
async def test_rate_limit_backoff_on_429() -> None:
    pytest.skip("TODO: Phase 1 — toss/client.py 구현 후 작성")
