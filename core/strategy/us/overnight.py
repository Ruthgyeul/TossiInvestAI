"""US 오버나이트 전략 — 정규장 마감 보유 포지션의 익일 갭 대응.

개발자 결정(익일 시가 갭 = 전일 종가 대비 당일 시가의 등락률)에 따라 아래 규칙으로 동작한다.
신규 매수(BUY)는 다루지 않는다 — 이미 보유 중인 포지션의 리스크 관리 전용이다.

1. 갭 상승 5% 이상 → 차익 실현 매도 (단기 차익 매물 출회 위험).
2. 갭 상승(0~5%) 후 현재가가 당일 시가 아래로 이탈 → 추세 반전으로 보고 손절 매도.
3. 갭 하락 5% 이상 → 추가 손실 방지를 위한 원칙적 손절 매도(성급한 추가 매수는 하지 않음 —
   이 전략은 매수 신호를 내지 않으므로 자동으로 지켜진다).
4. 그 외(갭 없음/소폭 갭)는 신호를 내지 않는다 — 바닥 확인 전 성급한 판단을 피한다.
"""

from core.models import Decision, StateSnapshot
from core.strategy.base import BaseStrategy

_GAP_UP_TAKE_PROFIT_PCT = 5.0
_GAP_DOWN_STOP_LOSS_PCT = -5.0


class OvernightStrategy(BaseStrategy):
    version = "v1.0.0"

    async def generate_signal(self, state: StateSnapshot) -> Decision | None:
        held_symbols = {h["symbol"]: h for h in state.portfolio.get("holdings", [])}

        for symbol, holding in held_symbols.items():
            data = state.prices.get(symbol)
            if data is None:
                continue

            gap_pct = data.get("gap_pct")
            if gap_pct is None:
                continue

            quantity = int(holding["quantity"])
            if quantity <= 0:
                continue

            if gap_pct >= _GAP_UP_TAKE_PROFIT_PCT:
                return self.make_decision(
                    symbol=symbol,
                    action="SELL",
                    quantity=quantity,
                    price=None,
                    reason=f"익일 갭 상승 {gap_pct:.1f}% — 단기 차익 실현",
                )

            day_open = data.get("day_open")
            price = data.get("price")
            if 0 < gap_pct < _GAP_UP_TAKE_PROFIT_PCT and day_open and price and price < day_open:
                return self.make_decision(
                    symbol=symbol,
                    action="SELL",
                    quantity=quantity,
                    price=None,
                    reason=f"익일 갭 상승 {gap_pct:.1f}% 후 시가({day_open:,.0f}) 이탈 — 추세 반전 손절",
                )

            if gap_pct <= _GAP_DOWN_STOP_LOSS_PCT:
                return self.make_decision(
                    symbol=symbol,
                    action="SELL",
                    quantity=quantity,
                    price=None,
                    reason=f"익일 갭 하락 {gap_pct:.1f}% — 추가 손실 방지 원칙적 손절",
                )

        return None
