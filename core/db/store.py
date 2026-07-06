"""CRUD 함수. core/db/models.py의 테이블에 대한 단일 접근 경로 (asyncpg + SQLAlchemy async)."""

from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from core.db.models import (
    ApiUsage,
    Base,
    ControlFlags,
    DailyPnl,
    DecisionRecord,
    FundRebalance,
    LivePortfolioSnapshot,
    MarketEvent,
    Order as OrderRow,
    PaperTrade,
    Reflection,
    SafetyRejection,
    SimulationDailyPnl,
    SimulationPortfolioSnapshot,
    SimulationPosition,
    SimulationTrade,
    StrategyVersion,
    Trade,
    Watchlist,
)
from core.models import Market, Mode, RunMode

_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
_SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)

_MODELS: list[type[DeclarativeBase]] = [
    Trade,
    OrderRow,
    DecisionRecord,
    PaperTrade,
    DailyPnl,
    ApiUsage,
    Watchlist,
    StrategyVersion,
    Reflection,
    MarketEvent,
    SafetyRejection,
    SimulationTrade,
    SimulationPosition,
    SimulationDailyPnl,
    SimulationPortfolioSnapshot,
    ControlFlags,
    FundRebalance,
    LivePortfolioSnapshot,
]
# Position은 core.db.models.Position이지만 core.models.Order와 이름이 겹쳐 별칭 처리한다.
from core.db.models import Position as PositionRow  # noqa: E402

_MODELS.append(PositionRow)
_MODEL_BY_TABLE: dict[str, type[DeclarativeBase]] = {m.__tablename__: m for m in _MODELS}  # type: ignore[attr-defined]

# upsert 시 충돌 판정에 사용할 컬럼 (테이블에 실제 UNIQUE 제약이 걸려 있어야 한다).
_CONFLICT_COLUMNS: dict[str, list[str]] = {
    "positions": ["symbol", "market"],
    "simulation_positions": ["symbol", "market"],
    "watchlist": ["symbol"],
}


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    async with _SessionFactory() as session:
        yield session


async def init_models() -> None:
    """개발·초기 구동 시 테이블을 생성한다 (docs/CODING_RULES.md Phase 1 "DB 스키마 생성")."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {c.key: getattr(row, c.key) for c in row.__table__.columns}


def _model_for(table: str) -> type[DeclarativeBase]:
    model = _MODEL_BY_TABLE.get(table)
    if model is None:
        raise ValueError(f"알 수 없는 테이블: {table}")
    return model


async def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
    model = _model_for(table)
    row = dict(values)
    if hasattr(model, "created_at") and "created_at" not in row:
        row["created_at"] = datetime.now(timezone.utc)

    async with _session() as session:
        obj = model(**row)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return _row_to_dict(obj)


async def upsert(table: str, values: dict[str, Any]) -> None:
    model = _model_for(table)
    conflict_columns = _CONFLICT_COLUMNS.get(table, ["id"])

    stmt = pg_insert(model).values(**values)
    update_columns = {
        key: getattr(stmt.excluded, key) for key in values if key not in conflict_columns
    }
    stmt = stmt.on_conflict_do_update(index_elements=conflict_columns, set_=update_columns)

    async with _session() as session:
        await session.execute(stmt)
        await session.commit()


async def fetch_all(
    table: str,
    filters: dict[str, Any] | None = None,
    *,
    order_by: str | None = None,
    descending: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    model = _model_for(table)
    stmt = select(model)
    for key, value in (filters or {}).items():
        stmt = stmt.where(getattr(model, key) == value)
    if order_by is not None:
        column = getattr(model, order_by)
        stmt = stmt.order_by(column.desc() if descending else column.asc())
    if limit is not None:
        stmt = stmt.limit(limit)

    async with _session() as session:
        result = await session.execute(stmt)
        return [_row_to_dict(row) for row in result.scalars().all()]


async def fetch_one(table: str, filters: dict[str, Any]) -> dict[str, Any] | None:
    rows = await fetch_all(table, filters, limit=1)
    return rows[0] if rows else None


async def delete(table: str, filters: dict[str, Any]) -> None:
    model = _model_for(table)
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)

    async with _session() as session:
        result = await session.execute(stmt)
        for row in result.scalars().all():
            await session.delete(row)
        await session.commit()


def _trade_model_for_mode(mode: Mode) -> type[DeclarativeBase]:
    return Trade if mode == "LIVE" else SimulationTrade


async def get_today_realized_pnl_krw(mode: Mode) -> int:
    """오늘(KST 자정 이후, UTC 기준 근사) 실현 손익 합계 — 부호를 포함한다."""
    model = _trade_model_for_mode(mode)
    today_start_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with _session() as session:
        stmt = select(model).where(model.created_at >= today_start_utc)  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return sum(row.pnl_krw or 0 for row in rows)  # type: ignore[attr-defined,misc]


async def get_daily_loss(mode: RunMode) -> int:
    """SafetyGate에서 사용. LIVE → trades, SIMULATION/DRY_RUN → simulation_trades 기준.

    오늘 실현 손익 합계가 음수면 그 절대값을, 아니면 0을 반환한다.
    """
    total_pnl = await get_today_realized_pnl_krw(mode.mode)
    return -total_pnl if total_pnl < 0 else 0


async def order_id_exists(client_order_id: str) -> bool:
    return await fetch_one("orders", {"client_order_id": client_order_id}) is not None


async def get_api_usage_month_summary() -> dict[str, Any]:
    """ApiUsage는 mode 컬럼이 없다 — 이번 달 전체 Claude API 호출·비용을 합산한다."""
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    async with _session() as session:
        stmt = select(ApiUsage).where(ApiUsage.created_at >= month_start)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return {
        "cost_krw": sum(row.cost_krw for row in rows),
        "cost_usd": sum(row.cost_usd for row in rows),
        "call_count": len(rows),
    }


async def get_api_usage_month_krw(mode: Mode = "LIVE") -> int:
    summary = await get_api_usage_month_summary()
    return int(summary["cost_krw"])


async def get_today_trades(mode: Mode, market: Market) -> list[dict[str, Any]]:
    """core/trading/reflection.py에서 사용. 오늘(KST 자정 이후, UTC 기준 근사) 체결 내역."""
    model = _trade_model_for_mode(mode)
    today_start_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with _session() as session:
        stmt = select(model).where(
            model.market == market,  # type: ignore[attr-defined]
            model.created_at >= today_start_utc,  # type: ignore[attr-defined]
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [_row_to_dict(row) for row in rows]


async def get_today_rejections(market: Market) -> list[dict[str, Any]]:
    """core/trading/reflection.py에서 사용. 오늘(KST 자정 이후, UTC 기준 근사) Safety Gate 거부 내역."""
    today_start_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with _session() as session:
        stmt = select(SafetyRejection).where(
            SafetyRejection.market == market,
            SafetyRejection.created_at >= today_start_utc,
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [_row_to_dict(row) for row in rows]


async def get_weekly_net_profit_krw(mode: Mode = "LIVE") -> int:
    """FundManager.weekly_rebalance에서 사용. 최근 7일 실현 손익 합계."""
    model = _trade_model_for_mode(mode)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    async with _session() as session:
        stmt = select(model).where(model.created_at >= week_ago)  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return sum(row.pnl_krw or 0 for row in rows)  # type: ignore[attr-defined,misc]


async def get_control_flags() -> dict[str, bool]:
    """core/main.py 기동 시 EMERGENCY_STOP/KR_STOP/US_STOP을 복원한다 (docs/SAFETY.md)."""
    async with _session() as session:
        stmt = select(ControlFlags).where(ControlFlags.id == 1)
        result = await session.execute(stmt)
        row = result.scalars().first()

    if row is None:
        return {"emergency_stop": False, "kr_stop": False, "us_stop": False}
    return {
        "emergency_stop": row.emergency_stop,
        "kr_stop": row.kr_stop,
        "us_stop": row.us_stop,
    }


async def set_control_flags(
    *, emergency_stop: bool, kr_stop: bool, us_stop: bool
) -> None:
    """`/stop`·`/resume` 즉시 DB에 반영한다 — 프로세스 재시작에도 상태가 유지되도록."""
    stmt = pg_insert(ControlFlags).values(
        id=1,
        emergency_stop=emergency_stop,
        kr_stop=kr_stop,
        us_stop=us_stop,
        updated_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "emergency_stop": stmt.excluded.emergency_stop,
            "kr_stop": stmt.excluded.kr_stop,
            "us_stop": stmt.excluded.us_stop,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    async with _session() as session:
        await session.execute(stmt)
        await session.commit()


async def get_simulation_started_at() -> datetime | None:
    """SIMULATION이 연속으로 유지된 시작 시각 (docs/SAFETY.md "실전 전환 전 2주 이상 필수")."""
    async with _session() as session:
        stmt = select(ControlFlags.simulation_started_at).where(ControlFlags.id == 1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def set_simulation_started_at(started_at: datetime | None) -> None:
    """SIMULATION 시작 시각을 기록/초기화한다. 프로세스 재시작으로 리허설 기간이
    소리 없이 리셋되지 않도록 DB에 영속화한다."""
    stmt = pg_insert(ControlFlags).values(
        id=1, simulation_started_at=started_at, updated_at=datetime.now(timezone.utc)
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "simulation_started_at": stmt.excluded.simulation_started_at,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    async with _session() as session:
        await session.execute(stmt)
        await session.commit()


async def get_recent_simulation_snapshots(limit: int = 30) -> list[dict[str, Any]]:
    """core/report/chart.py 시계열 그래프(자산 추이·수익률)에서 사용.

    core/trading/loop.py `publish_status_update`가 매 루프마다 적재하는
    simulation_portfolio_snapshots를 오래된 순으로 반환한다.
    """
    rows = await fetch_all(
        "simulation_portfolio_snapshots", order_by="snapshot_at", descending=True, limit=limit
    )
    return list(reversed(rows))


async def get_recent_live_snapshots(limit: int = 30) -> list[dict[str, Any]]:
    """get_recent_simulation_snapshots의 LIVE 대응 — live_portfolio_snapshots에서 조회한다."""
    rows = await fetch_all(
        "live_portfolio_snapshots", order_by="snapshot_at", descending=True, limit=limit
    )
    return list(reversed(rows))


async def get_long_term_memory(market: Market) -> dict[str, Any]:
    """gateway/claude.py L2 캐시 레이어에서 사용 (docs/BIN.md).

    30일 거래 히스토리(trade_count, win_rate) · 최근 reflections 요약(reflection_summary) ·
    종목별 수익 통계(symbol_stats)를 조회해 반환한다.
    """
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    async with _session() as session:
        trades: Sequence[Any] = []
        for model in (Trade, SimulationTrade):
            stmt = select(model).where(
                model.market == market,  # type: ignore[attr-defined]
                model.created_at >= thirty_days_ago,  # type: ignore[attr-defined]
            )
            result = await session.execute(stmt)
            trades = [*trades, *result.scalars().all()]

        reflection_stmt = (
            select(Reflection)
            .where(Reflection.market == market)
            .order_by(Reflection.created_at.desc())
            .limit(1)
        )
        reflection_result = await session.execute(reflection_stmt)
        latest_reflection = reflection_result.scalars().first()

    trade_count = len(trades)
    win_count = sum(1 for t in trades if (t.pnl_krw or 0) > 0)
    win_rate = win_count / trade_count if trade_count else 0.0

    symbol_stats: dict[str, dict[str, Any]] = {}
    for t in trades:
        stats = symbol_stats.setdefault(t.symbol, {"pnl_krw": 0, "trade_count": 0})
        stats["pnl_krw"] += t.pnl_krw or 0
        stats["trade_count"] += 1

    reflection_summary = "없음"
    if latest_reflection is not None:
        reflection_summary = latest_reflection.content_md.strip().splitlines()[0][:200]

    return {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "reflection_summary": reflection_summary,
        "symbol_stats": symbol_stats,
    }


async def get_latest_deployed_strategy_version(market: Market | None = None) -> dict[str, Any] | None:
    """가장 최근 승인·배포된 버전 (docs/SELF_IMPROVEMENT.md "approved_by가 비어 있는 레코드는
    미승인 상태로 간주한다") — GET /api/v1/version이 "현재 버전"으로 보여줄 유일한 소스."""
    async with _session() as session:
        stmt = select(StrategyVersion).where(StrategyVersion.approved_by.is_not(None))
        if market is not None:
            stmt = stmt.where(StrategyVersion.market == market)
        stmt = stmt.order_by(StrategyVersion.deployed_at.desc()).limit(1)
        result = await session.execute(stmt)
        row = result.scalars().first()
    return _row_to_dict(row) if row is not None else None


async def get_pending_strategy_candidates(market: Market | None = None) -> list[dict[str, Any]]:
    """개발자 승인을 기다리는 후보 (approved_by IS NULL) — `/version candidates`."""
    async with _session() as session:
        stmt = select(StrategyVersion).where(StrategyVersion.approved_by.is_(None))
        if market is not None:
            stmt = stmt.where(StrategyVersion.market == market)
        stmt = stmt.order_by(StrategyVersion.proposed_at.desc())
        result = await session.execute(stmt)
        rows = result.scalars().all()
    return [_row_to_dict(row) for row in rows]


async def approve_strategy_version(version_id: int, approved_by: str) -> dict[str, Any] | None:
    """후보를 승인해 배포 상태로 전환한다 — approved_by + deployed_at(지금)을 채운다."""
    async with _session() as session:
        stmt = select(StrategyVersion).where(StrategyVersion.id == version_id)
        result = await session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return None
        row.approved_by = approved_by
        row.deployed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        return _row_to_dict(row)


async def get_deployed_strategy_version_by_name(strategy_version: str) -> dict[str, Any] | None:
    """롤백 대상 조회 — 과거에 실제로 승인·배포된 이력이 있는 버전만 롤백 가능하다."""
    async with _session() as session:
        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_version == strategy_version)
            .where(StrategyVersion.approved_by.is_not(None))
            .order_by(StrategyVersion.deployed_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.scalars().first()
    return _row_to_dict(row) if row is not None else None
