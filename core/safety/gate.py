"""Safety Gate — 모든 주문은 반드시 SafetyGate.check()를 통과해야 한다 (docs/SAFETY.md).

수동 명령·백테스트를 포함한 어떠한 경로도 이 관문을 우회할 수 없다.
"""

from core.config import settings
from core.db import store as db
from core.events import calendar
from core.fund.manager import fund_manager
from core.models import GateResult, Order, RunMode
from core.toss import market as toss_market


class SafetyGate:
    async def check(self, order: Order, mode: RunMode) -> GateResult:
        # 0. 수량·금액은 반드시 양수 — 0 이하 값은 5번 조건(amount_krw > MAX_SINGLE_ORDER_KRW)의
        # 상한 비교를 무의미하게 만들어 사실상 한도를 우회하므로, 다른 경로(수동 주문 API 등)의
        # 입력 검증 누락 여부와 무관하게 Safety Gate 자체에서 막는다.
        if order.quantity <= 0 or order.amount_krw <= 0:
            return GateResult.reject("주문 수량·금액은 0보다 커야 합니다")

        # 1. 긴급 정지 해제 상태
        if settings.EMERGENCY_STOP:
            return GateResult.reject("EMERGENCY_STOP 활성화")

        # 2. 시장별 정지 플래그
        if mode.market == "KR" and settings.KR_STOP:
            return GateResult.reject("KR_STOP 활성화")
        if mode.market == "US" and settings.US_STOP:
            return GateResult.reject("US_STOP 활성화")

        # 3. 일일 손실 한도 미초과 (시뮬레이션: simulation_daily_pnl / 실전: trades)
        daily_loss = await self._get_daily_loss(mode)
        if daily_loss >= settings.MAX_DAILY_LOSS_KRW:
            return GateResult.reject(f"일일 손실 한도 초과: {daily_loss:,} KRW")

        # 4. 단일 종목 비중 상한
        position_ratio = await self._get_position_ratio(order.symbol, mode)
        if position_ratio > settings.MAX_POSITION_RATIO:
            return GateResult.reject(f"종목 비중 상한 초과: {position_ratio:.1%}")

        # 5. 1회 주문 금액 상한
        if order.amount_krw > settings.MAX_SINGLE_ORDER_KRW:
            return GateResult.reject(f"주문 금액 초과: {order.amount_krw:,} KRW")

        # 6. 현금 버퍼 최소 유지
        buffer = await self._get_cash_buffer(mode)
        if buffer < settings.INITIAL_SEED_KRW * 0.05:
            return GateResult.reject("현금 버퍼 부족")

        # 7. KR 종목: VI 발동·투자경고·정리매매 없음
        if order.market == "KR":
            warnings = await self._get_stock_warnings(order.symbol)
            if warnings.get("has_restriction"):
                return GateResult.reject(f"거래 제한 종목: {warnings.get('reason')}")

        # 8. 장 운영 중 확인
        if not await self._is_market_open(order.market):
            return GateResult.reject("장 마감 시간")

        # 9. 미국장 금액 주문은 정규장만
        if order.market == "US" and order.order_type == "AMOUNT":
            if not await self._is_regular_session("US"):
                return GateResult.reject("금액 주문은 정규장만 허용")

        # 10. 주문 ID 중복 없음
        if await self._order_id_exists(order.client_order_id):
            return GateResult.reject("중복 주문 ID")

        # 11. 고위험 이벤트 당일: 주문 한도 50% 자동 축소
        if await self._has_high_risk_event_today():
            limit = settings.MAX_SINGLE_ORDER_KRW * 0.5
            if order.amount_krw > limit:
                return GateResult.reject(f"고위험 이벤트 당일 한도 초과: {limit:,} KRW")

        return GateResult.approve()

    async def _get_daily_loss(self, mode: RunMode) -> int:
        """LIVE → trades, SIMULATION → simulation_daily_pnl 기준 (docs/SAFETY.md)."""
        return await db.get_daily_loss(mode)

    async def _get_position_ratio(self, symbol: str, mode: RunMode) -> float:
        """SIMULATION에서는 FundManager가 가상 포지션 기준으로 계산한다."""
        return await fund_manager.get_position_ratio(symbol, mode.mode)

    async def _get_cash_buffer(self, mode: RunMode) -> float:
        return await fund_manager.get_cash_buffer_krw(mode.mode)

    async def _get_stock_warnings(self, symbol: str) -> dict:
        return await toss_market.get_stock_warnings(symbol)

    async def _is_market_open(self, market: str) -> bool:
        """core/toss/market.py의 `is_market_open`으로 위임 — Redis `market_open:{market}` 캐시 공유."""
        return await toss_market.is_market_open(market)  # type: ignore[arg-type]

    async def _is_regular_session(self, market: str) -> bool:
        return await toss_market.is_regular_session(market)  # type: ignore[arg-type]

    async def _order_id_exists(self, client_order_id: str) -> bool:
        return await db.order_id_exists(client_order_id)

    async def _has_high_risk_event_today(self) -> bool:
        return await calendar.has_high_risk_event_today()


safety_gate = SafetyGate()
