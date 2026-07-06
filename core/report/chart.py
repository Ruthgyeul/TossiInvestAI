"""matplotlib 그래프 생성. `logs/reports/charts/`에 저장한다 (docs/REPORT.md).

생성 실패 시 텍스트 리포트만 발송하고 #stock-error에 경고 Embed를 전송한다.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # 헤드리스 라즈베리파이 — GUI 백엔드 불필요
import matplotlib.pyplot as plt

CHARTS_DIR = Path("logs/reports/charts")
_KST = ZoneInfo("Asia/Seoul")


def _save(fig: "plt.Figure", name: str) -> Path:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{datetime.now(_KST):%Y-%m-%d_%H%M%S}_{name}.png"
    fig.savefig(path, bbox_inches="tight", dpi=120)
    plt.close(fig)
    return path


def render_portfolio_return_chart(dates: list[str], returns: list[float]) -> Path:
    """포트폴리오 누적 수익률 라인차트."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(dates, returns, marker="o", color="#0984e3")
    ax.set_title("포트폴리오 수익률")
    ax.set_ylabel("수익률 (%)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, "portfolio_return")


def render_asset_value_chart(dates: list[str], values: list[float]) -> Path:
    """총 자산 KRW 추이."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(dates, values, marker="o", color="#00b894")
    ax.set_title("총 자산 추이 (KRW)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, "asset_value")


def render_index_comparison_chart(kospi: list[float], nasdaq: list[float]) -> Path:
    """KOSPI·NASDAQ 정규화 비교."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot([v / kospi[0] * 100 for v in kospi], label="KOSPI", color="#e17055")
    ax.plot([v / nasdaq[0] * 100 for v in nasdaq], label="NASDAQ", color="#0984e3")
    ax.set_title("시장 지수 비교 (시작=100)")
    ax.legend()
    fig.tight_layout()
    return _save(fig, "index_comparison")


def render_holdings_pie_chart(holdings: dict[str, float]) -> Path:
    """보유 종목 비중 파이차트."""
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(list(holdings.values()), labels=list(holdings.keys()), autopct="%1.1f%%")
    ax.set_title("보유 종목 비중")
    fig.tight_layout()
    return _save(fig, "holdings_pie")


def render_sector_distribution_chart(sectors: dict[str, float]) -> Path:
    """업종 분포 바차트."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(list(sectors.keys()), list(sectors.values()), color="#6c5ce7")
    ax.set_title("업종 분포")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, "sector_distribution")


def render_volume_histogram(symbols: dict[str, float]) -> Path:
    """관심 종목 거래량 변화 히스토그램."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(list(symbols.keys()), list(symbols.values()), color="#fdcb6e")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=1)
    ax.set_title("거래량 변화율 (전일 대비)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, "volume_histogram")


def render_pnl_contribution_chart(pnl_by_symbol: dict[str, float]) -> Path:
    """종목별 손익 기여 바차트."""
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#00b894" if v >= 0 else "#d63031" for v in pnl_by_symbol.values()]
    ax.bar(list(pnl_by_symbol.keys()), list(pnl_by_symbol.values()), color=colors)
    ax.set_title("종목별 손익 기여 (KRW)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, "pnl_contribution")


def render_cumulative_return_chart(dates: list[str], cumulative_returns: list[float]) -> Path:
    """시드 대비 누적 수익률 라인차트."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(dates, cumulative_returns, marker="o", color="#00b894")
    ax.axhline(0, color="gray", linestyle="--", linewidth=1)
    ax.set_title("누적 수익률 (시드 대비, %)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, "cumulative_return")
