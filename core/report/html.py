"""HTML 리포트 문서 생성 — 자기완결(self-contained) 대시보드 HTML을 만든다 (docs/REPORT.md).

마크다운(#stock-analyze Embed용)과 별개로, 같은 데이터를 받아 한 파일로 열리는 HTML
문서를 렌더한다. 그래프 PNG는 base64 data URI로 인라인해 외부 의존 없이 어디서든(디스코드
첨부·브라우저) 그대로 열린다. 텍스트 계산·판정은 generator가 담당하고 이 모듈은 표현만
맡는다(순환 import 방지 — generator를 import하지 않는다).
"""

import base64
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# generator가 판정한 신호·추천 텍스트 → CSS 클래스 (표현만 담당).
_SIGNAL_CLASS = {"과매수": "over", "과매도": "under", "중립": "mid", "데이터 없음": "mid"}
_REC_CLASS = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}

# 차트 파일명 접미사 → (제목, 부제). generator가 넘긴 경로 순서대로 캡션을 붙인다.
_CHART_CAPTIONS: list[tuple[str, str, str]] = [
    ("asset_value", "총 자산 추이", "최근 스냅샷 (KRW)"),
    ("cumulative_return", "누적 수익률", "시드 대비 (%)"),
    ("portfolio_return", "포트폴리오 수익률", "기간 시작 대비 (%)"),
    ("index_comparison", "시장 지수 비교", "관심 종목 대체 지표, 시작=100"),
    ("holdings_pie", "보유 종목 비중", "quantity × currentPrice"),
    ("pnl_contribution", "종목별 손익 기여", "KRW"),
    ("volume_histogram", "거래량 변화율", "전일 대비"),
]

_STYLE = """
:root{--bg:#f2f4f2;--panel:#fff;--panel-2:#f7f9f7;--line:#dde3df;--ink:#16221d;--ink-2:#4b5a53;--ink-3:#7b8a82;--teal:#0e9d81;--teal-soft:#e2f4ee;--kr:#d1553a;--kr-soft:#f8e7e1;--us:#1877c9;--us-soft:#e2eef9;--gain:#0e9d81;--loss:#d84b40;--shadow:0 1px 2px rgba(20,34,29,.05),0 8px 24px rgba(20,34,29,.05);--radius:14px;--mono:ui-monospace,"SF Mono","Roboto Mono",Menlo,monospace;--sans:system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR","Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#0d1518;--panel:#141e22;--panel-2:#18252a;--line:#223035;--ink:#e8efeb;--ink-2:#a6b5ae;--ink-3:#6f8079;--teal:#1fbd9c;--teal-soft:#10312a;--kr:#e87057;--kr-soft:#33201b;--us:#4ca2e8;--us-soft:#16283a;--gain:#22c39f;--loss:#ec6a5f;--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35)}}
:root[data-theme=light]{--bg:#f2f4f2;--panel:#fff;--panel-2:#f7f9f7;--line:#dde3df;--ink:#16221d;--ink-2:#4b5a53;--ink-3:#7b8a82;--teal:#0e9d81;--teal-soft:#e2f4ee;--kr:#d1553a;--kr-soft:#f8e7e1;--us:#1877c9;--us-soft:#e2eef9;--gain:#0e9d81;--loss:#d84b40}
:root[data-theme=dark]{--bg:#0d1518;--panel:#141e22;--panel-2:#18252a;--line:#223035;--ink:#e8efeb;--ink-2:#a6b5ae;--ink-3:#6f8079;--teal:#1fbd9c;--teal-soft:#10312a;--kr:#e87057;--kr-soft:#33201b;--us:#4ca2e8;--us-soft:#16283a;--gain:#22c39f;--loss:#ec6a5f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:clamp(20px,4vw,44px) clamp(16px,4vw,40px) 72px}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
header.top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:20px;padding-bottom:22px;margin-bottom:30px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:14px}
.mark{width:46px;height:46px;border-radius:12px;flex:none;background:linear-gradient(150deg,var(--teal),#0c7a64);display:grid;place-items:center;color:#fff;font-weight:800;font-size:24px}
.brand h1{margin:0;font-size:25px;font-weight:800;letter-spacing:-.02em;line-height:1.1}
.brand h1 span{color:var(--ink-3);font-weight:600}
.brand p{margin:3px 0 0;font-size:13px;color:var(--ink-2)}
.meta{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.pill{display:inline-flex;align-items:center;gap:7px;padding:5px 12px;border-radius:100px;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;background:var(--teal-soft);color:var(--teal);border:1px solid color-mix(in srgb,var(--teal) 28%,transparent)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:var(--teal)}
.meta .stamp{font-size:13px;color:var(--ink-2)}
.meta .stamp b{color:var(--ink);font-weight:700}
.sec-head{display:flex;align-items:baseline;gap:12px;margin:40px 0 16px}
.sec-head .k{font-family:var(--mono);font-size:12px;color:var(--ink-3);font-weight:600}
.sec-head h2{margin:0;font-size:17px;font-weight:750;letter-spacing:-.01em}
.sec-head .rule{flex:1;height:1px;background:var(--line)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--teal);opacity:.85}
.kpi .label{font-size:12px;color:var(--ink-2);font-weight:600}
.kpi .val{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:26px;font-weight:700;margin-top:6px;letter-spacing:-.02em}
.kpi .val small{font-size:14px;color:var(--ink-3);font-weight:600}
.kpi .sub{font-size:12.5px;margin-top:4px;font-family:var(--mono)}
.up{color:var(--gain)}.down{color:var(--loss)}
.markets{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.mkt{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.mkt>.hd{display:flex;align-items:center;gap:10px;padding:15px 18px;border-bottom:1px solid var(--line)}
.mkt .hd h3{margin:0;font-size:15px;font-weight:750}
.mkt .hd .tag{margin-left:auto;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:3px 9px;border-radius:6px}
.mkt.kr .tag{background:var(--kr-soft);color:var(--kr)}.mkt.us .tag{background:var(--us-soft);color:var(--us)}
.mkt.kr>.hd{box-shadow:inset 3px 0 0 var(--kr)}.mkt.us>.hd{box-shadow:inset 3px 0 0 var(--us)}
.mkt .body{padding:16px 18px;display:flex;flex-direction:column;gap:16px}
.fg{display:flex;flex-direction:column;gap:7px}
.fg .row{display:flex;justify-content:space-between;align-items:baseline}
.fg .row .t{font-size:12.5px;color:var(--ink-2);font-weight:600}
.fg .row .v{font-family:var(--mono);font-weight:700;font-size:15px}
.meter{height:8px;border-radius:6px;background:linear-gradient(90deg,#d84b40,#e6a23c 50%,#0e9d81);position:relative;opacity:.9}
.meter .mk{position:absolute;top:-3px;width:3px;height:14px;border-radius:2px;background:var(--ink);box-shadow:0 0 0 2px var(--panel)}
.mini-label{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);margin-bottom:7px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-family:var(--mono);font-size:12px;font-weight:600;padding:3px 9px;border-radius:7px;background:var(--panel-2);border:1px solid var(--line)}
table.tbl{width:100%;border-collapse:collapse;font-size:13px}
table.tbl th{text-align:right;font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--ink-3);padding:0 0 8px;border-bottom:1px solid var(--line)}
table.tbl th:first-child{text-align:left}
table.tbl td{padding:9px 0;border-bottom:1px solid var(--line);text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
table.tbl td:first-child{text-align:left;font-weight:700}
table.tbl tr:last-child td{border-bottom:none}
.sig{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:6px;font-family:var(--sans)}
.sig.buy,.sig.under{background:var(--teal-soft);color:var(--teal)}
.sig.sell,.sig.over{background:color-mix(in srgb,var(--loss) 16%,transparent);color:var(--loss)}
.sig.hold,.sig.mid{background:var(--panel-2);color:var(--ink-2);border:1px solid var(--line)}
.news{display:flex;flex-direction:column;gap:9px}
.news .item{font-size:12.5px;color:var(--ink-2);padding-left:14px;position:relative;line-height:1.45}
.news .item::before{content:"";position:absolute;left:0;top:8px;width:6px;height:6px;border-radius:50%;background:var(--teal);opacity:.7}
.news .item b{color:var(--ink);font-weight:700}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.card .pad{padding:6px 20px 8px}
.scroll{overflow-x:auto}
.weekly{display:grid;grid-template-columns:1.4fr 1fr;gap:18px}
.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border-radius:12px;overflow:hidden;border:1px solid var(--line)}
.metric{background:var(--panel);padding:14px 16px}
.metric .m-l{font-size:12px;color:var(--ink-2);font-weight:600}
.metric .m-v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:20px;font-weight:700;margin-top:4px}
.metric .m-s{font-size:11.5px;color:var(--ink-3);margin-top:2px;font-family:var(--mono)}
.settle{display:flex;flex-direction:column}
.settle .st-row{display:flex;justify-content:space-between;align-items:baseline;padding:11px 2px;border-bottom:1px dashed var(--line);font-size:13.5px}
.settle .st-row:last-child{border-bottom:none}
.settle .st-row .lab{color:var(--ink-2);font-weight:600}
.settle .st-row .amt{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:700}
.direction{margin-top:14px;padding:14px 16px;border-radius:12px;background:var(--teal-soft);border:1px solid color-mix(in srgb,var(--teal) 25%,transparent);font-size:13.5px;display:flex;gap:10px}
.direction .ic{color:var(--teal);font-weight:800}
.charts{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
figure.chart{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
figure.chart img{display:block;width:100%;height:auto;background:#fff}
figure.chart figcaption{padding:10px 16px;font-size:12.5px;color:var(--ink-2);border-top:1px solid var(--line);display:flex;gap:8px;align-items:baseline}
figure.chart figcaption b{color:var(--ink);font-weight:700;font-size:13px}
.notes{margin-top:18px;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius);padding:18px 20px}
.notes h4{margin:0 0 10px;font-size:13px;font-weight:750}
.notes ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:7px}
.notes li{font-size:12.5px;color:var(--ink-2)}
.notes code{font-family:var(--mono);font-size:11.5px;background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:1px 5px;color:var(--ink)}
footer.foot{margin-top:30px;padding-top:18px;border-top:1px solid var(--line);font-size:12px;color:var(--ink-3);display:flex;flex-wrap:wrap;gap:6px 16px;justify-content:space-between}
@media (max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}.markets,.weekly,.charts{grid-template-columns:1fr}.metric-grid{grid-template-columns:repeat(2,1fr)}}
"""


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{_STYLE}</style>\n</head>\n"
        f'<body>\n<div class="wrap">\n{body}\n</div>\n</body>\n</html>\n'
    )


def _header(title: str, run_mode: str, generated_at: datetime) -> str:
    return (
        '<header class="top">'
        '<div class="brand"><div class="mark">빈</div>'
        "<div><h1>빈 <span>· Bin</span></h1>"
        "<p>AI 자동 트레이딩 봇 · KRX + US · 24/7</p></div></div>"
        f'<div class="meta"><span class="pill"><span class="dot"></span>{escape(run_mode)}</span>'
        f'<span class="stamp">{escape(title)} · <b>{generated_at:%Y-%m-%d %H:%M}</b> KST</span></div>'
        "</header>"
    )


def _sec(num: str, title: str, extra: str = "") -> str:
    return f'<div class="sec-head"><span class="k">{num}</span><h2>{title}{extra}</h2><span class="rule"></span></div>'


def _pct(x: float | None, plus: bool = True) -> str:
    if x is None:
        return "—"
    sign = "+" if plus and x >= 0 else ""
    return f"{sign}{x * 100:.2f}%"


def _kpis(portfolio: dict[str, Any]) -> str:
    total = portfolio.get("totalValueKrw")
    today = portfolio.get("todayPnlKrw", 0) or 0
    cum_pct = portfolio.get("cumulativePnlPct")
    cum_krw = portfolio.get("cumulativePnlKrw")
    cash = portfolio.get("cashBufferKrw")
    holdings = portfolio.get("holdings", [])
    kr = sum(1 for h in holdings if h.get("market") == "KR")
    us = sum(1 for h in holdings if h.get("market") == "US")

    today_cls = "up" if today >= 0 else "down"
    cum_cls = "up" if (cum_pct or 0) >= 0 else "down"
    cum_sub = f'{"+" if (cum_krw or 0) >= 0 else ""}{cum_krw:,} ₩' if cum_krw is not None else "시드 500,000 기준"

    return (
        '<div class="kpis">'
        f'<div class="kpi"><div class="label">총 자산</div><div class="val">{total:,}<small> ₩</small></div>'
        f'<div class="sub {today_cls}">금일 {"+" if today >= 0 else ""}{today:,} ₩</div></div>'
        f'<div class="kpi"><div class="label">누적 수익률</div><div class="val {cum_cls}">{_pct(cum_pct)}</div>'
        f'<div class="sub {cum_cls}">{escape(cum_sub)}</div></div>'
        f'<div class="kpi"><div class="label">현금 버퍼</div><div class="val">{cash:,}<small> ₩</small></div>'
        '<div class="sub">시드의 15% 목표선</div></div>'
        f'<div class="kpi"><div class="label">보유 종목</div><div class="val">{len(holdings)}<small> 종목</small></div>'
        f'<div class="sub">KR {kr} · US {us}</div></div>'
        "</div>"
    )


def _market_section(view: dict[str, Any]) -> str:
    market = view["market"]
    cls = "kr" if market == "KR" else "us"
    flag = "🇰🇷" if market == "KR" else "🇺🇸"
    name = "한국장 · KRX" if market == "KR" else "미국장 · US"

    fg = view.get("fear_greed")
    fg_html = (
        f'<div class="fg"><div class="row"><span class="t">공포탐욕지수 '
        f'<span style="color:var(--ink-3)">(관심 종목 대체 지표)</span></span>'
        f'<span class="v">{fg}<span style="color:var(--ink-3);font-size:12px"> / 100</span></span></div>'
        f'<div class="meter"><span class="mk" style="left:{fg}%"></span></div></div>'
        if fg is not None
        else '<div class="fg"><div class="row"><span class="t">공포탐욕지수</span>'
        '<span class="v" style="font-size:12px;color:var(--ink-3)">데이터 없음</span></div></div>'
    )

    hot = set(view.get("surge", []))
    chips = "".join(
        f'<span class="chip"{" style=color:var(--teal);border-color:var(--teal)" if s in hot else ""}>'
        f'{escape(s)}{" ▲" if s in hot else ""}</span>'
        for s in (view.get("popular") or [])
    ) or '<span class="chip">해당 없음</span>'

    def _row(r: dict[str, Any]) -> str:
        sig_cls = _SIGNAL_CLASS.get(r["signal"], "mid")
        rec_cls = _REC_CLASS.get(r["rec"], "hold")
        return (
            f"<tr><td>{escape(r['symbol'])}</td><td>{escape(r['price_str'])}</td>"
            f"<td>{escape(r['rsi_str'])}</td>"
            f'<td><span class="sig {sig_cls}">{escape(r["signal"])}</span></td>'
            f'<td><span class="sig {rec_cls}">{escape(r["rec"])}</span></td></tr>'
        )

    rows = "".join(
        _row(r) for r in view.get("rows", [])
    ) or '<tr><td colspan="5" style="text-align:center;color:var(--ink-3)">관심 종목 데이터 없음</td></tr>'

    news = view.get("market_news") or []
    news_html = (
        '<div><div class="mini-label">시장 경제 뉴스</div><div class="news">'
        + "".join(f'<div class="item">{escape(h)}</div>' for h in news)
        + "</div></div>"
        if news
        else ""
    )

    return (
        f'<section class="mkt {cls}"><div class="hd"><span style="font-size:18px">{flag}</span>'
        f'<h3>{name}</h3><span class="tag">관심 {len(view.get("symbols", []))}</span></div>'
        f'<div class="body">{fg_html}'
        f'<div><div class="mini-label">인기 · 거래량 급증</div><div class="chips">{chips}</div></div>'
        '<div class="scroll"><table class="tbl"><thead><tr><th>종목</th><th>현재가</th><th>RSI</th>'
        f'<th>신호</th><th>AI</th></tr></thead><tbody>{rows}</tbody></table></div>'
        f"{news_html}</div></section>"
    )


def _holdings_card(portfolio: dict[str, Any]) -> str:
    holdings = portfolio.get("holdings", [])
    if not holdings:
        body = '<tr><td colspan="6" style="text-align:center;color:var(--ink-3)">보유 종목 없음</td></tr>'
    else:
        body = "".join(
            f"<tr><td>{escape(h['symbol'])}</td><td>{escape(h['market'])}</td><td>{h['quantity']}</td>"
            f"<td>{h['avgPrice']:,.0f}</td><td>{h['currentPrice']:,.0f}</td>"
            f'<td class="{"up" if h["pnlPct"] >= 0 else "down"}">{"+" if h["pnlPct"] >= 0 else ""}{h["pnlPct"] * 100:.1f}%</td></tr>'
            + (
                f'<tr><td colspan="6" style="text-align:left;font-weight:400;color:var(--ink-2);'
                f'font-family:var(--sans);font-size:12px;padding-top:2px">📰 {escape(h["news"])}</td></tr>'
                if h.get("news")
                else ""
            )
            for h in holdings
        )
    return (
        '<div class="card"><div class="pad scroll"><table class="tbl"><thead><tr><th>종목</th><th>시장</th>'
        "<th>수량</th><th>평균단가</th><th>현재가</th><th>수익률</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div></div>"
    )


def _chart_data_uri(path: str) -> str | None:
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as e:
        log.warning("chart_embed_failed", path=path, error=str(e))
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def _caption_for(path: str) -> tuple[str, str]:
    for key, title, sub in _CHART_CAPTIONS:
        if key in path:
            return title, sub
    return Path(path).stem, ""


def _charts_grid(chart_paths: list[str]) -> str:
    figs = []
    for path in chart_paths:
        uri = _chart_data_uri(path)
        if uri is None:
            continue
        title, sub = _caption_for(path)
        figs.append(
            f'<figure class="chart"><img alt="{escape(title)}" src="{uri}">'
            f'<figcaption><b>{escape(title)}</b>{escape(sub)}</figcaption></figure>'
        )
    if not figs:
        return ""
    return _sec("", "그래프", ' <span style="font-weight:500;color:var(--ink-3);font-size:14px">· core/report/chart.py</span>') + f'<div class="charts">{"".join(figs)}</div>'


_NOTES = (
    '<div class="notes"><h4>리포트 생성 방식 · 주의</h4><ul>'
    "<li>본 리포트는 <code>core/report/generator.py</code> · <code>chart.py</code> · "
    "<code>html.py</code>가 생성한다. 그래프는 base64로 인라인돼 외부 의존 없이 열린다.</li>"
    "<li><b>지수 현황</b>은 토스 API에 지수 엔드포인트가 없어 미연동, 공포탐욕지수·인기 종목은 "
    "관심 종목 기반 <b>대체 지표</b>다 (docs/REPORT.md).</li>"
    "<li>보유 비중·손익 기여 차트는 환율 미반영(<code>quantity × currentPrice</code>)이라 "
    "KR·US 혼합 보유 시 US 비중이 축소돼 보인다.</li>"
    "</ul></div>"
)


def render_market_report(
    *,
    report_title: str,
    run_mode: str,
    generated_at: datetime,
    portfolio: dict[str, Any],
    market_views: list[dict[str, Any]],
    chart_paths: list[str],
) -> str:
    """시장 리포트(KR/US/ALL) HTML 문서. market_views는 시장별 뷰 dict 리스트."""
    sections = "".join(_market_section(v) for v in market_views)
    body = (
        _header(report_title, run_mode, generated_at)
        + _kpis(portfolio)
        + _sec("01", "시장별 현황")
        + f'<div class="markets">{sections}</div>'
        + _sec("02", "보유 종목 분석")
        + _holdings_card(portfolio)
        + _charts_grid(chart_paths)
        + _NOTES
        + '<footer class="foot"><span>빈(Bin) · AI 자동 트레이딩 봇</span>'
        "<span>Discord · #stock-analyze</span></footer>"
    )
    return _document(f"빈 Bin — {report_title}", body)


def render_weekly_report(
    *,
    run_mode: str,
    generated_at: datetime,
    view: dict[str, Any],
    portfolio: dict[str, Any],
) -> str:
    """주간 성과 리포트 HTML 문서. view는 generator._weekly_view()가 만든 계산 결과."""
    m = view["metrics"]

    def metric(label: str, value: str, sub: str, cls: str = "") -> str:
        return (
            f'<div class="metric"><div class="m-l">{escape(label)}</div>'
            f'<div class="m-v {cls}">{value}</div><div class="m-s">{escape(sub)}</div></div>'
        )

    win_cls = "up" if m["win_rate"] >= 0.5 else "down"
    grid = (
        '<div class="metric-grid">'
        + metric("총 거래", f'{m["total_count"]}<span style="font-size:13px;color:var(--ink-3)">회</span>', f'매수 {m["buy_count"]} · 매도 {m["sell_count"]}')
        + metric("승률", f'{m["win_rate"] * 100:.1f}%', f'{m["sell_count"]}건 중 실현', win_cls)
        + metric("평균 수익률", _pct(m["avg_return"]), "거래당 실현손익", "up" if m["avg_return"] >= 0 else "down")
        + metric("MDD", f'{view["mdd"] * 100:.1f}%', "고점 대비 최대 낙폭", "down")
        + metric("샤프 지수", f'{view["sharpe"]:.2f}', "√252 연환산")
        + metric("수익 팩터", f'{m["profit_factor"]:.2f}', "총수익 / 총손실")
        + metric("평균 보유", f'{m["avg_holding_days"]:.1f}<span style="font-size:13px;color:var(--ink-3)">일</span>', "FIFO 수량 가중")
        + metric("최대 수익", escape(view["max_win_str"]), "이번 주", "up")
        + metric("최대 손실", escape(view["max_loss_str"]), "이번 주", "down")
        + "</div>"
    )

    settle = (
        '<div class="card" style="padding:16px 20px 18px;display:flex;flex-direction:column">'
        '<div class="mini-label" style="margin-bottom:2px">자금 정산</div><div class="settle">'
        f'<div class="st-row"><span class="lab">운용 자금</span><span class="amt">{view["operating_funds"]:,.0f} ₩</span></div>'
        f'<div class="st-row"><span class="lab">현금 버퍼</span><span class="amt">{portfolio["cashBufferKrw"]:,} ₩</span></div>'
        f'<div class="st-row"><span class="lab">Claude API 비용</span><span class="amt down">-{view["rebalance"].api_cost_covered_krw:,} ₩</span></div>'
        f'<div class="st-row"><span class="lab">순수익 재투자</span><span class="amt up">+{view["rebalance"].reinvested_krw:,} ₩</span></div>'
        "</div>"
        f'<div class="direction"><span class="ic">→</span><span><b>다음 주 방향</b> — {escape(view["direction"])}</span></div>'
        "</div>"
    )

    body = (
        _header("주간 성과 리포트", run_mode, generated_at)
        + _kpis(portfolio)
        + _sec("01", "주간 성과 지표")
        + f'<div class="weekly"><div>{grid}</div>{settle}</div>'
        + _NOTES
        + '<footer class="foot"><span>빈(Bin) · AI 자동 트레이딩 봇 · 주간 성과</span>'
        "<span>Discord · #stock-analyze</span></footer>"
    )
    return _document("빈 Bin — 주간 성과 리포트", body)
