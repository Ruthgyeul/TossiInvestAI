"""core/api/server.py auth_middleware — Bearer 토큰 검증 (docs/INTERNAL_API.md)."""

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from core.api.server import auth_middleware
from core.config import settings


async def _handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


@pytest.mark.asyncio
async def test_auth_middleware_rejects_missing_token() -> None:
    request = make_mocked_request("GET", "/api/v1/status")

    response = await auth_middleware(request, _handler)

    assert response.status == 401


@pytest.mark.asyncio
async def test_auth_middleware_rejects_wrong_token() -> None:
    request = make_mocked_request(
        "GET", "/api/v1/status", headers={"Authorization": "Bearer wrong-token"}
    )

    response = await auth_middleware(request, _handler)

    assert response.status == 401


@pytest.mark.asyncio
async def test_auth_middleware_accepts_correct_token() -> None:
    request = make_mocked_request(
        "GET",
        "/api/v1/status",
        headers={"Authorization": f"Bearer {settings.CORE_INTERNAL_API_TOKEN}"},
    )

    response = await auth_middleware(request, _handler)

    assert response.status == 200
