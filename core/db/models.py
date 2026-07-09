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
    """주문 이력 (미체결 포함). docs/INTERNAL_API.md `GET /api/v1/orders` 응답과 매칭된다."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(50), unique=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(2))
    action: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int]
    price: Mapped[float | None] = mapped_column(Numeric)
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
    # 개발자가 Discord로 직접 지적한 오판 사례 (docs/SELF_IMPROVEMENT.md "개선 후보의 출처").
    actual_outcome: Mapped[str | None]
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
    """프롬프트·전략 버전 기록 (docs/SELF_IMPROVEMENT.md "버전 관리 및 롤백").

    개발자 승인 없이 deployed_at으로 표시하지 않는다 — approved_by가 비어 있는 레코드는
    미승인 상태로 간주한다.
    """

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(2))
    strategy_version: Mapped[str] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(30))
    based_on: Mapped[str | None] = mapped_column(String(20))
    change_summary: Mapped[str | None]
    backtest_result: Mapped[dict | None] = mapped_column(JSON)
    approved_by: Mapped[str | None] = mapped_column(String(50))
    # 후보 제안 시각 — 항상 채워진다 (proposed_at은 db.insert()의 created_at 자동 채움 대상이
    # 아니므로 자기개선 파이프라인에서 직접 지정한다).
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 승인 전에는 NULL — approved_by가 채워질 때만 지금 시각으로 설정한다.
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Reflection(_ModeMixin, Base):
    """일일 자기평가 리포트."""

    __tablename__ = "reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(2))
    content_md: Mapped[str]
    # 자기개선 후보 초안 — 프롬프트 문구 수정/전략 파라미터 조정 제안 (docs/SELF_IMPROVEMENT.md).
    proposed_change: Mapped[str | None]
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


class ControlFlags(Base):
    """긴급 정지 상태 — 단일 행(id=1)을 갱신한다.

    프로세스 재시작 시(systemd 자동 재시작 등) 인메모리 settings 값이 초기화되므로
    core/main.py 기동 시 이 테이블에서 복원한다 (docs/SAFETY.md "EMERGENCY_STOP = true
    (DB + Redis 즉시 반영)").
    """

    __tablename__ = "control_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    emergency_stop: Mapped[bool] = mapped_column(default=False)
    kr_stop: Mapped[bool] = mapped_column(default=False)
    us_stop: Mapped[bool] = mapped_column(default=False)
    # SIMULATION이 연속으로 유지된 시작 시각 — LIVE 전환 전 "2주 이상 필수"
    # (CLAUDE.md 절대 규칙 11, docs/SAFETY.md)를 판정하는 기준. 재시작에도 유지되어야 하므로
    # emergency_stop과 함께 이 단일 행에 영속화한다.
    simulation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FundRebalance(_ModeMixin, Base):
    """주간 자금 재배분 실행 기록 (docs/FUND_MANAGER.md "수익금 재배분 규칙").

    weekly_rebalance()가 매주 계산한 결과를 영구 기록해, 코드 외부에서 임의로 재현·변경할 수
    없는 감사 기록으로 남긴다.
    """

    __tablename__ = "fund_rebalances"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_value_krw: Mapped[int]
    api_cost_covered_krw: Mapped[int]
    reinvested_krw: Mapped[int]
    buffer_added_krw: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulationPortfolioSnapshot(Base):
    """시뮬레이션 포트폴리오 스냅샷."""

    __tablename__ = "simulation_portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_value_krw: Mapped[int]
    cash_krw: Mapped[int]
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LivePortfolioSnapshot(Base):
    """실전 포트폴리오 스냅샷 — simulation_portfolio_snapshots의 LIVE 대응.

    core/report/generator.py의 자산 추이·수익률 시계열 차트가 LIVE 모드에서도
    생성될 수 있도록 트레이딩 루프가 매 틱마다 적재한다.
    """

    __tablename__ = "live_portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_value_krw: Mapped[int]
    cash_krw: Mapped[int]
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Report(_ModeMixin, Base):
    """정기/즉시 리포트 생성 기록 — 전체 마크다운은 logs/reports/*.md 파일로만 남고
    (core/report/generator.py), 여기는 모니터(docs/MONITOR.md)의 "리포트" 서브스트립이
    쓸 한 줄 요약만 감사 가능한 형태로 영속화한다.
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(3))
    report_type: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
