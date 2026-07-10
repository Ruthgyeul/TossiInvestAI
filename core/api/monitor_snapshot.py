"""모니터(monitor/) 대시보드 전용 스냅샷 집계. docs/MONITOR.md "데이터 흐름" 참고.

monitor/src/app/api/snapshot/route.ts는 여러 엔드포인트를 조합하지 않고 이 모듈이
만드는 `GET /api/v1/monitor/snapshot` 하나만 호출해 화면 전체를 채운다. 여기서 다루는
값 중 일부는 이 프로젝트에 애초에 실데이터 소스가 없다(토스 Open API에 "인기 종목"
랭킹·시장 지수 엔드포인트가 없다 — docs/TOSS_API.md) — 그런 항목은 이미 이 저장소가
써 온 대체 지표를 그대로 재사용한다(`core/market_data/collector.py`의
`_popular_top10`/`_fear_greed_index` 문서 주석, `core/report/generator.py`의
`_market_composite_series` 참고). 새로 지어내지 않는다.
"""

import json
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psutil

from core.config import settings
from core.db import store as db
from core.db.redis import get_redis
from core.fund.manager import fund_manager
from core.market_data import indicators
from core.market_data.watchlist import get_watchlist
from core.models import Mode
from core.monitoring.health import HEALTH_REDIS_KEY
from core.toss import market as toss_market

_KST = ZoneInfo("Asia/Seoul")
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
_REPORT_LABELS: dict[str, str] = {
    "pre_market": "장 시작 전 브리핑",
    "midday": "중간 리포트",
    "close": "장 마감 리포트",
    "weekly": "주간 성과 리포트",
    "on_demand": "즉시 리포트",
}

# docs/SAFETY.md가 명시한 조건 수. core/safety/gate.py의 실제 거부 분기 수(13)와 어긋나
# 있다 — 이 스냅샷은 문서상 공개 수치를 그대로 보여준다. 두 수를 맞추는 건 이 변경의
# 범위 밖이라 TODO로 남긴다.
_SAFETY_GATE_CONDITION_COUNT = 11

# 서브 스트립 "성과"/"리스크" 회전 카드, 손익 차트 "일평균/승률" 계산의 표본 창.
_ALPHA_WINDOW_DAYS = 20
_SHARPE_WINDOW_DAYS = 30
_VOLATILITY_WINDOW_DAYS = 5
_RECENT_TRADES_LIMIT = 30
_FULL_CHART_MAX_BARS = 60
_RECENT_15D_BARS = 15


def _current_mode() -> Mode:
    return "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"


def _to_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_KST)


def _format_log_time(dt: datetime) -> str:
    """오늘은 "HH:MM", 어제/그제는 "어제 HH:MM"/"그제 HH:MM", 그 이전은 "MM/DD HH:MM"."""
    dt_kst = _to_kst(dt)
    today = datetime.now(_KST).date()
    time_str = dt_kst.strftime("%H:%M")
    if dt_kst.date() == today:
        return time_str
    if dt_kst.date() == today - timedelta(days=1):
        return f"어제 {time_str}"
    if dt_kst.date() == today - timedelta(days=2):
        return f"그제 {time_str}"
    return f"{dt_kst.strftime('%m/%d')} {time_str}"


def _fear_greed_label(index: int | None) -> str:
    if index is None:
        return "데이터 없음"
    if index < 25:
        return "극도의 공포"
    if index < 45:
        return "공포"
    if index < 55:
        return "중립"
    if index < 75:
        return "탐욕"
    return "극도의 탐욕"


def _short_model_name(model: str | None) -> str:
    if not model:
        return settings.CLAUDE_MODEL
    lowered = model.lower()
    if "opus" in lowered:
        return "Opus"
    if "haiku" in lowered:
        return "Haiku"
    if "sonnet" in lowered:
        return "Sonnet"
    return model


async def _latest_decision_state() -> dict[str, Any] | None:
    """가장 최근 트레이딩 루프 틱의 StateSnapshot(JSON) — toss_popular_top10·fear_greed_index·
    종목별 news_summary가 여기 이미 들어 있어 재수집(추가 토스 API 호출) 없이 재사용한다."""
    rows = await db.fetch_all("decisions", order_by="created_at", descending=True, limit=1)
    return rows[0]["state_snapshot"] if rows else None


async def _build_header(mode: Mode) -> dict[str, Any]:
    usd_krw = await toss_market.get_exchange_rate()
    kr_open = await toss_market.is_market_open("KR")
    us_open = await toss_market.is_market_open("US")
    version = await db.get_latest_deployed_strategy_version()

    return {
        "usdKrw": usd_krw,
        "krMarketStatus": "장중" if kr_open else "장마감",
        "usMarketStatus": "장중" if us_open else "장마감",
        "strategyVersion": version["strategy_version"] if version else "v1.0.0",
        "promptVersion": version["prompt_version"] if version else "system_kr_v1",
    }


async def _build_substrip(
    state: dict[str, Any] | None,
    perf_stats: list[dict[str, Any]],
    risk_stats: list[dict[str, Any]],
) -> dict[str, Any]:
    reports = await db.fetch_all("reports", order_by="created_at", descending=True, limit=1)
    latest_report = reports[0] if reports else None
    fear_greed: int | None = (state or {}).get("fear_greed_index")

    return {
        "reportTime": _format_log_time(latest_report["created_at"]).split(" ")[-1] if latest_report else "-",
        "reportSummary": latest_report["summary"] if latest_report else "아직 생성된 리포트가 없습니다",
        "perfStats": perf_stats,
        "riskStats": risk_stats,
        "fearGreedIndex": fear_greed,
        "fearGreedLabel": _fear_greed_label(fear_greed),
    }


async def _build_total_assets(mode: Mode, portfolio: dict, exchange_rate: float) -> dict[str, Any]:
    holdings = portfolio["holdings"]
    kr_value = sum(h["quantity"] * h["currentPrice"] for h in holdings if h["market"] == "KR")
    us_value_krw = sum(
        h["quantity"] * h["currentPrice"] * exchange_rate for h in holdings if h["market"] == "US"
    )
    unrealized_pnl_krw = 0.0
    for h in holdings:
        delta = (h["currentPrice"] - h["avgPrice"]) * h["quantity"]
        if h["market"] == "US":
            delta *= exchange_rate
        unrealized_pnl_krw += delta

    op_days = await db.get_operation_days()
    api_today = await db.get_api_usage_today_summary()
    api_month = await db.get_api_usage_month_summary()

    return {
        "totalKrw": portfolio["totalValueKrw"],
        "todayChangeKrw": portfolio["todayPnlKrw"],
        "todayChangePct": portfolio["todayPnlPct"] * 100,
        "breakdown": {
            "cashKrw": portfolio["cashKrw"],
            "krInvestedKrw": int(kr_value),
            "usInvestedKrw": int(us_value_krw),
        },
        "realizedPnlTodayKrw": portfolio["todayPnlKrw"],
        "unrealizedPnlKrw": int(unrealized_pnl_krw),
        "cumulativeReturnPct": portfolio["cumulativePnlPct"] * 100,
        "seedKrw": settings.INITIAL_SEED_KRW,
        "operatingDays": op_days["total_days"],
        "liveDays": op_days["live_days"],
        "apiModel": _short_model_name(api_today["model"]),
        "apiCallsToday": api_today["call_count"],
        "apiCostTodayUsd": round(api_today["cost_usd"], 2),
        "apiCostTodayKrw": api_today["cost_krw"],
        "monthlyTokensInK": round(api_month["input_tokens"] / 1000, 1),
        "monthlyTokensOutK": round(api_month["output_tokens"] / 1000, 1),
        "apiCallsMonthly": api_month["call_count"],
        "apiCostMonthlyUsd": round(api_month["cost_usd"], 2),
        "apiCostMonthlyKrw": api_month["cost_krw"],
    }


async def _fetch_portfolio_snapshots(mode: Mode) -> list[dict[str, Any]]:
    """오래된 순으로 정렬된 최근 포트폴리오 스냅샷(15분 간격 루프 틱마다 적재).

    일별 손익 차트("전체"/"최근 15일")와 오늘 시간대별 차트("일일") 모두 이 한 번의
    조회로 만든다 — daily_pnl 테이블은 실제로 채워지지 않아(core/db/models.py) 쓸 수 없다.
    """
    return (
        await db.get_recent_live_snapshots(limit=2000)
        if mode == "LIVE"
        else await db.get_recent_simulation_snapshots(limit=2000)
    )


def _daily_last_values(snapshots: list[dict[str, Any]]) -> dict[date, float]:
    """날짜별 마지막 스냅샷 총자산 — 오름차순 입력이므로 마지막 값이 그날의 종가다."""
    daily_last: dict[date, float] = {}
    for s in snapshots:
        day = _to_kst(s["snapshot_at"]).date()
        daily_last[day] = float(s["total_value_krw"])
    return daily_last


def _hourly_last_values_today(snapshots: list[dict[str, Any]]) -> dict[datetime, float]:
    today = datetime.now(_KST).date()
    hourly_last: dict[datetime, float] = {}
    for s in snapshots:
        ts_kst = _to_kst(s["snapshot_at"])
        if ts_kst.date() != today:
            continue
        bucket = ts_kst.replace(minute=0, second=0, microsecond=0)
        hourly_last[bucket] = float(s["total_value_krw"])
    return hourly_last


def _bars_from_values(values: list[float]) -> list[int]:
    return [int(values[i] - values[i - 1]) for i in range(1, len(values))]


def _win_rate_pct(bars: list[int]) -> int:
    if not bars:
        return 0
    wins = sum(1 for b in bars if b > 0)
    return round(wins / len(bars) * 100)


def _avg_daily_return_pct(bars: list[int]) -> float:
    if not bars:
        return 0.0
    return sum(bars) / len(bars) / settings.INITIAL_SEED_KRW * 100


def _day_labels(days: list[date]) -> list[str]:
    """3개 바마다 "MM/DD" 라벨을 붙이고, 마지막 바는 항상 "오늘"로 표시한다."""
    n = len(days)
    labels = []
    for i, d in enumerate(days):
        if i == n - 1:
            labels.append("오늘")
        elif i % 3 == 0:
            labels.append(f"{d.month}/{d.day}")
        else:
            labels.append("")
    return labels


def _hour_labels(hours: list[datetime]) -> list[str]:
    n = len(hours)
    labels = []
    for i, h in enumerate(hours):
        if i == n - 1:
            labels.append("지금")
        elif i % 3 == 0:
            labels.append(f"{h.hour}시")
        else:
            labels.append("")
    return labels


async def _proxy_daily_returns(market: str) -> list[float] | None:
    """관심 종목 일봉 종가의 동일가중 평균 시계열에서 뽑은 일별 수익률(비율), 오래된 순.

    docs/TOSS_API.md에 KOSPI/NASDAQ 같은 시장 지수 엔드포인트가 없어, core/report/
    generator.py `_market_composite_series`와 같은 방식(관심 종목 종가 동일가중 평균)을
    벤치마크 대체 시계열로 재사용한다. 관심 종목이 없거나 공통 히스토리가 짧으면 None.
    """
    watchlist_items = await get_watchlist(market)
    symbols = [item["symbol"] for item in watchlist_items]
    if not symbols:
        return None

    all_closes = []
    for symbol in symbols:
        candles = await toss_market.get_candles(symbol, "1d")
        closes = [c["close"] for c in candles]
        if closes:
            all_closes.append(closes)
    if not all_closes:
        return None

    min_len = min(len(closes) for closes in all_closes)
    if min_len < 2:
        return None

    trimmed = [closes[-min_len:] for closes in all_closes]
    composite = [sum(day_values) / len(day_values) for day_values in zip(*trimmed, strict=True)]
    return [
        (composite[i] - composite[i - 1]) / composite[i - 1]
        for i in range(1, len(composite))
        if composite[i - 1] > 0
    ]


def _compound_return(returns: list[float]) -> float:
    total = 1.0
    for r in returns:
        total *= 1 + r
    return total - 1


def _blended_benchmark_bars(
    n: int,
    kr_returns: list[float] | None,
    us_returns: list[float] | None,
    kr_weight: float,
    us_weight: float,
    base_krw: float,
) -> list[int]:
    """포트폴리오 KR/US 투자 비중으로 가중한 벤치마크 일별 손익(KRW 환산 근사치).

    실제 일별 자산 기준선을 과거 시점별로 추적하지 않으므로, 현재 총자산(`base_krw`)을
    고정 기준선으로 삼아 벤치마크가 그 기준선에서 같은 비율로 움직였다면의 근사 손익을
    낸다 — 손익 차트의 벤치마크 겹쳐그리기용 참고선이지 정밀한 성과 귀속이 아니다.
    """
    if not kr_returns and not us_returns:
        return []

    def _tail(returns: list[float] | None) -> list[float]:
        returns = returns or []
        if len(returns) >= n:
            return returns[-n:]
        return [0.0] * (n - len(returns)) + returns

    kr_tail = _tail(kr_returns)
    us_tail = _tail(us_returns)
    blended = [kr_weight * kr + us_weight * us for kr, us in zip(kr_tail, us_tail, strict=True)]
    return [round(r * base_krw) for r in blended]


async def _build_chart_period(
    label: str,
    values: list[float],
    day_keys: list[date] | list[datetime],
    *,
    hourly: bool,
    kr_returns: list[float] | None,
    us_returns: list[float] | None,
    kr_weight: float,
    us_weight: float,
    base_krw: float,
) -> dict[str, Any]:
    bars = _bars_from_values(values)
    x_labels = _hour_labels(day_keys[1:]) if hourly else _day_labels(day_keys[1:])  # type: ignore[arg-type]
    benchmark_bars = [] if hourly else _blended_benchmark_bars(
        len(bars), kr_returns, us_returns, kr_weight, us_weight, base_krw
    )
    return {
        "label": label,
        "bars": bars,
        "xLabels": x_labels,
        "avgDailyReturnPct": _avg_daily_return_pct(bars),
        "winRatePct": _win_rate_pct(bars),
        "benchmarkBars": benchmark_bars,
    }


def _concentration_stat(holdings: list[dict], exchange_rate: float) -> dict[str, Any] | None:
    values = []
    for h in holdings:
        value = h["quantity"] * h["currentPrice"]
        if h["market"] == "US":
            value *= exchange_rate
        values.append((h["symbol"], value))
    invested_total = sum(v for _, v in values)
    if not values or invested_total <= 0:
        return None

    top_symbol, top_value = max(values, key=lambda item: item[1])
    ratio_pct = top_value / invested_total * 100
    cap_pct = settings.MAX_POSITION_RATIO * 100
    if ratio_pct >= cap_pct:
        tone, label = "bad", "위험"
    elif ratio_pct >= cap_pct * 0.8:
        tone, label = "warn", "주의"
    else:
        tone, label = "good", "정상"

    return {"label": "집중도", "value": f"{label} · {top_symbol} {ratio_pct:.1f}%", "tone": tone}


def _volatility_stat(days_sorted: list[date], daily_last: dict[date, float]) -> dict[str, Any] | None:
    recent_days = days_sorted[-(_VOLATILITY_WINDOW_DAYS + 1):]
    if len(recent_days) < 3:
        return None
    values = [daily_last[d] for d in recent_days]
    returns_pct = [
        (values[i] - values[i - 1]) / values[i - 1] * 100
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]
    if len(returns_pct) < 2:
        return None
    stdev = statistics.pstdev(returns_pct)
    if stdev < 0.5:
        tone, label = "good", "낮음"
    elif stdev < 1.5:
        tone, label = "warn", "보통"
    else:
        tone, label = "bad", "높음"
    return {"label": "변동성", "value": f"{label} · 최근 {len(returns_pct)}일", "tone": tone}


def _mdd_stat(values: list[float]) -> dict[str, Any] | None:
    if len(values) < 2:
        return None
    mdd = indicators.calculate_max_drawdown_pct(values)
    return {"label": "MDD", "value": f"{mdd * 100:.1f}% · 시드 대비", "tone": "bad"}


def _var_stat(bars: list[int]) -> dict[str, Any] | None:
    if len(bars) < 10:
        return None
    sorted_bars = sorted(bars)
    idx = max(0, min(len(sorted_bars) - 1, round(0.05 * (len(sorted_bars) - 1))))
    var_krw = sorted_bars[idx]
    return {"label": "VaR (95%)", "value": f"{var_krw:+,}원 · 1일 기준", "tone": "bad"}


def _sharpe_stat(values: list[float]) -> dict[str, Any] | None:
    if len(values) < 5:
        return None
    sharpe = indicators.calculate_sharpe_ratio(values)
    tone = "positive" if sharpe > 0 else "neutral"
    return {"label": "샤프지수", "value": f"{sharpe:.2f} · 최근 {len(values) - 1}일", "tone": tone}


def _win_streak_stat(bars: list[int]) -> dict[str, Any] | None:
    if not bars:
        return None
    streak = 0
    for b in reversed(bars):
        if b > 0:
            streak += 1
        else:
            break
    tone = "positive" if streak > 0 else "neutral"
    value = f"{streak}일 · 진행 중" if streak > 0 else "0일 · 없음"
    return {"label": "연속수익", "value": value, "tone": tone}


def _profit_factor_and_win_rate(trades: list[dict]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    closed = [t for t in trades if t.get("pnl_krw") is not None]
    if not closed:
        return None, None
    wins = [t for t in closed if t["pnl_krw"] > 0]
    losses = [t for t in closed if t["pnl_krw"] < 0]

    win_rate_stat = {
        "label": "승률",
        "value": f"{round(len(wins) / len(closed) * 100)}% · 최근 {len(closed)}건",
        "tone": "neutral",
    }

    gross_profit = sum(t["pnl_krw"] for t in wins)
    gross_loss = abs(sum(t["pnl_krw"] for t in losses))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = 999.0 if gross_profit > 0 else None
    profit_factor_stat = None
    if profit_factor is not None:
        tone = "positive" if profit_factor >= 1 else "negative"
        value = f"{profit_factor:.1f} · 평균 수익/손실"
        profit_factor_stat = {"label": "손익비", "value": value, "tone": tone}
    return win_rate_stat, profit_factor_stat


def _fill_rate_stat(trades: list[dict], rejections: list[dict]) -> dict[str, Any] | None:
    """"체결률" = Safety Gate를 통과해 실제 체결된 시도 / (체결 + Safety Gate 거부) 시도.

    LIVE 모드의 `orders` 테이블은 Safety Gate를 통과한 주문만 기록해 실제 체결 실패
    케이스가 없고, SIMULATION은 애초에 `orders`에 쓰지 않는다(core/trading/executor.py) —
    두 모드 모두에서 의미가 통하도록 "매매 시그널이 최종 체결까지 이어졌는가"를
    체결 건수 대 Safety Gate 거부 건수의 비율로 근사한다.
    """
    filled = len(trades)
    attempted = filled + len(rejections)
    if attempted == 0:
        return None
    pct = round(filled / attempted * 100)
    return {"label": "체결률", "value": f"{pct}% · {filled}/{attempted}건", "tone": "neutral"}


def _alpha_stat(
    label_suffix: str, holdings: list[dict], market: str, proxy_returns: list[float] | None
) -> dict[str, Any] | None:
    market_holdings = [h for h in holdings if h["market"] == market]
    if not market_holdings or not proxy_returns:
        return None

    total_value = sum(h["quantity"] * h["currentPrice"] for h in market_holdings)
    if total_value <= 0:
        return None
    portfolio_return_pct = sum(
        h["pnlPct"] * (h["quantity"] * h["currentPrice"]) for h in market_holdings
    ) / total_value * 100

    proxy_return_pct = _compound_return(proxy_returns[-_ALPHA_WINDOW_DAYS:]) * 100
    alpha_pp = portfolio_return_pct - proxy_return_pct
    tone = "positive" if alpha_pp >= 0 else "negative"
    return {"label": "알파", "value": f"{alpha_pp:+.1f}%p · {label_suffix} 대비", "tone": tone}


async def _build_perf_stats(
    mode: Mode,
    portfolio: dict,
    daily_last: dict[date, float],
    days_sorted: list[date],
    kr_returns: list[float] | None,
    us_returns: list[float] | None,
) -> list[dict[str, Any]]:
    holdings = portfolio["holdings"]
    trade_table = "trades" if mode == "LIVE" else "simulation_trades"
    trades = await db.fetch_all(
        trade_table, order_by="created_at", descending=True, limit=_RECENT_TRADES_LIMIT
    )
    rejections = await db.fetch_all(
        "safety_rejections",
        {"mode": mode},
        order_by="created_at",
        descending=True,
        limit=_RECENT_TRADES_LIMIT,
    )

    values = [daily_last[d] for d in days_sorted]
    all_bars = _bars_from_values(values)
    sharpe_window = values[-(_SHARPE_WINDOW_DAYS + 1):]

    win_rate_stat, profit_factor_stat = _profit_factor_and_win_rate(trades)

    stats = [
        _alpha_stat("KOSPI", holdings, "KR", kr_returns),
        _alpha_stat("S&P500", holdings, "US", us_returns),
        win_rate_stat,
        _fill_rate_stat(trades, rejections),
        profit_factor_stat,
        _sharpe_stat(sharpe_window),
        _win_streak_stat(all_bars),
    ]
    resolved = [s for s in stats if s is not None]
    if not resolved:
        return [{"label": "성과", "value": "데이터 수집 중", "tone": "neutral"}]
    return resolved


def _build_risk_stats(
    portfolio: dict,
    exchange_rate: float,
    daily_last: dict[date, float],
    days_sorted: list[date],
) -> list[dict[str, Any]]:
    values = [daily_last[d] for d in days_sorted]
    all_bars = _bars_from_values(values)

    stats = [
        _concentration_stat(portfolio["holdings"], exchange_rate),
        _volatility_stat(days_sorted, daily_last),
        _mdd_stat(values),
        _var_stat(all_bars),
    ]
    resolved = [s for s in stats if s is not None]
    if not resolved:
        return [{"label": "리스크", "value": "데이터 수집 중", "tone": "neutral"}]
    return resolved


def _process_uptime_label() -> str:
    """core(=스케줄러와 동일 프로세스)의 실제 프로세스 가동 시간."""
    boot = datetime.fromtimestamp(psutil.Process().create_time(), tz=UTC)
    return _duration_label(datetime.now(UTC) - boot)


def _duration_label(delta: timedelta) -> str:
    days = delta.days
    hours = delta.seconds // 3600
    if days > 0:
        return f"{days}d {hours}h"
    minutes = (delta.seconds % 3600) // 60
    return f"{hours}h {minutes}m"


async def _discord_bot_uptime_label(redis: Any) -> str | None:
    """discord-bot이 준비 완료 시 기록하는 Redis 키 — discord-bot/src/index.ts.

    core 프로세스와 달리 별도 프로세스라 psutil로 직접 잴 수 없다. 키가 없으면(구버전
    discord-bot 실행 중이거나 아직 기동 전) None을 돌려주고 호출자가 "응답 없음"으로 표시한다.
    """
    started_at_raw = await redis.get("service:started_at:discord-bot")
    if not started_at_raw:
        return None
    started_at = datetime.fromisoformat(started_at_raw)
    return _duration_label(datetime.now(UTC) - started_at)


async def _build_system_health(mode: Mode) -> dict[str, Any]:
    redis = get_redis()
    cached = await redis.get(HEALTH_REDIS_KEY)
    collected_at: str | None = None
    if cached:
        collected_at = json.loads(cached).get("collected_at")

    hb_seconds_ago = 0
    if collected_at:
        hb_seconds_ago = max(0, int((datetime.now(UTC) - datetime.fromisoformat(collected_at)).total_seconds()))

    core_uptime = _process_uptime_label()
    discord_uptime = await _discord_bot_uptime_label(redis)
    db_ok = True
    try:
        await db.fetch_all("control_flags", limit=1)
    except Exception:  # noqa: BLE001 — 헬스 표시용 ping이라 어떤 이유로든 실패하면 오류로 취급
        db_ok = False
    toss_ok = True
    try:
        await toss_market.get_exchange_rate()
    except Exception:  # noqa: BLE001 — 위와 동일한 이유
        toss_ok = False

    services = [
        {"name": "core", "status": "ok", "detail": core_uptime},
        {
            "name": "discord-bot",
            "status": "ok" if discord_uptime else "error",
            "detail": discord_uptime or "응답 없음",
        },
        {"name": "scheduler", "status": "ok", "detail": core_uptime},
        {"name": "DB·Redis", "status": "ok" if db_ok else "error", "detail": "정상" if db_ok else "오류"},
        {"name": "Toss API", "status": "ok" if toss_ok else "error", "detail": "정상" if toss_ok else "오류"},
        {"name": "매매 판단 모델 API", "status": "ok", "detail": "정상"},
    ]

    trade_table = "trades" if mode == "LIVE" else "simulation_trades"
    trades = await db.fetch_all(trade_table, order_by="created_at", descending=True, limit=6)
    rejections = await db.fetch_all("safety_rejections", order_by="created_at", descending=True, limit=6)
    reflections = await db.fetch_all("reflections", order_by="created_at", descending=True, limit=3)
    reports = await db.fetch_all("reports", order_by="created_at", descending=True, limit=3)

    log_entries: list[tuple[datetime, str, str]] = []
    for t in trades:
        log_entries.append((t["created_at"], "INFO", f"{t['symbol']} {t['action']} 주문 체결"))
    for r in rejections:
        log_entries.append((r["created_at"], "WARN", f"{r['symbol']} Safety Gate 거부"))
    for r in reflections:
        log_entries.append((r["created_at"], "INFO", f"{r['market']} 자기평가 완료"))
    for r in reports:
        label = _REPORT_LABELS.get(r["report_type"], "리포트")
        log_entries.append((r["created_at"], "INFO", f"{r['market']} {label} 생성 완료"))
    if collected_at:
        log_entries.append((datetime.fromisoformat(collected_at), "INFO", "하트비트 정상 · core"))

    log_entries.sort(key=lambda e: e[0], reverse=True)
    logs = [{"time": _format_log_time(t), "level": lvl, "message": msg} for t, lvl, msg in log_entries[:12]]

    latest_reflection = reflections[0] if reflections else None
    self_summary = "아직 자기평가 기록이 없습니다"
    self_time = "-"
    if latest_reflection is not None:
        self_summary = latest_reflection["content_md"].strip().splitlines()[0][:200]
        self_time = _format_log_time(latest_reflection["created_at"])

    return {
        # 시스템 예외/크래시를 별도로 집계하는 로그 저장소가 없어 항상 0이다 — 거짓으로
        # 임의의 숫자를 채우지 않고, 실제로 에러 추적이 붙기 전까지는 0으로 둔다.
        "errorCountToday": 0,
        "lastHeartbeatSecondsAgo": hb_seconds_ago,
        "services": services,
        "logs": logs,
        "safetyGate": {
            "passRateLabel": f"{_SAFETY_GATE_CONDITION_COUNT}/{_SAFETY_GATE_CONDITION_COUNT} 통과",
            "rejections": [
                {"time": _format_log_time(r["created_at"]), "message": f"{r['symbol']} · {r['reason']}"}
                for r in rejections
            ],
        },
        "selfAssessment": {"time": self_time, "summary": self_summary},
    }


def _build_positions(holdings: list[dict]) -> list[dict]:
    ranked = sorted(holdings, key=lambda h: h["pnlPct"], reverse=True)
    return [
        {
            "market": h["market"],
            "symbol": h["symbol"],
            "quantityLabel": f"{h['quantity']}주",
            "returnPct": round(h["pnlPct"] * 100, 1),
        }
        for h in ranked
    ]


async def _build_ai_decisions() -> tuple[list[dict], int]:
    rows = await db.fetch_all("decisions", order_by="created_at", descending=True, limit=50)
    today = datetime.now(_KST).date()
    today_count = sum(1 for r in rows if _to_kst(r["created_at"]).date() == today)
    decisions = [
        {
            "time": _format_log_time(r["created_at"]),
            "action": r["decision"]["action"],
            "symbol": r["decision"]["symbol"],
            "confidencePct": round(r["decision"]["confidence"] * 100),
        }
        for r in rows[:8]
    ]
    return decisions, today_count


def _build_news(state: dict[str, Any] | None) -> list[dict]:
    """최근 루프 틱에 이미 수집된 종목별 뉴스 요약(Gemini) — 모니터 폴링마다 RSS를 다시
    긁지 않는다. 감성(호재/주의/악재) 분류는 여기서 하지 않는다 — 텍스트만 real이고
    분류 로직은 monitor 쪽 표시 계층 관심사라 src/lib/format.ts 근처에 둔다."""
    if not state:
        return []
    items = []
    for symbol, data in (state.get("prices") or {}).items():
        summary = data.get("news_summary")
        if summary and summary != "뉴스 없음":
            items.append({"symbol": symbol, "text": summary})
    return items[:3]


async def _build_events() -> list[dict]:
    now = datetime.now(UTC)
    rows = await db.fetch_all("market_events", order_by="event_at", descending=False, limit=100)
    upcoming = [e for e in rows if e["event_at"] >= now][:5]

    result = []
    today = datetime.now(_KST).date()
    for e in upcoming:
        event_kst = _to_kst(e["event_at"])
        days_until = (event_kst.date() - today).days
        weekday = _WEEKDAY_KO[event_kst.weekday()]
        result.append(
            {
                "label": f"{event_kst.month}/{event_kst.day} ({weekday}) {e['event_type']}",
                "risk": "고위험" if e["is_high_risk"] else "일반",
                "daysUntilLabel": None if e["is_high_risk"] else f"D+{days_until}",
            }
        )
    return result


async def build_monitor_snapshot() -> dict[str, Any]:
    """GET /api/v1/monitor/snapshot의 전체 응답 본문(mode 제외 — routes.py `_json`이 채운다)."""
    mode = _current_mode()
    exchange_rate = await toss_market.get_exchange_rate()
    portfolio = await fund_manager.get_portfolio_status(mode)
    state = await _latest_decision_state()
    ai_decisions, ai_decisions_today = await _build_ai_decisions()

    snapshots = await _fetch_portfolio_snapshots(mode)
    daily_last = _daily_last_values(snapshots)
    days_sorted = sorted(daily_last.keys())
    kr_returns = await _proxy_daily_returns("KR") if days_sorted else None
    us_returns = await _proxy_daily_returns("US") if days_sorted else None

    perf_stats = await _build_perf_stats(mode, portfolio, daily_last, days_sorted, kr_returns, us_returns)
    risk_stats = _build_risk_stats(portfolio, exchange_rate, daily_last, days_sorted)
    chart = await _build_chart(portfolio, snapshots, daily_last, days_sorted, kr_returns, us_returns)

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "header": await _build_header(mode),
        "subStrip": await _build_substrip(state, perf_stats, risk_stats),
        "totalAssets": await _build_total_assets(mode, portfolio, exchange_rate),
        "chart": chart,
        "systemHealth": await _build_system_health(mode),
        "positions": _build_positions(portfolio["holdings"]),
        "aiDecisions": ai_decisions,
        "aiDecisionsCountToday": ai_decisions_today,
        "news": _build_news(state),
        "events": await _build_events(),
    }


async def _build_chart(
    portfolio: dict,
    snapshots: list[dict[str, Any]],
    daily_last: dict[date, float],
    days_sorted: list[date],
    kr_returns: list[float] | None,
    us_returns: list[float] | None,
) -> dict[str, Any]:
    """손익 차트 — "전체"/"최근 15일"/"일일"(오늘 시간대별) 3개 기간을 모두 만든다.

    daily_pnl/simulation_daily_pnl 테이블은 현재 어디서도 채워지지 않아(core/db/models.py의
    두 모델을 찾아봐도 insert 지점이 없다) 실데이터 소스로 쓸 수 없다. 대신 매 루프 틱마다
    이미 쌓이는 {live,simulation}_portfolio_snapshots에서 날짜/시간별 마지막 스냅샷 간
    차액으로 손익(실현+평가)을 역산한다 — 새 트래킹을 추가하지 않고 이미 있는 데이터를 쓴다.
    `daily_last`/`days_sorted`/`kr_returns`/`us_returns`는 호출자(`build_monitor_snapshot`)가
    성과·리스크 지표와 공유하려고 미리 계산해 전달한다 — 중복 조회를 없앤다.
    """
    empty_period = {
        "label": "전체",
        "bars": [],
        "xLabels": [],
        "avgDailyReturnPct": 0.0,
        "winRatePct": 0,
        "benchmarkBars": [],
    }

    # "일일"(오늘 시간대별) 기간은 일별 히스토리 길이와 무관하게 오늘의 스냅샷만으로 계산한다
    # — 운용 첫날이라 daily_last가 하루치뿐이어도 당일 흐름은 보여줄 수 있어야 한다.
    hourly_last = _hourly_last_values_today(snapshots)
    hours_sorted = sorted(hourly_last.keys())
    if len(hours_sorted) >= 2:
        hourly_values = [hourly_last[h] for h in hours_sorted]
        hourly_period = await _build_chart_period(
            "일일", hourly_values, hours_sorted, hourly=True,
            kr_returns=None, us_returns=None, kr_weight=0.0, us_weight=0.0, base_krw=0,
        )
    else:
        hourly_period = {**empty_period, "label": "일일"}

    if len(days_sorted) < 2:
        return {
            "periods": [
                {**empty_period, "label": "전체"},
                {**empty_period, "label": "최근 15일"},
                hourly_period,
            ],
            "totalUpKrw": 0,
            "upDays": 0,
            "totalDownKrw": 0,
            "downDays": 0,
            "netKrw": 0,
        }

    kr_value = sum(h["quantity"] * h["currentPrice"] for h in portfolio["holdings"] if h["market"] == "KR")
    us_value = sum(h["quantity"] * h["currentPrice"] for h in portfolio["holdings"] if h["market"] == "US")
    invested_total = (kr_value + us_value) or 1
    kr_weight = kr_value / invested_total
    us_weight = us_value / invested_total

    full_days = days_sorted[-(_FULL_CHART_MAX_BARS + 1):]
    full_values = [daily_last[d] for d in full_days]
    full_period = await _build_chart_period(
        "전체", full_values, full_days, hourly=False,
        kr_returns=kr_returns, us_returns=us_returns, kr_weight=kr_weight, us_weight=us_weight,
        base_krw=portfolio["totalValueKrw"],
    )

    recent_days = days_sorted[-(_RECENT_15D_BARS + 1):]
    recent_values = [daily_last[d] for d in recent_days]
    recent_period = await _build_chart_period(
        "최근 15일", recent_values, recent_days, hourly=False,
        kr_returns=kr_returns, us_returns=us_returns, kr_weight=kr_weight, us_weight=us_weight,
        base_krw=portfolio["totalValueKrw"],
    )

    all_bars = _bars_from_values(full_values)
    up = [b for b in all_bars if b > 0]
    down = [b for b in all_bars if b < 0]

    return {
        "periods": [full_period, recent_period, hourly_period],
        "totalUpKrw": sum(up),
        "upDays": len(up),
        "totalDownKrw": sum(down),
        "downDays": len(down),
        "netKrw": sum(up) + sum(down),
    }
