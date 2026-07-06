"""리포트 텍스트 생성 — 하루 6회 정기 리포트 + 즉시 리포트 (docs/REPORT.md)."""

from typing import Literal

ReportType = Literal["pre_market", "midday", "close", "weekly"]


async def generate_report(market: Literal["KR", "US"], report_type: ReportType) -> str:
    """REPORT.md 14개 필수 항목(시장 요약·지수·환율·공포탐욕지수·인기종목·
    거래량 급증·등락률 TOP10·보유종목 분석·기술적 분석·AI 예상/추천·
    리스크 요소·오늘 전략)을 포함한 마크다운 리포트를 생성한다."""
    raise NotImplementedError


async def generate_weekly_report() -> str:
    """매주 월요일 장 시작 전 발송되는 주간 성과 리포트."""
    raise NotImplementedError
