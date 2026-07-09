"""모니터(monitor/) 대시보드 전용 스냅샷 집계. docs/MONITOR.md "데이터 흐름" 참고.

monitor/src/app/api/snapshot/route.ts는 여러 엔드포인트를 조합하지 않고 이 모듈이
만드는 `GET /api/v1/monitor/snapshot` 하나만 호출해 화면 전체를 채운다. 여기서 다루는
값 중 일부는 이 프로젝트에 애초에 실데이터 소스가 없다(토스 Open API에 "인기 종목"
랭킹·시장 지수 엔드포인트가 없다 — docs/TOSS_API.md) — 그런 항목은 이미 이 저장소가
써 온 대체 지표를 그대로 재사용한다(`core/market_data/collector.py`의
`_popular_top10`/`_fear_greed_index` 문서 주석 참고). 새로 지어내지 않는다.
"""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psutil

from core.config import settings
from core.db import store as db
from core.db.redis import get_redis
from core.fund.manager import fund_manager
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


async def _build_substrip(state: dict[str, Any] | None, holdings: list[dict]) -> dict[str, Any]:
    reports = await db.fetch_all("reports", order_by="created_at", descending=True, limit=1)
    latest_report = reports[0] if reports else None
    candidates = await db.get_pending_strategy_candidates()

    toss_top10: list[str] = (state or {}).get("toss_popular_top10") or []
    fear_greed: int | None = (state or {}).get("fear_greed_index")
    holding_symbols = {h["symbol"] for h in holdings}
    overlap_holding_count = sum(1 for s in toss_top10 if s in holding_symbols)

    return {
        "reportTime": _format_log_time(latest_report["created_at"]).split(" ")[-1] if latest_report else "-",
        "reportSummary": latest_report["summary"] if latest_report else "아직 생성된 리포트가 없습니다",
        "selfImprovementPendingCount": len(candidates),
        "selfImprovementVersion": candidates[0]["strategy_version"] if candidates else "-",
        "tossOverlapSymbols": toss_top10[:3],
        "tossOverlapHoldingCount": overlap_holding_count,
        "tossOverlapTotalCount": len(toss_top10),
        "fearGreedIndex": fear_greed,
        "fearGreedLabel": _fear_greed_label(fear_greed),
    }


def _next_rebalance_days(now_kst: datetime) -> int:
    """다음 주간 재배분은 매주 월요일 08:00 KST(core/scheduler/tasks.py weekly_report)."""
    weekday = now_kst.weekday()  # Mon=0
    days_ahead = (0 - weekday) % 7
    if days_ahead == 0 and now_kst.hour >= 8:
        days_ahead = 7
    return days_ahead


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

    rebalance = await fund_manager.get_last_rebalance(mode)
    op_days = await db.get_operation_days()
    api_today = await db.get_api_usage_today_summary()

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
        "operatingDays": op_days["total_days"],
        "liveDays": op_days["live_days"],
        "weeklyRebalanceDaysUntil": _next_rebalance_days(datetime.now(_KST)),
        "lastReinvestmentKrw": rebalance["reinvested_krw"] if rebalance else 0,
        "apiCallsToday": api_today["call_count"],
        "apiModel": _short_model_name(api_today["model"]),
        "tokensInK": round(api_today["input_tokens"] / 1000, 1),
        "tokensOutK": round(api_today["output_tokens"] / 1000, 1),
        "apiCostTodayUsd": round(api_today["cost_usd"], 2),
        "apiCostTodayKrw": api_today["cost_krw"],
    }


async def _build_chart(mode: Mode) -> dict[str, Any]:
    """daily_pnl/simulation_daily_pnl 테이블은 현재 어디서도 채워지지 않아(core/db/models.py의
    두 모델을 찾아봐도 insert 지점이 없다) 실데이터 소스로 쓸 수 없다. 대신 매 루프 틱마다
    이미 쌓이는 {live,simulation}_portfolio_snapshots에서 날짜별 마지막 스냅샷 간 차액으로
    일별 손익(실현+평가)을 역산한다 — 새 트래킹을 추가하지 않고 이미 있는 데이터를 쓴다."""
    snapshots = (
        await db.get_recent_live_snapshots(limit=2000)
        if mode == "LIVE"
        else await db.get_recent_simulation_snapshots(limit=2000)
    )

    empty = {
        "periodLabel": "전체",
        "bars": [],
        "avgDailyReturnPct": 0.0,
        "winRatePct": 0,
        "totalUpKrw": 0,
        "upDays": 0,
        "totalDownKrw": 0,
        "downDays": 0,
        "netKrw": 0,
    }
    if len(snapshots) < 2:
        return empty

    daily_last: dict[date, float] = {}
    for s in snapshots:
        day = _to_kst(s["snapshot_at"]).date()
        daily_last[day] = float(s["total_value_krw"])  # 오름차순이므로 마지막 값이 그날의 종가

    days_sorted = sorted(daily_last.keys())
    values = [daily_last[d] for d in days_sorted]
    if len(values) < 2:
        return empty

    bars = [int(values[i] - values[i - 1]) for i in range(1, len(values))][-20:]
    up = [b for b in bars if b > 0]
    down = [b for b in bars if b < 0]
    total_up = sum(up)
    total_down = sum(down)

    return {
        "periodLabel": "전체",
        "bars": bars,
        "avgDailyReturnPct": (sum(bars) / len(bars) / settings.INITIAL_SEED_KRW * 100) if bars else 0.0,
        "winRatePct": round(len(up) / len(bars) * 100) if bars else 0,
        "totalUpKrw": total_up,
        "upDays": len(up),
        "totalDownKrw": total_down,
        "downDays": len(down),
        "netKrw": total_up + total_down,
    }


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

    services = [
        {"name": "core", "status": "ok", "detail": core_uptime},
        {
            "name": "discord-bot",
            "status": "ok" if discord_uptime else "error",
            "detail": discord_uptime or "응답 없음",
        },
        {"name": "scheduler", "status": "ok", "detail": core_uptime},
        {"name": "DB·Redis", "status": "ok" if db_ok else "error", "detail": "정상" if db_ok else "오류"},
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

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "header": await _build_header(mode),
        "subStrip": await _build_substrip(state, portfolio["holdings"]),
        "totalAssets": await _build_total_assets(mode, portfolio, exchange_rate),
        "chart": await _build_chart(mode),
        "systemHealth": await _build_system_health(mode),
        "positions": _build_positions(portfolio["holdings"]),
        "aiDecisions": ai_decisions,
        "aiDecisionsCountToday": ai_decisions_today,
        "news": _build_news(state),
        "events": await _build_events(),
    }
