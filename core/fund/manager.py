"""자금 배분·재투자·API 비용 추적 (docs/FUND_MANAGER.md).

INITIAL_SEED_KRW는 손익 계산 기준점이므로 최초 설정 이후 절대 변경하지 않는다.
"""

from dataclasses import dataclass

from core.config import settings


@dataclass
class RebalanceResult:
    api_cost_covered_krw: int
    reinvested_krw: int
    buffer_added_krw: int


class FundManager:
    def get_total_value_krw(self) -> float:
        """총 자산 KRW 환산 (보유 주식 시가 + 현금)."""
        raise NotImplementedError

    def get_operating_funds_krw(self) -> float:
        """운용 자금 = 총 자산 - 현금 버퍼."""
        raise NotImplementedError

    def get_cash_buffer_krw(self) -> float:
        """현금 버퍼 잔고."""
        raise NotImplementedError

    def can_allocate(self, amount_krw: float, symbol: str) -> tuple[bool, str]:
        """주문 가능 여부 판단 (종목당 상한 MAX_POSITION_RATIO 체크)."""
        raise NotImplementedError

    async def weekly_rebalance(self) -> RebalanceResult:
        """매주 월요일 장 시작 전 자동 실행. 코드 외부에서 임의 변경 불가.

        STEP 1. Claude API 사용료 추정 → 현금 버퍼에서 확보
        STEP 2. 남은 순수익의 80% → 운용 자금 재투자
        STEP 3. 남은 순수익의 20% → 현금 버퍼 적립
        STEP 4. 현금 버퍼가 총 자산의 20% 초과 시 초과분을 운용 자금으로 이동
        """
        raise NotImplementedError

    def record_api_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """Claude API 호출마다 토큰 수·비용을 api_usage 테이블에 기록한다."""
        p_in = settings.claude_input_price_per_mtok / 1_000_000
        p_out = settings.claude_output_price_per_mtok / 1_000_000

        cost_usd = (
            input_tokens * p_in
            + cache_write_tokens * p_in * 1.25  # 5m write
            + cache_read_tokens * p_in * 0.10   # hit
            + output_tokens * p_out
        )
        self._insert_api_usage(model, cost_usd, input_tokens, output_tokens,
                                cache_read_tokens, cache_write_tokens)

    def _insert_api_usage(
        self,
        model: str,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
    ) -> None:
        raise NotImplementedError

    def estimated_api_cost_krw(self) -> float:
        """이번 달 추정 API 비용 (KRW 환산)."""
        raise NotImplementedError

    def get_position_ratio(self, symbol: str) -> float:
        """특정 종목의 운용 자금 대비 비중."""
        raise NotImplementedError


fund_manager = FundManager()
