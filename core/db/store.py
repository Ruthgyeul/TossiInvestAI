"""CRUD 함수. core/db/models.py의 테이블에 대한 단일 접근 경로 (asyncpg + SQLAlchemy async)."""

from typing import Any

from core.models import Market, Mode, RunMode


async def insert(table: str, values: dict[str, Any]) -> None:
    raise NotImplementedError


async def upsert(table: str, values: dict[str, Any]) -> None:
    raise NotImplementedError


async def get_daily_loss(mode: RunMode) -> int:
    """SafetyGate에서 사용. LIVE → trades, SIMULATION → simulation_daily_pnl 기준."""
    raise NotImplementedError


async def order_id_exists(client_order_id: str) -> bool:
    raise NotImplementedError


async def get_api_usage_month_krw(mode: Mode = "LIVE") -> int:
    raise NotImplementedError


async def get_weekly_net_profit_krw(mode: Mode = "LIVE") -> int:
    """FundManager.weekly_rebalance에서 사용. 전주 실현 손익 + 평가 손익 변화 합산."""
    raise NotImplementedError


async def get_long_term_memory(market: Market) -> dict[str, Any]:
    """gateway/claude.py L2 캐시 레이어에서 사용 (docs/BIN.md).

    30일 거래 히스토리(trade_count, win_rate) · 최근 reflections 요약(reflection_summary) ·
    종목별 수익 통계(symbol_stats)를 조회해 반환한다.
    """
    raise NotImplementedError
