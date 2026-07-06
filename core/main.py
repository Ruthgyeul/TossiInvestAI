"""bin-core.service 진입점. 트레이딩 스케줄러 + 내부 HTTP API 서버를 한 프로세스에서 기동한다."""

import asyncio

import structlog
from aiohttp import web

from core.api.server import create_app
from core.config import settings
from core.db.store import init_models
from core.scheduler.tasks import register_all_jobs, scheduler

log = structlog.get_logger(__name__)


async def _start_api_server() -> web.AppRunner:
    runner = web.AppRunner(create_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8000)
    await site.start()
    return runner


async def main() -> None:
    await init_models()
    register_all_jobs()
    scheduler.start()
    await _start_api_server()

    log.info("bin_core_started", mode=settings.run_mode)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
