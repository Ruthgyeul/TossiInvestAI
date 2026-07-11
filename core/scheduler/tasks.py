"""APScheduler 태스크 정의. KR·US 루프, 리포트 6회/일, 헬스체크, 자동 백업, 자기평가를 등록한다.

시각은 모두 KST 기준이며 docs/REPORT.md·docs/FUND_MANAGER.md·docs/LOGGING.md·docs/BIN.md
스케줄을 따른다.
"""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.db.backup import run_daily_backup, run_monthly_backup, run_weekly_backup
from core.monitoring.health import run_health_check
from core.report.generator import generate_and_publish, generate_weekly_and_publish
from core.trading.reflection import run_reflection

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
        generate_weekly_and_publish,
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

    # docs/LOGGING.md "자동 DB 백업" — 매일 03:00 / 매주 일요일 / 매월 1일 (KST)
    scheduler.add_job(
        run_daily_backup,
        CronTrigger(hour=3, minute=0, timezone=_KST),
        id="db_backup_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        run_weekly_backup,
        CronTrigger(day_of_week="sun", hour=3, minute=10, timezone=_KST),
        id="db_backup_weekly",
        replace_existing=True,
    )
    scheduler.add_job(
        run_monthly_backup,
        CronTrigger(day=1, hour=3, minute=20, timezone=_KST),
        id="db_backup_monthly",
        replace_existing=True,
    )

    # docs/BIN.md "자기평가" — KR 15:40 / US 06:10 (KST) 장 마감 후 1회
    scheduler.add_job(
        run_reflection,
        CronTrigger(hour=15, minute=40, timezone=_KST),
        args=["KR"],
        id="reflection_kr",
        replace_existing=True,
    )
    scheduler.add_job(
        run_reflection,
        CronTrigger(hour=6, minute=10, timezone=_KST),
        args=["US"],
        id="reflection_us",
        replace_existing=True,
    )
