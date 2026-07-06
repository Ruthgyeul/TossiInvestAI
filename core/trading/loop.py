"""KR·US 트레이딩 루프 진입점. APScheduler가 시장별로 독립 실행한다 (docs/BIN.md)."""

from core.models import Market


async def run_loop(market: Market) -> None:
    """매 15분 실행되는 단일 루프 사이클.

    STEP 1. 시장 캘린더 확인 — 장 마감이면 스킵
    STEP 2. 시장 데이터 수집 (Redis 캐시 우선)
    STEP 3. 규칙 기반 필터 (Claude 호출 없이 처리)
    STEP 4. StateSnapshot 구성
    STEP 5. Claude API 직접 호출
    STEP 6. Safety Gate 검증
    STEP 7. 주문 실행 / 가상 체결
    STEP 8. 결과 기록 (DB·로그·Discord)
    """
    raise NotImplementedError


async def start_schedulers() -> None:
    """KR·US 루프를 APScheduler에 등록하고 기동한다."""
    raise NotImplementedError
