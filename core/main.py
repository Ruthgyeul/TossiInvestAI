"""bin-core.service 진입점. 트레이딩 스케줄러 + 내부 HTTP API 서버를 한 프로세스에서 기동한다."""

import asyncio

import structlog
from aiohttp import web

from datetime import datetime, timezone

from core.api.server import create_app
from core.config import settings
from core.db.store import (
    get_control_flags,
    get_simulation_started_at,
    init_models,
    set_simulation_started_at,
)
from core.scheduler.tasks import register_all_jobs, scheduler

log = structlog.get_logger(__name__)


async def _start_api_server() -> web.AppRunner:
    runner = web.AppRunner(create_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8000)
    await site.start()
    return runner


async def _restore_control_flags() -> None:
    """프로세스 재시작(systemd 자동 재시작 등)으로 인메모리 EMERGENCY_STOP이 초기화되지
    않도록 DB에서 복원한다 (docs/SAFETY.md "EMERGENCY_STOP = true (DB + Redis 즉시 반영)")."""
    flags = await get_control_flags()
    settings.EMERGENCY_STOP = flags["emergency_stop"]
    settings.KR_STOP = flags["kr_stop"]
    settings.US_STOP = flags["us_stop"]
    if any(flags.values()):
        log.warning("control_flags_restored", **flags)


async def _restore_simulation_clock() -> None:
    """SIMULATION 시작 시각을 복원한다. 프로세스 재시작(systemd 자동 재시작 등)이 리허설
    기간을 소리 없이 리셋하면 안 되므로, DB에 기록이 없을 때만(최초 부팅) 지금 시각으로
    새로 기록한다 (docs/SAFETY.md "실전 전환 전 SIMULATION 모드 2주 이상 필수")."""
    if not settings.SIMULATION:
        return
    started_at = await get_simulation_started_at()
    if started_at is None:
        await set_simulation_started_at(datetime.now(timezone.utc))


async def main() -> None:
    await init_models()
    await _restore_control_flags()
    await _restore_simulation_clock()
    register_all_jobs()
    scheduler.start()
    await _start_api_server()

    log.info("bin_core_started", mode=settings.run_mode)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
