"""CRUD 함수. core/db/models.py의 테이블에 대한 단일 접근 경로 (asyncpg + SQLAlchemy async)."""

from typing import Any

from core.models import Mode, RunMode


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
