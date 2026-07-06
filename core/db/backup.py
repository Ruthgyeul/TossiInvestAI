"""자동 백업·복구 (docs/LOGGING.md).

매일 03:00 전체 덤프(30일 보관) / 매주 일요일 주간 스냅샷(1년) / 매월 1일 월간 스냅샷(무제한).
실패 시 Discord #stock-error 즉시 알림.
"""

from pathlib import Path

BACKUPS_DIR = Path("backups")


async def run_daily_backup() -> Path:
    raise NotImplementedError


async def run_weekly_backup() -> Path:
    raise NotImplementedError


async def run_monthly_backup() -> Path:
    raise NotImplementedError


async def restore(backup_path: Path) -> None:
    raise NotImplementedError
