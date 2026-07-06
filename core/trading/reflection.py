"""장 마감 후 자기평가. KR 15:40 / US 06:10 (KST) 1회 실행 (docs/BIN.md)."""

from core.models import Market


async def run_reflection(market: Market) -> None:
    """오늘 매매 적절성·놓친 기회·Safety Gate 거부 타당성·개선점을 Claude에 질의하고
    reflections 테이블 + logs/reports/reflection_YYYY-MM-DD.md 에 저장한다."""
    raise NotImplementedError
