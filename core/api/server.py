"""discord-bot ↔ core 내부 HTTP API 서버. `127.0.0.1`에만 바인딩한다 (docs/INTERNAL_API.md).

discord-bot의 모든 요청은 `Authorization: Bearer {CORE_INTERNAL_API_TOKEN}` 헤더를 실어야 하며,
토큰이 없거나 일치하지 않으면 401 {"error": "unauthorized"}를 반환한다. 다른 토큰으로 재시도하지 않는다.
"""

from aiohttp import web

from core.api.routes import register_routes
from core.config import settings


@web.middleware
async def auth_middleware(request: web.Request, handler: web.Handler) -> web.StreamResponse:
    if request.headers.get("Authorization") != f"Bearer {settings.CORE_INTERNAL_API_TOKEN}":
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


def create_app() -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    register_routes(app)
    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    web.run_app(create_app(), host=host, port=port)
