"""discord-bot ↔ core 내부 HTTP API 서버. `127.0.0.1`에만 바인딩한다 (docs/INTERNAL_API.md).

discord-bot의 모든 요청은 `Authorization: Bearer {CORE_INTERNAL_API_TOKEN}` 헤더를 실어야 하며,
토큰이 없거나 일치하지 않으면 401 {"error": "unauthorized"}를 반환한다. 다른 토큰으로 재시도하지 않는다.
"""

import hmac
from collections.abc import Awaitable, Callable

from aiohttp import web

from core.api.routes import register_routes
from core.config import settings

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def auth_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    expected = f"Bearer {settings.CORE_INTERNAL_API_TOKEN}"
    provided = request.headers.get("Authorization", "")
    # hmac.compare_digest로 상수 시간 비교한다 — `!=`는 첫 불일치 바이트에서 조기 종료돼
    # 응답 시간차로 토큰을 바이트 단위로 추측하는 타이밍 공격에 노출된다.
    if not hmac.compare_digest(provided, expected):
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


def create_app() -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    register_routes(app)
    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    web.run_app(create_app(), host=host, port=port)
