"""APScheduler 태스크 정의. KR·US 루프, 리포트 6회/일, 헬스체크를 등록한다.

시각은 모두 KST 기준이며 docs/REPORT.md·docs/FUND_MANAGER.md·docs/LOGGING.md 스케줄을 따른다.

Reflection(자기평가)·자동 DB 백업은 core/trading/reflection.py·core/db/backup.py가
아직 최소 스캐폴드 상태라 이번 Phase에서는 등록하지 않는다 — 구현 완료 후 여기에 추가한다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings
from core.events.publisher import publish_event
from core.monitoring.health import run_health_check
from core.report.generator import generate_and_publish, generate_weekly_report

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
_KST = ZoneInfo("Asia/Seoul")

# docs/REPORT.md 리포트 스케줄 (KST)
_REPORT_SCHEDULE: list[tuple[str, str, str, str]] = [
    ("08:50", "KR", "pre_market", "report_kr_pre_market"),
    ("12:00", "KR", "midday", "report_kr_midday"),
    ("15:35", "KR", "close", "report_kr_close"),
    ("22:20", "US", "pre_market", "report_us_pre_market"),
    ("02:00", "US", "midday", "report_us_midday"),
    ("06:05", "US", "close", "report_us_close"),
]


async def _run_weekly_report() -> None:
    content_md = await generate_weekly_report()
    await publish_event(
        "report_ready",
        mode=settings.run_mode,
        market=None,
        payload={
            "title": "[빈] 주간 성과 리포트",
            "market": "ALL",
            "reportType": "weekly",
            "contentMd": content_md[:3800],
            "chartPaths": [],
            "generatedAt": datetime.now(_KST).isoformat(),
        },
    )


def register_all_jobs() -> None:
    """트레이딩 루프(15분 간격) + 리포트(08:50/12:00/15:35/22:20/02:00/06:05) +
    주간 리포트(월요일 장전) + 헬스체크(5분 간격)를 등록한다."""
    from core.trading.loop import start_schedulers

    start_schedulers()

    for time_str, market, report_type, job_id in _REPORT_SCHEDULE:
        hour, minute = (int(part) for part in time_str.split(":"))
        scheduler.add_job(
            generate_and_publish,
            CronTrigger(hour=hour, minute=minute, timezone=_KST),
            args=[market, report_type],
            id=job_id,
            replace_existing=True,
        )

    scheduler.add_job(
        _run_weekly_report,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=_KST),
        id="weekly_report",
        replace_existing=True,
    )

    scheduler.add_job(
        run_health_check,
        "interval",
        minutes=5,
        id="health_check",
        replace_existing=True,
    )
