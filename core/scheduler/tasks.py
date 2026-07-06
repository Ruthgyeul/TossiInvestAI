"""APScheduler 태스크 정의. KR·US 루프, 리포트 6회/일, Reflection, 주간 재배분, 백업, 헬스체크를 등록한다.

시각은 모두 KST 기준이며 docs/REPORT.md·docs/FUND_MANAGER.md·docs/LOGGING.md 스케줄을 따른다.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def register_all_jobs() -> None:
    """트레이딩 루프(15분 간격) + 리포트(08:50/12:00/15:35/22:20/02:00/06:05) +
    Reflection(15:40 KR·06:10 US) + 주간 재배분(월요일 장전) +
    DB 백업(03:00/일요일/매월1일) + 헬스체크(5분 간격)를 등록한다."""
    raise NotImplementedError
