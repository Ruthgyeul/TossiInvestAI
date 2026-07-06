"""가상 포트폴리오 상태를 메모리 + DB에서 관리한다 (docs/LOGGING.md).

SIMULATION 모드 전용이며 실전 `positions`/`trades` 테이블과 절대 혼용하지 않는다.
"""

from dataclasses import dataclass

from core.config import settings
from core.db import store as db


@dataclass
class SimPosition:
    qty: int
    avg_price: float


class SimulationPortfolio:
    def __init__(self, cash: float = settings.INITIAL_SEED_KRW) -> None:
        self.cash = cash
        self.positions: dict[str, SimPosition] = {}

    async def apply_buy(
        self, symbol: str, qty: int, fill_price: float, commission: float, market: str
    ) -> None:
        """가상 매수 체결 처리."""
        cost = fill_price * qty + commission
        self.cash -= cost
        if symbol in self.positions:
            old = self.positions[symbol]
            total_qty = old.qty + qty
            avg_price = (old.qty * old.avg_price + qty * fill_price) / total_qty
            self.positions[symbol] = SimPosition(qty=total_qty, avg_price=avg_price)
        else:
            self.positions[symbol] = SimPosition(qty=qty, avg_price=fill_price)
        await db.upsert("simulation_positions", vars(self.positions[symbol]) | {"symbol": symbol, "market": market})

    async def apply_sell(self, symbol: str, qty: int, fill_price: float, commission: float) -> float:
        """가상 매도 체결 처리. 실현 손익을 반환한다."""
        pos = self.positions[symbol]
        realized_pnl = (fill_price - pos.avg_price) * qty - commission
        self.cash += fill_price * qty - commission
        if pos.qty == qty:
            del self.positions[symbol]
        else:
            pos.qty -= qty
        await db.insert("simulation_trades", {"symbol": symbol, "pnl_krw": realized_pnl, "mode": "SIMULATION"})
        return realized_pnl

    def get_total_value(self, current_prices: dict[str, float]) -> float:
        """총 자산 = 현금 + 보유 종목 평가액."""
        holdings_value = sum(
            pos.qty * current_prices.get(sym, pos.avg_price)
            for sym, pos in self.positions.items()
        )
        return self.cash + holdings_value

    def get_return_rate(self, current_prices: dict[str, float]) -> float:
        """시드 대비 수익률."""
        return (self.get_total_value(current_prices) - settings.INITIAL_SEED_KRW) / settings.INITIAL_SEED_KRW
