"""리포트 텍스트 생성 — 하루 6회 정기 리포트 + 즉시 리포트 (docs/REPORT.md)."""

from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import structlog

from core.config import settings
from core.db import store as db
from core.events.publisher import publish_event
from core.fund.manager import fund_manager
from core.market_data.collector import collect_market_snapshot
from core.market_data.watchlist import get_watchlist
from core.models import Market
from core.report import chart

log = structlog.get_logger(__name__)

ReportType = Literal["pre_market", "midday", "close", "weekly", "on_demand"]

_KST = ZoneInfo("Asia/Seoul")
_REPORTS_DIR = Path("logs/reports")

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


async def generate_report(market: Market, report_type: ReportType) -> str:
    """REPORT.md 14개 필수 항목(시장 요약·지수·환율·공포탐욕지수·인기종목·
    거래량 급증·등락률 TOP10·보유종목 분석·기술적 분석·AI 예상/추천·
    리스크 요소·오늘 전략)을 포함한 마크다운 리포트를 생성한다.

    지수·공포탐욕지수·토스 인기 종목은 현재 토스증권 API에 해당 엔드포인트가
    없어 연동 전까지 "데이터 소스 미연동"으로 표기한다 (docs/TOSS_API.md 엔드포인트 표 기준).
    """
    watchlist_items = await get_watchlist(market)
    symbols = [item["symbol"] for item in watchlist_items]
    snapshot = (
        await collect_market_snapshot(market, symbols)
        if symbols
        else {"prices": {}, "holdings": [], "exchange_rate_krw_usd": None}
    )

    mode: Literal["LIVE", "SIMULATION"] = "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
    portfolio = await fund_manager.get_portfolio_status(mode)

    now = datetime.now(_KST)
    lines: list[str] = [
        f"# [빈] {market} {_REPORT_TITLES[report_type]} — {now:%Y-%m-%d %H:%M} KST",
        "",
        "## 1. 오늘 시장 요약",
        f"운영 모드: {settings.run_mode} | 관심 종목 {len(symbols)}개 추적 중",
        "",
        "## 2. 지수 현황",
        "데이터 소스 미연동 (토스증권 API에 지수 엔드포인트 없음)",
        "",
        "## 3. 환율",
        f"USD/KRW: {snapshot.get('exchange_rate_krw_usd') or '데이터 없음'}",
        "",
        "## 4. 공포탐욕지수",
        "데이터 소스 미연동",
        "",
        "## 5. 토스 인기 종목 TOP 10",
        "데이터 소스 미연동",
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
    if portfolio["holdings"]:
        for h in portfolio["holdings"]:
            lines.append(
                f"- {h['symbol']} ({h['market']}) {h['quantity']}주 | "
                f"평균단가 {h['avgPrice']:,.0f} | 현재가 {h['currentPrice']:,.0f} | "
                f"수익률 {h['pnlPct']:+.1%}"
            )
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
        if rsi is not None and rsi < 30:
            recommendation = "BUY"
        elif rsi is not None and rsi > 70:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"
        lines.append(f"- {symbol}: {recommendation} (RSI 기준 {_rsi_signal(rsi)})")

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


async def generate_weekly_report() -> str:
    """매주 월요일 장 시작 전 발송되는 주간 성과 리포트."""
    mode: Literal["LIVE", "SIMULATION"] = "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
    portfolio = await fund_manager.get_portfolio_status(mode)
    rebalance = await fund_manager.weekly_rebalance(mode)
    now = datetime.now(_KST)

    return "\n".join(
        [
            f"# [빈] 주간 성과 리포트 — {now:%Y-%m-%d}",
            "",
            f"총 자산: {portfolio['totalValueKrw']:,} KRW",
            f"누적 수익률: {portfolio['cumulativePnlPct']:+.2%} ({portfolio['cumulativePnlKrw']:+,} KRW)",
            f"오늘 실현 손익: {portfolio['todayPnlKrw']:+,} KRW",
            "",
            "## 자금 정산",
            f"Claude API 비용 충당    {rebalance.api_cost_covered_krw:,} KRW",
            f"운용 자금 재투자        {rebalance.reinvested_krw:,} KRW",
            f"현금 버퍼 적립          {rebalance.buffer_added_krw:,} KRW",
        ]
    )


def _report_filename(market: str) -> Path:
    now = datetime.now(_KST)
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR / f"report_{market.lower()}_{now:%Y-%m-%d_%H%M}.md"


async def generate_and_publish(
    market: Literal["KR", "US", "ALL"],
    report_type: ReportType,
    correlation_id: str | None = None,
) -> None:
    """리포트 생성 → 마크다운 파일 저장 → 그래프 생성 → `report_ready` 이벤트 발행.

    `/api/v1/reports/generate`가 202로 즉시 응답한 뒤 백그라운드로 실행하는 지연 작업이다
    (docs/INTERNAL_API.md "동기 vs 지연 응답").

    docs/REPORT.md가 명시한 8종 중 6종(보유 비중·손익 기여·거래량 변화·자산 추이·
    포트폴리오 수익률·누적 수익률)을 실데이터로 생성한다. 업종 분포·시장 지수 비교는
    섹터 분류·지수 데이터 소스가 없어(위 "2. 지수 현황" 참고) 생성하지 않는다.
    """
    markets: list[Market] = ["KR", "US"] if market == "ALL" else [market]  # type: ignore[list-item]

    content_md = "\n\n---\n\n".join(
        [await generate_report(m, report_type) for m in markets]
    )

    _report_filename(market).write_text(content_md, encoding="utf-8")

    chart_paths: list[str] = []
    try:
        mode: Literal["LIVE", "SIMULATION"] = (
            "LIVE" if settings.run_mode == "LIVE" else "SIMULATION"
        )
        portfolio = await fund_manager.get_portfolio_status(mode)
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
        for m in markets:
            watchlist_items = await get_watchlist(m)
            symbols = [item["symbol"] for item in watchlist_items]
            if not symbols:
                continue
            snapshot = await collect_market_snapshot(m, symbols)
            for symbol, data in snapshot["prices"].items():
                if "volume_ratio" in data:
                    volume_by_symbol[symbol] = data["volume_ratio"]
        if volume_by_symbol:
            chart_paths.append(str(chart.render_volume_histogram(volume_by_symbol)))

        # 시계열(자산 추이·수익률)은 simulation_portfolio_snapshots에만 존재한다 — LIVE는
        # 스냅샷 테이블이 아직 없어(daily_pnl 미사용) 시계열 그래프를 생성할 수 없다.
        if mode == "SIMULATION":
            snapshots = await db.get_recent_simulation_snapshots()
            if len(snapshots) >= 2:
                dates = [s["snapshot_at"].strftime("%m-%d %H:%M") for s in snapshots]
                values = [float(s["total_value_krw"]) for s in snapshots]
                chart_paths.append(str(chart.render_asset_value_chart(dates, values)))

                first_value = values[0] or 1.0
                period_returns = [(v / first_value - 1) * 100 for v in values]
                chart_paths.append(
                    str(chart.render_portfolio_return_chart(dates, period_returns))
                )

                seed = settings.INITIAL_SEED_KRW
                cumulative_returns = [(v - seed) / seed * 100 for v in values]
                chart_paths.append(
                    str(chart.render_cumulative_return_chart(dates, cumulative_returns))
                )
    except Exception as e:  # noqa: BLE001 — 그래프 생성 실패가 텍스트 리포트 발송을 막으면 안 된다
        log.warning("chart_render_failed", error=str(e))

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
            "generatedAt": datetime.now(_KST).isoformat(),
        },
    )
