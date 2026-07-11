"""리포트 텍스트 생성 — 하루 6회 정기 리포트 + 즉시 리포트 (docs/REPORT.md)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import structlog

from core.config import settings
from core.db import store as db
from core.events.publisher import publish_event
from core.fund.manager import fund_manager
from core.market_data import indicators
from core.market_data.collector import collect_market_snapshot
from core.market_data.news import fetch_market_news
from core.market_data.watchlist import get_watchlist
from core.models import Market
from core.report import chart
from core.report import extras as report_extras
from core.report import html as report_html
from core.toss import market as toss_market

log = structlog.get_logger(__name__)

ReportType = Literal["pre_market", "midday", "close", "weekly", "on_demand"]

_KST = ZoneInfo("Asia/Seoul")
_REPORTS_DIR = Path("logs/reports")
_MARKET_NEWS_IN_REPORT = 4  # 리포트에 싣는 시장 전반 경제 뉴스 헤드라인 수

_REPORT_TITLES: dict[str, str] = {
    "pre_market": "장 시작 전 브리핑",
    "midday": "중간 리포트",
    "close": "장 마감 리포트",
    "weekly": "주간 성과 리포트",
    "on_demand": "즉시 리포트",
}


def _rsi_signal(rsi: float | None) -> str:
    if rsi is None:
        return "데이터 없음"
    if rsi > 70:
        return "과매수"
    if rsi < 30:
        return "과매도"
    return "중립"


def _recommendation(rsi: float | None) -> str:
    """RSI 기준 규칙 기반 매매 추천 — 리포트 조회는 별도 Claude 호출 없이 처리한다
    (CLAUDE.md 절대 규칙 5)."""
    if rsi is not None and rsi < 30:
        return "BUY"
    if rsi is not None and rsi > 70:
        return "SELL"
    return "HOLD"


def _empty_snapshot() -> dict:
    return {
        "prices": {},
        "holdings": [],
        "exchange_rate_krw_usd": None,
        "toss_popular_top10": [],
        "fear_greed_index": None,
    }


async def _resolve_report_inputs(
    market: Market,
    snapshot: dict | None,
    portfolio: dict | None,
    market_news: list[str] | None,
) -> tuple[dict, dict, list[str]]:
    """generate_report/HTML 렌더가 공유하는 입력을 채운다. 미리 수집한 값이 있으면
    재사용하고(generate_and_publish의 중복 수집 방지), 없으면 여기서 조회한다."""
    if snapshot is None:
        watchlist_items = await get_watchlist(market)
        symbols = [item["symbol"] for item in watchlist_items]
        snapshot = await collect_market_snapshot(market, symbols) if symbols else _empty_snapshot()
    if portfolio is None:
        mode: Literal["LIVE", "SIMULATION"] = (
            "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
        )
        portfolio = await fund_manager.get_portfolio_status(mode)
    if market_news is None:
        market_news = await fetch_market_news(market)
    return snapshot, portfolio, market_news


def build_market_view(market: Market, snapshot: dict, market_news: list[str]) -> dict:
    """HTML 렌더용 시장 뷰 dict. 신호·추천 판정은 여기서 하고 표현은 html.py가 맡는다."""
    prices: dict[str, dict] = snapshot.get("prices", {})
    surge = [s for s, d in prices.items() if d.get("volume_ratio", 0) >= 2.0]
    ranked = sorted(prices.items(), key=lambda kv: kv[1].get("volume_ratio", 0), reverse=True)
    rows = []
    for symbol, data in ranked:
        rsi = data.get("rsi_14")
        price = data.get("price")
        rows.append(
            {
                "symbol": symbol,
                "price_str": (
                    f"{price:,.0f}" if symbol.isdigit() else f"{price:,.2f}"
                ) if isinstance(price, (int, float)) else "-",
                "rsi_str": f"{rsi}" if rsi is not None else "-",
                "signal": _rsi_signal(rsi),
                "rec": _recommendation(rsi),
            }
        )
    return {
        "market": market,
        "symbols": list(prices.keys()),
        "fear_greed": snapshot.get("fear_greed_index"),
        "popular": snapshot.get("toss_popular_top10", []),
        "surge": surge,
        "rows": rows,
        "market_news": market_news[:_MARKET_NEWS_IN_REPORT],
    }


def _holdings_with_news(portfolio: dict, snapshot: dict) -> list[dict]:
    """보유 종목에 스냅샷의 종목별 뉴스 요약을 붙인다(docs/REPORT.md 9. 보유 종목 분석 —
    "종목별 최신 뉴스 요약"). collector가 이미 news_summary를 채워 두므로 추가 호출은 없다."""
    prices = snapshot.get("prices", {})
    enriched = []
    for h in portfolio.get("holdings", []):
        summary = prices.get(h["symbol"], {}).get("news_summary")
        news = summary if summary and summary != "뉴스 없음" else ""
        enriched.append({**h, "news": news})
    return enriched


async def generate_report(
    market: Market,
    report_type: ReportType,
    *,
    snapshot: dict | None = None,
    portfolio: dict | None = None,
    market_news: list[str] | None = None,
) -> str:
    """REPORT.md 14개 필수 항목(시장 요약·지수·환율·공포탐욕지수·인기종목·
    거래량 급증·등락률 TOP10·보유종목 분석·기술적 분석·AI 예상/추천·
    리스크 요소·오늘 전략)과 뉴스(시장 경제 뉴스·종목별 뉴스 요약)를 포함한 마크다운
    리포트를 생성한다. 미리 수집한 snapshot/portfolio/market_news를 넘기면 재사용한다.

    시장 지수(KOSPI·NASDAQ)는 토스증권 API에 해당 엔드포인트가 없어 "데이터 소스
    미연동"으로 표기한다(docs/TOSS_API.md 엔드포인트 표 기준). 공포탐욕지수·토스 인기
    종목은 관심 종목 기반 대체 지표(`collector._fear_greed_index`/`_popular_top10`)를 사용한다.
    """
    snapshot, portfolio, market_news = await _resolve_report_inputs(
        market, snapshot, portfolio, market_news
    )
    symbols = list(snapshot.get("prices", {}).keys())
    news_headlines = market_news[:_MARKET_NEWS_IN_REPORT]

    now = datetime.now(_KST)
    lines: list[str] = [
        f"# [빈] {market} {_REPORT_TITLES[report_type]} — {now:%Y-%m-%d %H:%M} KST",
        "",
        "## 1. 오늘 시장 요약",
        f"운영 모드: {settings.run_mode} | 관심 종목 {len(symbols)}개 추적 중",
        "",
        "### 시장 경제 뉴스",
    ]
    if news_headlines:
        lines += [f"- {headline}" for headline in news_headlines]
    else:
        lines.append("수집된 시장 뉴스 없음")

    lines += [
        "",
        "## 2. 지수 현황",
        "데이터 소스 미연동 (토스증권 API에 지수 엔드포인트 없음)",
        "",
        "## 3. 환율",
        f"USD/KRW: {snapshot.get('exchange_rate_krw_usd') or '데이터 없음'}",
        "",
        "## 4. 공포탐욕지수",
        (
            f"{snapshot['fear_greed_index']} / 100 (관심 종목 등락 비율 기반 대체 지표)"
            if snapshot.get("fear_greed_index") is not None
            else "데이터 없음 (관심 종목 등락 데이터 부족)"
        ),
        "",
        "## 5. 토스 인기 종목 TOP 10",
        (
            ", ".join(snapshot["toss_popular_top10"])
            if snapshot.get("toss_popular_top10")
            else "해당 없음 (관심 종목 내 거래량 급증 없음)"
        ),
        "",
        "## 6. 거래량 급증 종목",
    ]

    surge = [
        symbol
        for symbol, data in snapshot["prices"].items()
        if data.get("volume_ratio", 0) >= 2.0
    ]
    lines.append(", ".join(surge) if surge else "해당 없음")

    lines += [
        "",
        "## 7. 상승률 TOP 10 / 8. 하락률 TOP 10",
        "관심 종목 범위 내 거래량비 상위 종목 (전체 시장 스캔은 지원하지 않음)",
    ]
    ranked = sorted(
        snapshot["prices"].items(), key=lambda kv: kv[1].get("volume_ratio", 0), reverse=True
    )
    for symbol, data in ranked[:10]:
        lines.append(f"- {symbol}: 현재가 {data.get('price', '-')}")

    lines += ["", "## 9. 보유 종목 분석"]
    holdings = _holdings_with_news(portfolio, snapshot)
    if holdings:
        for h in holdings:
            lines.append(
                f"- {h['symbol']} ({h['market']}) {h['quantity']}주 | "
                f"평균단가 {h['avgPrice']:,.0f} | 현재가 {h['currentPrice']:,.0f} | "
                f"수익률 {h['pnlPct']:+.1%}"
            )
            if h["news"]:
                lines.append(f"  📰 {h['news']}")
    else:
        lines.append("보유 종목 없음")

    lines += ["", "## 10. 기술적 분석"]
    for symbol, data in snapshot["prices"].items():
        rsi = data.get("rsi_14")
        lines.append(
            f"- {symbol}: RSI {rsi if rsi is not None else '-'} ({_rsi_signal(rsi)}) | "
            f"MACD {data.get('macd', '-')}/{data.get('macd_signal', '-')} | "
            f"EMA20/60 {data.get('ema_20', '-')}/{data.get('ema_60', '-')}"
        )

    lines += [
        "",
        "## 11. AI 예상 / 12. AI 추천",
        "지표 기반 자동 요약 (리포트 조회는 별도 Claude 호출 없이 처리 — API 비용 절감, CLAUDE.md 절대 규칙 5)",
    ]
    for symbol, data in snapshot["prices"].items():
        rsi = data.get("rsi_14")
        lines.append(f"- {symbol}: {_recommendation(rsi)} (RSI 기준 {_rsi_signal(rsi)})")

    lines += [
        "",
        "## 13. 리스크 요소",
        f"일일 손실 한도 {settings.MAX_DAILY_LOSS_KRW:,} KRW | "
        f"종목당 상한 {settings.MAX_POSITION_RATIO:.0%} | "
        f"긴급정지 {'활성화' if settings.EMERGENCY_STOP else '비활성'}",
        "",
        "## 14. 오늘 전략",
        f"관심 종목 {len(symbols)}개 대상 규칙 기반 필터 우선 적용, "
        "불명확한 신호만 Claude 판단으로 넘긴다 (docs/BIN.md).",
    ]

    return "\n".join(lines)


def _weekly_trade_metrics(all_trades: list[dict], week_ago: datetime) -> dict:
    """docs/REPORT.md "일일·주간·월간 성과 지표" — 승률·평균 수익률·최대 손익·수익 팩터·
    평균 보유 기간을 이번 주(최근 7일) 체결 내역으로 계산한다.

    수익률(%)은 거래별로 저장돼 있지 않아 `pnl_krw`와 체결 대금으로 원가를 역산한다
    (원가 = 대금 - 손익, 수익률 = 손익 / 원가) — Position의 가중평균단가 기준 실현손익과
    일치한다. 평균 보유 기간은 조회 기간 이전에 열린 매수 lot도 매칭해야 하므로
    `all_trades`(전체 이력)를 받아 FIFO로 계산한다.
    """
    week_trades = [t for t in all_trades if t["created_at"] >= week_ago]
    buys = [t for t in week_trades if t["action"] == "BUY"]
    sells = [t for t in week_trades if t["action"] == "SELL" and t["pnl_krw"] is not None]

    returns: list[tuple[str, float]] = []
    for t in sells:
        notional = float(t["fill_price"]) * t["quantity"]
        cost_basis = notional - t["pnl_krw"]
        pct = (t["pnl_krw"] / cost_basis) if cost_basis else 0.0
        returns.append((t["symbol"], pct))

    win_count = sum(1 for _, pct in returns if pct > 0)
    losers = [r for r in returns if r[1] < 0]
    winners = [r for r in returns if r[1] > 0]

    gross_profit = sum(t["pnl_krw"] for t in sells if t["pnl_krw"] > 0)
    gross_loss = abs(sum(t["pnl_krw"] for t in sells if t["pnl_krw"] < 0))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        # 손실 거래가 없으면 비율이 정의되지 않는다 — core/strategy/backtest.py와 동일한
        # 유한한 상한값 표기 규칙을 따른다.
        profit_factor = 999.0 if gross_profit > 0 else 0.0

    return {
        "total_count": len(week_trades),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "win_rate": win_count / len(returns) if returns else 0.0,
        "avg_return": sum(pct for _, pct in returns) / len(returns) if returns else 0.0,
        "max_win": max(winners, key=lambda r: r[1]) if winners else None,
        "max_loss": min(losers, key=lambda r: r[1]) if losers else None,
        "profit_factor": profit_factor,
        "avg_holding_days": indicators.calculate_avg_holding_days(all_trades, since=week_ago),
    }


def _next_week_direction(metrics: dict, mdd: float) -> str:
    """규칙 기반 다음 주 전략 방향 — 리포트 조회는 별도 Claude 호출 없이 처리한다
    (CLAUDE.md 절대 규칙 5)."""
    if metrics["sell_count"] == 0:
        return "이번 주 체결된 매도가 없어 성과 평가 보류 — 관심 종목 신호 관찰을 지속한다."
    if metrics["win_rate"] < 0.4 or mdd < -0.10:
        return "승률·낙폭이 저하됐다 — 신규 진입 조건을 보수적으로 조정하고 RSI 임계값을 재검토한다."
    if metrics["win_rate"] >= 0.6:
        return "현재 규칙 기반 필터를 유지하고 관심 종목 확대를 검토한다."
    return "현재 전략을 유지하며 지표 추이를 관찰한다."


async def _weekly_view() -> dict:
    """주간 성과 리포트의 계산 결과를 모은다 — 마크다운·HTML 렌더가 공유한다.

    `reports` 테이블 기록도 여기서 한 번 수행한다(마크다운·HTML을 모두 내도 중복 기록 없음)."""
    mode: Literal["LIVE", "SIMULATION"] = "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
    portfolio = await fund_manager.get_portfolio_status(mode)
    rebalance = await fund_manager.weekly_rebalance(mode)
    week_ago = datetime.now(UTC) - timedelta(days=7)

    all_trades = await db.get_all_trades(mode)
    metrics = _weekly_trade_metrics(all_trades, week_ago)

    snapshots = (
        await db.get_recent_live_snapshots(limit=2000)
        if mode == "LIVE"
        else await db.get_recent_simulation_snapshots(limit=2000)
    )
    week_values = [
        float(s["total_value_krw"]) for s in snapshots if s["snapshot_at"] >= week_ago
    ]
    mdd = indicators.calculate_max_drawdown_pct(week_values)
    sharpe = indicators.calculate_sharpe_ratio(week_values)

    max_win_str = (
        f"{metrics['max_win'][1]:+.1%} ({metrics['max_win'][0]})" if metrics["max_win"] else "해당 없음"
    )
    max_loss_str = (
        f"{metrics['max_loss'][1]:+.1%} ({metrics['max_loss'][0]})"
        if metrics["max_loss"]
        else "해당 없음"
    )

    await db.insert(
        "reports",
        {
            "mode": settings.run_mode,
            "market": "ALL",
            "report_type": "weekly",
            "summary": _one_line_summary("ALL", portfolio),
        },
    )

    return {
        "portfolio": portfolio,
        "rebalance": rebalance,
        "metrics": metrics,
        "mdd": mdd,
        "sharpe": sharpe,
        "operating_funds": await fund_manager.get_operating_funds_krw(mode),
        "max_win_str": max_win_str,
        "max_loss_str": max_loss_str,
        "direction": _next_week_direction(metrics, mdd),
    }


def _render_weekly_md(view: dict) -> str:
    now = datetime.now(_KST)
    m = view["metrics"]
    portfolio = view["portfolio"]
    rebalance = view["rebalance"]
    return "\n".join(
        [
            f"# [빈] 주간 성과 리포트 — {now:%Y-%m-%d}",
            "",
            "## 이번 주 거래 요약",
            f"총 거래 횟수    {m['total_count']}회 (매수 {m['buy_count']} / 매도 {m['sell_count']})",
            f"승률            {m['win_rate']:.1%}",
            f"평균 수익률     {m['avg_return']:+.2%}",
            f"최대 단일 손실  {view['max_loss_str']}",
            f"최대 단일 수익  {view['max_win_str']}",
            "",
            "## 성과 지표",
            f"MDD (최대 낙폭)   {view['mdd']:.1%}",
            f"샤프 지수         {view['sharpe']:.2f}",
            f"수익 팩터         {m['profit_factor']:.2f}",
            f"평균 보유 기간    {m['avg_holding_days']:.1f}일",
            f"누적 수익률       {portfolio['cumulativePnlPct']:+.2%} ({portfolio['cumulativePnlKrw']:+,} KRW)",
            "",
            "## 자금 정산",
            f"운용 자금         {view['operating_funds']:,.0f} KRW",
            f"현금 버퍼         {portfolio['cashBufferKrw']:,} KRW",
            f"Claude API 비용   -{rebalance.api_cost_covered_krw:,} KRW",
            f"순수익 재투자     +{rebalance.reinvested_krw:,} KRW",
            "",
            "## 다음 주 전략 방향",
            view["direction"],
        ]
    )


async def generate_weekly_report() -> str:
    """매주 월요일 장 시작 전 발송되는 주간 성과 리포트 마크다운 (docs/REPORT.md "주간 성과 리포트")."""
    return _render_weekly_md(await _weekly_view())


async def generate_weekly_and_publish() -> None:
    """주간 성과 리포트 생성 → 마크다운·HTML 파일 저장 → `report_ready` 이벤트 발행.

    스케줄러(월요일 장전)가 호출한다. 마크다운은 Discord Embed, HTML은 첨부 문서로 쓰인다."""
    view = await _weekly_view()
    content_md = _render_weekly_md(view)
    now = datetime.now(_KST)

    _report_filename("weekly").write_text(content_md, encoding="utf-8")
    html_content = report_html.render_weekly_report(
        run_mode=settings.run_mode,
        generated_at=now,
        view=view,
        portfolio=view["portfolio"],
    )
    html_path = _report_html_filename("weekly")
    html_path.write_text(html_content, encoding="utf-8")

    await publish_event(
        "report_ready",
        mode=settings.run_mode,
        market=None,
        payload={
            "title": "[빈] 주간 성과 리포트",
            "market": "ALL",
            "reportType": "weekly",
            "contentMd": content_md[:3800],
            "chartPaths": [],
            "htmlPath": str(html_path),
            "generatedAt": now.isoformat(),
        },
    )


async def _market_composite_series(market: Market) -> list[float] | None:
    """관심 종목 일봉 종가의 동일가중 평균 시계열.

    docs/TOSS_API.md에 KOSPI/NASDAQ 같은 시장 지수 엔드포인트가 없어, 관심 종목의
    일봉 종가를 동일가중 평균한 값을 지수 비교 차트의 대체 시계열로 사용한다.
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
    return [sum(day_values) / len(day_values) for day_values in zip(*trimmed)]


# 파일명에 쓰는 시장 라벨을 상수 화이트리스트로 고정한다 — market은 `/report` API body에서
# 오는 사용자 입력이므로(core/api/routes.py) 경로 조작(path traversal)을 막기 위해 알려진
# 값만 리터럴로 매핑하고, 그 외에는 "unknown"으로 대체한다.
_SAFE_MARKET_LABELS: dict[str, str] = {"KR": "kr", "US": "us", "ALL": "all", "WEEKLY": "weekly"}


def _safe_market_label(market: str) -> str:
    return _SAFE_MARKET_LABELS.get(str(market).upper(), "unknown")


def _report_filename(market: str) -> Path:
    now = datetime.now(_KST)
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR / f"report_{_safe_market_label(market)}_{now:%Y-%m-%d_%H%M}.md"


def _report_html_filename(market: str) -> Path:
    now = datetime.now(_KST)
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR / f"report_{_safe_market_label(market)}_{now:%Y-%m-%d_%H%M}.html"


def _one_line_summary(market: str, portfolio: dict) -> str:
    """docs/MONITOR.md "리포트" 서브스트립용 한 줄 요약 — 전체 마크다운(REPORT.md 14개
    항목)과 별개로, 이미 계산된 포트폴리오 수치만으로 규칙 기반 구성한다(Claude 미호출,
    CLAUDE.md 절대 규칙 5)."""
    pnl = portfolio["todayPnlKrw"]
    pnl_desc = f"{'+' if pnl >= 0 else ''}{pnl:,}원"
    cum_pct = portfolio["cumulativePnlPct"]
    return f"{market} 금일 {pnl_desc} · 누적 {cum_pct:+.1%} · 보유 {len(portfolio['holdings'])}종목"


def _render_extras_md(extras: dict) -> str:
    """확장 지표의 compact 마크다운 요약 (docs/REPORT.md "확장 지표"). 전체 상세는 HTML 문서에."""
    un = extras.get("unrealized") or {}
    safety = extras.get("safety") or {}
    ai = extras.get("ai") or {}
    counts = ai.get("today_counts", {})
    alpha = extras.get("alpha")
    fx = extras.get("fx")
    calendar = extras.get("calendar") or {}
    timeline = extras.get("timeline") or []

    lines = [
        "",
        "## 15. 리스크 · 성과 확장 지표",
        f"미실현 손익: {un.get('total_krw', 0):+,} KRW ({un.get('total_pct', 0):+.1%})",
        f"Safety Gate: 일일 손실 {safety.get('daily_loss', 0):,}/{safety.get('daily_limit', 0):,} KRW "
        f"(소진 {safety.get('daily_usage', 0):.0%}) | 종목당 상한 {safety.get('cap', 0):.0%} | "
        f"VI/거래정지 {', '.join(safety.get('restricted', [])) or '없음'}",
        f"AI 결정(오늘): BUY {counts.get('BUY', 0)} · HOLD {counts.get('HOLD', 0)} · "
        f"SELL {counts.get('SELL', 0)} | API {ai.get('api_calls_today', 0)}회 · "
        f"이번달 비용 {ai.get('api_cost_month_krw', 0):,} KRW",
    ]
    if alpha:
        lines.append(
            f"초과수익 α: {alpha['alpha_pp']:+.1%}p (포트 {alpha['portfolio_pct']:+.1%} vs "
            f"벤치 {alpha['benchmark_pct']:+.1%})"
        )
    if fx:
        lines.append(
            f"환율 민감도: USD/KRW {fx['usd_krw']:,.1f} | US 노출 {fx['us_exposure_krw']:,} KRW | "
            f"1% 변동 시 {fx['sensitivity_1pct_krw']:+,} KRW"
        )
    session = " · ".join(
        f"{m} {'장중' if (v or {}).get('open') else '장마감'}" for m, v in calendar.items()
    )
    if session:
        lines.append(f"세션: {session}")
    lines.append(f"오늘 체결: {len(timeline)}건")
    return "\n".join(lines)


async def generate_and_publish(
    market: Literal["KR", "US", "ALL"],
    report_type: ReportType,
    correlation_id: str | None = None,
) -> None:
    """리포트 생성 → 마크다운 파일 저장 → 그래프 생성 → `report_ready` 이벤트 발행.

    `/api/v1/reports/generate`가 202로 즉시 응답한 뒤 백그라운드로 실행하는 지연 작업이다
    (docs/INTERNAL_API.md "동기 vs 지연 응답").

    docs/REPORT.md가 명시한 8종 중 7종(보유 비중·손익 기여·거래량 변화·자산 추이·
    포트폴리오 수익률·누적 수익률·시장 지수 비교)을 실데이터로 생성한다. 자산 추이·수익률
    시계열은 LIVE는 live_portfolio_snapshots, SIMULATION은 simulation_portfolio_snapshots
    (둘 다 core/trading/loop.py publish_status_update가 매 틱 적재)를 사용한다. 시장 지수
    비교는 토스 API에 KOSPI/NASDAQ 엔드포인트가 없어(위 "2. 지수 현황" 참고) 관심 종목
    일봉 종가의 동일가중 평균을 대체 시계열로 사용한다(`_market_composite_series`).
    업종 분포만 섹터 분류 데이터 소스가 없어 생성하지 않는다.

    마크다운(Discord Embed)과 HTML 문서(그래프를 base64로 인라인한 첨부 파일)를 함께
    생성하며, 마크다운·HTML·차트는 시장별 스냅샷을 한 번만 수집해 공유한다.
    """
    markets: list[Market] = ["KR", "US"] if market == "ALL" else [market]  # type: ignore[list-item]
    now = datetime.now(_KST)

    mode: Literal["LIVE", "SIMULATION"] = "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
    portfolio = await fund_manager.get_portfolio_status(mode)

    # 시장별 입력(스냅샷·시장 뉴스)을 한 번만 수집해 마크다운·HTML·차트가 공유한다.
    market_inputs: dict[str, tuple[dict, list[str]]] = {}
    for m in markets:
        snapshot, _, m_news = await _resolve_report_inputs(m, None, portfolio, None)
        market_inputs[m] = (snapshot, m_news)

    content_md = "\n\n---\n\n".join(
        [
            await generate_report(
                m, report_type, snapshot=snap, portfolio=portfolio, market_news=m_news
            )
            for m, (snap, m_news) in market_inputs.items()
        ]
    )

    # 확장 지표(미실현 손익·Safety Gate·AI 결정·α·환율·세션·체결 타임라인) — 실패해도
    # 본문을 막지 않도록 방어적으로 수집한다 (docs/REPORT.md "확장 지표").
    extras: dict | None = None
    try:
        benchmark_series = await _market_composite_series(markets[0])
        snapshots_by_market = {m: snap for m, (snap, _n) in market_inputs.items()}
        extras = await report_extras.gather_report_extras(
            markets, snapshots_by_market, portfolio, mode, benchmark_series
        )
        if extras:
            content_md += "\n\n" + _render_extras_md(extras)
    except Exception as e:  # noqa: BLE001 — 확장 지표 실패가 리포트 발송을 막으면 안 된다
        log.warning("report_extras_failed", error=str(e))

    _report_filename(market).write_text(content_md, encoding="utf-8")

    await db.insert(
        "reports",
        {
            "mode": settings.run_mode,
            "market": market,
            "report_type": report_type,
            "summary": _one_line_summary(market, portfolio),
        },
    )

    chart_paths: list[str] = []
    try:
        if portfolio["holdings"]:
            holdings_value = {
                h["symbol"]: h["quantity"] * h["currentPrice"] for h in portfolio["holdings"]
            }
            chart_paths.append(str(chart.render_holdings_pie_chart(holdings_value)))

            pnl_by_symbol = {
                h["symbol"]: (h["currentPrice"] - h["avgPrice"]) * h["quantity"]
                for h in portfolio["holdings"]
            }
            chart_paths.append(str(chart.render_pnl_contribution_chart(pnl_by_symbol)))

        volume_by_symbol: dict[str, float] = {}
        for snap, _news in market_inputs.values():
            for symbol, data in snap["prices"].items():
                if "volume_ratio" in data:
                    volume_by_symbol[symbol] = data["volume_ratio"]
        if volume_by_symbol:
            chart_paths.append(str(chart.render_volume_histogram(volume_by_symbol)))

        if "KR" in markets and "US" in markets:
            kr_series = await _market_composite_series("KR")
            us_series = await _market_composite_series("US")
            if kr_series and us_series:
                chart_paths.append(str(chart.render_index_comparison_chart(kr_series, us_series)))

        # 시계열(자산 추이·수익률) — LIVE는 live_portfolio_snapshots, SIMULATION은
        # simulation_portfolio_snapshots (core/trading/loop.py publish_status_update가 매 틱 적재).
        snapshots = (
            await db.get_recent_live_snapshots()
            if mode == "LIVE"
            else await db.get_recent_simulation_snapshots()
        )
        if len(snapshots) >= 2:
            dates = [s["snapshot_at"].strftime("%m-%d %H:%M") for s in snapshots]
            values = [float(s["total_value_krw"]) for s in snapshots]
            chart_paths.append(str(chart.render_asset_value_chart(dates, values)))

            first_value = values[0] or 1.0
            period_returns = [(v / first_value - 1) * 100 for v in values]
            chart_paths.append(str(chart.render_portfolio_return_chart(dates, period_returns)))

            seed = settings.INITIAL_SEED_KRW
            cumulative_returns = [(v - seed) / seed * 100 for v in values]
            chart_paths.append(str(chart.render_cumulative_return_chart(dates, cumulative_returns)))
    except Exception as e:  # noqa: BLE001 — 그래프 생성 실패가 텍스트 리포트 발송을 막으면 안 된다
        log.warning("chart_render_failed", error=str(e))

    # HTML 문서 — 그래프 생성 실패 시에도 텍스트/표는 나오도록 차트 이후에 렌더한다.
    html_path_str = ""
    try:
        market_views = [
            build_market_view(m, snap, m_news) for m, (snap, m_news) in market_inputs.items()
        ]
        html_content = report_html.render_market_report(
            report_title=f"{market} {_REPORT_TITLES[report_type]}",
            run_mode=settings.run_mode,
            generated_at=now,
            portfolio=portfolio,
            market_views=market_views,
            chart_paths=chart_paths,
            extras=extras,
        )
        html_path = _report_html_filename(market)
        html_path.write_text(html_content, encoding="utf-8")
        html_path_str = str(html_path)
    except Exception as e:  # noqa: BLE001 — HTML 생성 실패가 마크다운 리포트 발송을 막으면 안 된다
        log.warning("html_render_failed", error=str(e))

    await publish_event(
        "report_ready",
        mode=settings.run_mode,
        market=None if market == "ALL" else market,
        correlation_id=correlation_id,
        payload={
            "title": f"[빈] {market} {_REPORT_TITLES[report_type]}",
            "market": market,
            "reportType": report_type,
            "contentMd": content_md[:3800],
            "chartPaths": chart_paths,
            "htmlPath": html_path_str,
            "generatedAt": now.isoformat(),
        },
    )
