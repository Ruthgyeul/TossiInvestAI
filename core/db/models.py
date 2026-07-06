"""SQLAlchemy ORM 모델. docs/ARCHITECTURE.md의 PostgreSQL 스키마 표에 대응한다.

시뮬레이션 테이블(simulation_*)은 실전 테이블과 완전히 분리되어 있으며 절대 혼용하지 않는다
(docs/SAFETY.md, docs/LOGGING.md). 공용 테이블은 모두 `mode` 컬럼을 포함한다.
"""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class _ModeMixin:
    """LIVE | SIMULATION | DRY_RUN — 공용 테이블에 공통 적용."""

    mode: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("mode IN ('LIVE', 'SIMULATION', 'DRY_RUN')"),
        default="SIMULATION",
    )


class Trade(Base):
    """체결된 거래 전체 내역 (실전)."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    action: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int]
    fill_price: Mapped[float] = mapped_column(Numeric)
    commission_krw: Mapped[int]
    pnl_krw: Mapped[int | None]
    decision_id: Mapped[str | None] = mapped_column(String(36))
    order_id: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Order(Base):
    """주문 이력 (미체결 포함)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(50), unique=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Position(Base):
    """현재 보유 포지션 (매수 시 환율 포함)."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("symbol", "market", name="uq_positions_symbol_market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    quantity: Mapped[int]
    avg_price: Mapped[float] = mapped_column(Numeric)
    buy_exchange_rate: Mapped[float | None] = mapped_column(Numeric)


class DecisionRecord(_ModeMixin, Base):
    """AI 의사결정 히스토리 JSON."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(36), unique=True)
    market: Mapped[str] = mapped_column(String(2))
    strategy_version: Mapped[str] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(30))
    model_used: Mapped[str] = mapped_column(String(50))
    state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperTrade(Base):
    """모의투자 체결 내역."""

    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    strategy_version: Mapped[str] = mapped_column(String(20))
    pnl_krw: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailyPnl(Base):
    """일별 손익 (실전)."""

    __tablename__ = "daily_pnl"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    realized_pnl_krw: Mapped[int]
    unrealized_pnl_krw: Mapped[int]


class ApiUsage(Base):
    """Claude API 토큰·비용 기록."""

    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(50))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    cache_write_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric)
    cost_krw: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Watchlist(Base):
    """관심 종목 및 우선순위."""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True)
    market: Mapped[str] = mapped_column(String(2))
    priority: Mapped[int] = mapped_column(default=0)


class StrategyVersion(Base):
    """프롬프트·전략 버전 기록."""

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_version: Mapped[str] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(30))
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reflection(_ModeMixin, Base):
    """일일 자기평가 리포트."""

    __tablename__ = "reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(2))
    content_md: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MarketEvent(Base):
    """시장 이벤트 캘린더 (FOMC·CPI·실적발표 등)."""

    __tablename__ = "market_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30))
    market: Mapped[str] = mapped_column(String(2))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_high_risk: Mapped[bool] = mapped_column(default=False)


class SafetyRejection(_ModeMixin, Base):
    """Safety Gate 거부 이력."""

    __tablename__ = "safety_rejections"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulationTrade(Base):
    """시뮬레이션 가상 체결 내역."""

    __tablename__ = "simulation_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    action: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int]
    fill_price: Mapped[float] = mapped_column(Numeric)
    commission_krw: Mapped[int]
    pnl_krw: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulationPosition(Base):
    """시뮬레이션 가상 보유 포지션."""

    __tablename__ = "simulation_positions"
    __table_args__ = (
        UniqueConstraint("symbol", "market", name="uq_simulation_positions_symbol_market"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    quantity: Mapped[int]
    avg_price: Mapped[float] = mapped_column(Numeric)


class SimulationDailyPnl(Base):
    """시뮬레이션 가상 일별 손익."""

    __tablename__ = "simulation_daily_pnl"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    realized_pnl_krw: Mapped[int]
    unrealized_pnl_krw: Mapped[int]


class SimulationPortfolioSnapshot(Base):
    """시뮬레이션 포트폴리오 스냅샷."""

    __tablename__ = "simulation_portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_value_krw: Mapped[int]
    cash_krw: Mapped[int]
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
