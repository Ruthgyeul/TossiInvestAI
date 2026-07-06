"""자금 배분·재투자·API 비용 추적 (docs/FUND_MANAGER.md).

INITIAL_SEED_KRW는 손익 계산 기준점이므로 최초 설정 이후 절대 변경하지 않는다.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from core.config import settings
from core.db import store as db
from core.models import Mode
from core.toss import account as toss_account
from core.toss import market as toss_market

_KRW_PER_USD = 1382.0  # 실시간 환율로 교체 가능
_WEEKLY_REINVEST_RATIO = 0.80
_MAX_CASH_BUFFER_RATIO = 0.20


@dataclass
class RebalanceResult:
    api_cost_covered_krw: int
    reinvested_krw: int
    buffer_added_krw: int


class FundManager:
    async def _load_holdings_and_cash(self, mode: Mode) -> tuple[list[dict], float]:
        """LIVE는 실계좌, SIMULATION/DRY_RUN은 가상 포트폴리오 기준 보유종목·현금을 반환한다.

        SIMULATION 중 실전 계좌 데이터를 참조하면 Safety Gate의 종목당 상한·현금버퍼
        게이트가 실계좌 기준으로 계산돼버린다 (CLAUDE.md 규칙 11 — 실전/시뮬 DB 혼용 금지).
        """
        if mode == "LIVE":
            holdings = await toss_account.get_holdings()
            cash = await toss_account.get_buying_power()
            return holdings, cash

        from core.simulation.portfolio import SimulationPortfolio

        portfolio = await SimulationPortfolio.load()
        holdings = [
            {"symbol": symbol, "market": pos.market, "quantity": pos.qty, "avgPrice": pos.avg_price}
            for symbol, pos in portfolio.positions.items()
        ]
        return holdings, portfolio.cash

    async def _get_position_value_krw(self, symbol: str, mode: Mode = "LIVE") -> float:
        """특정 종목의 현재 평가액 (KRW 환산)."""
        holdings, _ = await self._load_holdings_and_cash(mode)
        holding = next((h for h in holdings if h["symbol"] == symbol), None)
        if holding is None:
            return 0.0

        price_data = await toss_market.get_price(symbol)
        value = holding["quantity"] * price_data["price"]
        if holding["market"] == "US":
            value *= await toss_market.get_exchange_rate()
        return float(value)

    async def _get_holdings_value_krw(self, holdings: list[dict]) -> float:
        """보유 종목 전체 평가액 (KRW 환산)."""
        exchange_rate = await toss_market.get_exchange_rate()

        total = 0.0
        for holding in holdings:
            price_data = await toss_market.get_price(holding["symbol"])
            value = holding["quantity"] * price_data["price"]
            if holding["market"] == "US":
                value *= exchange_rate
            total += value
        return total

    async def get_total_value_krw(self, mode: Mode = "LIVE") -> float:
        """총 자산 KRW 환산 (보유 주식 시가 + 현금). mode에 따라 실계좌/가상 포트폴리오를 사용한다."""
        holdings, cash = await self._load_holdings_and_cash(mode)
        holdings_value = await self._get_holdings_value_krw(holdings)
        return holdings_value + cash

    async def get_cash_buffer_krw(self, mode: Mode = "LIVE") -> float:
        """현금 버퍼 잔고 = 총 자산의 CASH_BUFFER_RATIO."""
        total_value = await self.get_total_value_krw(mode)
        return total_value * settings.CASH_BUFFER_RATIO

    async def get_operating_funds_krw(self, mode: Mode = "LIVE") -> float:
        """운용 자금 = 총 자산 - 현금 버퍼."""
        total_value = await self.get_total_value_krw(mode)
        return total_value * (1 - settings.CASH_BUFFER_RATIO)

    async def get_position_ratio(self, symbol: str, mode: Mode = "LIVE") -> float:
        """특정 종목의 운용 자금 대비 비중."""
        operating_funds = await self.get_operating_funds_krw(mode)
        if operating_funds <= 0:
            return 0.0
        position_value = await self._get_position_value_krw(symbol, mode)
        return position_value / operating_funds

    async def can_allocate(self, amount_krw: float, symbol: str, mode: Mode = "LIVE") -> tuple[bool, str]:
        """주문 가능 여부 판단 (종목당 상한 MAX_POSITION_RATIO 체크)."""
        operating_funds = await self.get_operating_funds_krw(mode)
        if operating_funds <= 0:
            return False, "운용 자금 부족"

        current_position_krw = await self._get_position_value_krw(symbol, mode)
        projected_ratio = (current_position_krw + amount_krw) / operating_funds
        if projected_ratio > settings.MAX_POSITION_RATIO:
            return False, f"종목당 상한 초과: {projected_ratio:.1%}"

        return True, "허용"

    async def weekly_rebalance(self, mode: Mode = "LIVE") -> RebalanceResult:
        """매주 월요일 장 시작 전 자동 실행. 코드 외부에서 임의 변경 불가.

        STEP 1. Claude API 사용료 추정 → 현금 버퍼에서 확보
        STEP 2. 남은 순수익의 80% → 운용 자금 재투자
        STEP 3. 남은 순수익의 20% → 현금 버퍼 적립
        STEP 4. 현금 버퍼가 총 자산의 20% 초과 시 초과분을 운용 자금으로 이동
        """
        api_cost_krw = int(await self.estimated_api_cost_krw())
        net_profit_krw = await db.get_weekly_net_profit_krw(mode)
        remaining = max(net_profit_krw - api_cost_krw, 0)

        reinvested_krw = int(remaining * _WEEKLY_REINVEST_RATIO)
        buffer_added_krw = remaining - reinvested_krw

        total_value = await self.get_total_value_krw(mode)
        cash_buffer = await self.get_cash_buffer_krw(mode) + buffer_added_krw
        max_buffer = total_value * _MAX_CASH_BUFFER_RATIO
        if cash_buffer > max_buffer:
            overflow = cash_buffer - max_buffer
            reinvested_krw += int(overflow)
            buffer_added_krw -= int(overflow)

        result = RebalanceResult(
            api_cost_covered_krw=api_cost_krw,
            reinvested_krw=reinvested_krw,
            buffer_added_krw=buffer_added_krw,
        )
        # 계산만 하고 끝나면 "코드 외부에서 임의 변경 불가"(docs/FUND_MANAGER.md)를 보장할 수
        # 없다 — 매주 실행 결과를 영구 기록해 감사 가능한 재배분 이력으로 남긴다.
        await db.insert(
            "fund_rebalances",
            {
                "mode": mode,
                "total_value_krw": int(total_value),
                "api_cost_covered_krw": result.api_cost_covered_krw,
                "reinvested_krw": result.reinvested_krw,
                "buffer_added_krw": result.buffer_added_krw,
            },
        )
        return result

    async def get_last_rebalance(self, mode: Mode = "LIVE") -> dict | None:
        """가장 최근 주간 재배분 기록 (Discord `/fund` 등에서 참고)."""
        rows = await db.fetch_all(
            "fund_rebalances", {"mode": mode}, order_by="created_at", descending=True, limit=1
        )
        return rows[0] if rows else None

    async def record_api_usage(
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
            + cache_read_tokens * p_in * 0.10  # hit
            + output_tokens * p_out
        )
        await self._insert_api_usage(
            model,
            cost_usd,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_write_tokens,
        )

    async def _insert_api_usage(
        self,
        model: str,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
    ) -> None:
        await db.insert(
            "api_usage",
            {
                "model": model,
                "cost_usd": cost_usd,
                "cost_krw": int(cost_usd * _KRW_PER_USD),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
            },
        )

    async def estimated_api_cost_krw(self) -> float:
        """이번 달 추정 API 비용 (KRW 환산)."""
        return await db.get_api_usage_month_krw()

    async def get_portfolio_status(self, mode: Mode, market: str | None = None) -> dict:
        """`/api/v1/status`용 PortfolioStatus (discord-bot embeds/status.ts와 매칭).

        market이 주어지면 holdings만 해당 시장으로 필터링한다 — 총 자산·현금 버퍼는
        KR·US가 하나의 자금 풀을 공유하므로(docs/FUND_MANAGER.md) 전체 계정 기준을 유지한다.
        """
        exchange_rate = await toss_market.get_exchange_rate()
        raw_holdings, cash = await self._load_holdings_and_cash(mode)

        holdings = []
        holdings_value_krw = 0.0
        for h in raw_holdings:
            price_data = await toss_market.get_price(h["symbol"])
            current_price = float(price_data["price"])
            avg_price = float(h.get("avgPrice", current_price))
            quantity = int(h["quantity"])

            value = quantity * current_price
            if h["market"] == "US":
                value *= exchange_rate
            holdings_value_krw += value

            holdings.append(
                {
                    "symbol": h["symbol"],
                    "market": h["market"],
                    "quantity": quantity,
                    "avgPrice": avg_price,
                    "currentPrice": current_price,
                    "pnlPct": (current_price - avg_price) / avg_price if avg_price else 0.0,
                }
            )

        total_value_krw = holdings_value_krw + cash
        today_pnl_krw = await db.get_today_realized_pnl_krw(mode)
        cumulative_pnl_krw = int(total_value_krw - settings.INITIAL_SEED_KRW)

        if market is not None:
            holdings = [h for h in holdings if h["market"] == market]

        return {
            "totalValueKrw": int(total_value_krw),
            "todayPnlKrw": today_pnl_krw,
            "todayPnlPct": today_pnl_krw / settings.INITIAL_SEED_KRW,
            "cumulativePnlKrw": cumulative_pnl_krw,
            "cumulativePnlPct": cumulative_pnl_krw / settings.INITIAL_SEED_KRW,
            "cashBufferKrw": int(total_value_krw * settings.CASH_BUFFER_RATIO),
            "cashKrw": int(cash),
            "holdings": holdings,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }


fund_manager = FundManager()
