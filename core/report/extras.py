"""리포트 확장 지표 수집 (docs/REPORT.md "확장 지표").

미실현 손익·Safety Gate 소진율·AI 결정 요약·리스크 라인·캘린더/세션·변동성(%B)·
환율 민감도·체결 타임라인을 모은다. 각 항목은 데이터 소스 장애·미연동 시 None/[]로 조용히
떨어져 리포트 본문을 막지 않는다(그래프·본문과 동일한 graceful degradation 원칙).

기존 코어 함수를 재사용한다(중복 계산·추가 토스 호출 최소화):
- 실현 손익/일일 손실: `db.get_today_realized_pnl_krw`
- 종목 비중: `fund_manager.get_position_ratio`
- AI 결정·API 사용량: `decisions` 테이블 + `db.get_api_usage_*_summary`
- 캘린더: `toss_market.is_market_open`/`is_regular_session` (CLAUDE.md 절대 규칙 4)
- 체결: `db.get_today_trades`
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from core.config import settings
from core.db import store as db
from core.fund.manager import fund_manager
from core.models import Market, Mode
from core.toss import market as toss_market

log = structlog.get_logger(__name__)

_TIMELINE_LIMIT = 8
_AI_DECISION_LOOKBACK = 50


def _today_start_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def compute_unrealized(holdings: list[dict], rate: float | None) -> dict[str, Any]:
    """보유 종목 미실현 손익 합계(₩)와 원가 대비 수익률. US는 환율로 원화 환산한다."""
    rows: list[dict[str, Any]] = []
    total_pnl = 0.0
    total_cost = 0.0
    for h in holdings:
        delta = (h["currentPrice"] - h["avgPrice"]) * h["quantity"]
        cost = h["avgPrice"] * h["quantity"]
        if h.get("market") == "US" and rate:
            delta *= rate
            cost *= rate
        total_pnl += delta
        total_cost += cost
        rows.append(
            {
                "symbol": h["symbol"],
                "market": h.get("market"),
                "pnl_krw": int(delta),
                "pnl_pct": h.get("pnlPct", 0.0),
            }
        )
    return {
        "total_krw": int(total_pnl),
        "total_pct": (total_pnl / total_cost) if total_cost else 0.0,
        "rows": rows,
    }


def compute_fx(holdings: list[dict], rate: float | None) -> dict[str, Any] | None:
    """USD/KRW와 US 보유 원화 환산 노출액·환율 1% 변동 민감도(₩)."""
    if not rate:
        return None
    us_value_usd = sum(
        h["currentPrice"] * h["quantity"] for h in holdings if h.get("market") == "US"
    )
    exposure_krw = us_value_usd * rate
    return {
        "usd_krw": rate,
        "us_exposure_krw": int(exposure_krw),
        "sensitivity_1pct_krw": int(exposure_krw * 0.01),
    }


def compute_bands(prices: dict[str, dict]) -> list[dict[str, Any]]:
    """볼린저밴드 %B(밴드 내 위치)·밴드폭(변동성). 스냅샷에 이미 계산된 bb_upper/lower 사용."""
    out: list[dict[str, Any]] = []
    for symbol, data in prices.items():
        upper, lower, price = data.get("bb_upper"), data.get("bb_lower"), data.get("price")
        if upper is None or lower is None or price is None or upper <= lower:
            continue
        mid = (upper + lower) / 2
        out.append(
            {
                "symbol": symbol,
                "pct_b": (price - lower) / (upper - lower),
                "bandwidth": (upper - lower) / mid if mid else 0.0,
            }
        )
    return out


def compute_risk_lines(holdings: list[dict]) -> list[dict[str, Any]]:
    """참고 손절/익절 라인 — 설정값(REPORT_STOP_LOSS_PCT/REPORT_TAKE_PROFIT_PCT) 기준으로
    평균단가에서 역산한다. 실제 청산은 전략이 결정하며 이 라인은 참고용이다."""
    sl = settings.REPORT_STOP_LOSS_PCT
    tp = settings.REPORT_TAKE_PROFIT_PCT
    out: list[dict[str, Any]] = []
    for h in holdings:
        avg = h["avgPrice"]
        out.append(
            {
                "symbol": h["symbol"],
                "market": h.get("market"),
                "avg": avg,
                "current": h["currentPrice"],
                "stop": avg * (1 - sl),
                "take": avg * (1 + tp),
                "stop_pct": sl,
                "take_pct": tp,
            }
        )
    return out


def compute_alpha(
    snapshot_values: list[float], benchmark_values: list[float]
) -> dict[str, Any] | None:
    """포트폴리오 기간 수익률 vs 관심 종목 지수(대체 지표) 기간 수익률의 초과분(α, %p)."""
    if len(snapshot_values) < 2 or not snapshot_values[0]:
        return None
    if len(benchmark_values) < 2 or not benchmark_values[0]:
        return None
    portfolio_pct = snapshot_values[-1] / snapshot_values[0] - 1
    benchmark_pct = benchmark_values[-1] / benchmark_values[0] - 1
    return {
        "portfolio_pct": portfolio_pct,
        "benchmark_pct": benchmark_pct,
        "alpha_pp": portfolio_pct - benchmark_pct,
    }


async def compute_safety(
    holdings: list[dict], prices_by_market: dict[str, dict], mode: Mode
) -> dict[str, Any]:
    """Safety Gate 소진율 — 일일 손실 한도, 종목당 비중 상한, VI/거래정지, 긴급정지 플래그."""
    realized = await db.get_today_realized_pnl_krw(mode)
    daily_loss = -realized if realized < 0 else 0
    limit = settings.MAX_DAILY_LOSS_KRW

    positions: list[dict[str, Any]] = []
    for h in holdings:
        try:
            ratio = await fund_manager.get_position_ratio(h["symbol"], mode)
        except Exception as e:  # noqa: BLE001 — 비중 조회 실패가 리포트를 막으면 안 된다
            log.warning("position_ratio_failed", symbol=h["symbol"], error=str(e))
            ratio = None
        positions.append({"symbol": h["symbol"], "ratio": ratio})

    restricted = [
        symbol
        for prices in prices_by_market.values()
        for symbol, data in prices.items()
        if data.get("vi_triggered")
    ]

    try:
        flags = await db.get_control_flags()
    except Exception as e:  # noqa: BLE001
        log.warning("control_flags_failed", error=str(e))
        flags = {"emergency_stop": False, "kr_stop": False, "us_stop": False}

    return {
        "daily_loss": daily_loss,
        "daily_limit": limit,
        "daily_usage": (daily_loss / limit) if limit else 0.0,
        "cap": settings.MAX_POSITION_RATIO,
        "positions": positions,
        "restricted": restricted,
        "flags": flags,
    }


async def compute_ai_summary() -> dict[str, Any]:
    """최근 AI 결정 요약 — 오늘 BUY/HOLD/SELL 건수, 최신 결정, API 호출·비용."""
    try:
        rows = await db.fetch_all(
            "decisions", order_by="created_at", descending=True, limit=_AI_DECISION_LOOKBACK
        )
    except Exception as e:  # noqa: BLE001
        log.warning("decisions_fetch_failed", error=str(e))
        rows = []

    today = _today_start_utc()
    counts = {"BUY": 0, "HOLD": 0, "SELL": 0}
    latest: dict[str, Any] | None = None
    for row in rows:
        decision = row.get("decision") or {}
        if latest is None and decision:
            latest = {
                "action": decision.get("action"),
                "symbol": decision.get("symbol"),
                "confidence": decision.get("confidence"),
                "reason": decision.get("reason"),
            }
        created = row.get("created_at")
        if created is not None and created >= today:
            action = decision.get("action")
            if action in counts:
                counts[action] += 1

    try:
        today_usage = await db.get_api_usage_today_summary()
        month_usage = await db.get_api_usage_month_summary()
    except Exception as e:  # noqa: BLE001
        log.warning("api_usage_fetch_failed", error=str(e))
        today_usage, month_usage = {}, {}

    return {
        "today_counts": counts,
        "latest": latest,
        "api_calls_today": today_usage.get("call_count", 0),
        "api_cost_today_krw": int(today_usage.get("cost_krw", 0)),
        "api_cost_month_krw": int(month_usage.get("cost_krw", 0)),
    }


async def compute_calendar(markets: list[Market]) -> dict[str, Any]:
    """시장별 개장 여부·정규장 여부 (토스 market-calendar API 기준, 하드코딩 금지)."""
    out: dict[str, Any] = {}
    for market in markets:
        try:
            out[market] = {
                "open": await toss_market.is_market_open(market),
                "regular": await toss_market.is_regular_session(market),
            }
        except Exception as e:  # noqa: BLE001
            log.warning("calendar_fetch_failed", market=market, error=str(e))
            out[market] = None
    return out


async def compute_timeline(markets: list[Market], mode: Mode) -> list[dict[str, Any]]:
    """오늘 체결 타임라인 — 시장별 체결을 시간 내림차순으로 병합해 최근 N건."""
    trades: list[dict[str, Any]] = []
    for market in markets:
        try:
            trades += await db.get_today_trades(mode, market)
        except Exception as e:  # noqa: BLE001
            log.warning("today_trades_failed", market=market, error=str(e))
    dated = [t for t in trades if t.get("created_at") is not None]
    dated.sort(key=lambda t: t["created_at"], reverse=True)
    return [
        {
            "created_at": t["created_at"],
            "symbol": t.get("symbol"),
            "action": t.get("action"),
            "quantity": t.get("quantity"),
            "fill_price": t.get("fill_price"),
            "pnl_krw": t.get("pnl_krw"),
        }
        for t in dated[:_TIMELINE_LIMIT]
    ]


async def gather_report_extras(
    markets: list[Market],
    snapshots_by_market: dict[str, dict],
    portfolio: dict,
    mode: Mode,
    benchmark_values: list[float] | None = None,
) -> dict[str, Any]:
    """리포트 확장 지표를 한 번에 모은다. 개별 항목은 내부에서 방어적으로 처리한다."""
    holdings = portfolio.get("holdings", [])
    prices_by_market = {m: snap.get("prices", {}) for m, snap in snapshots_by_market.items()}
    rate = next(
        (
            snap.get("exchange_rate_krw_usd")
            for snap in snapshots_by_market.values()
            if snap.get("exchange_rate_krw_usd")
        ),
        None,
    )

    snapshots = (
        await db.get_recent_live_snapshots()
        if mode == "LIVE"
        else await db.get_recent_simulation_snapshots()
    )
    snapshot_values = [float(s["total_value_krw"]) for s in snapshots]

    return {
        "unrealized": compute_unrealized(holdings, rate),
        "fx": compute_fx(holdings, rate),
        "bands": compute_bands(
            {sym: d for prices in prices_by_market.values() for sym, d in prices.items()}
        ),
        "risk_lines": compute_risk_lines(holdings),
        "alpha": compute_alpha(snapshot_values, benchmark_values or []),
        "safety": await compute_safety(holdings, prices_by_market, mode),
        "ai": await compute_ai_summary(),
        "calendar": await compute_calendar(markets),
        "timeline": await compute_timeline(markets, mode),
    }
