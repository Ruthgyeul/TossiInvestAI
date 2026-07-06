"""matplotlib 그래프 생성. `logs/reports/charts/`에 저장한다 (docs/REPORT.md).

생성 실패 시 텍스트 리포트만 발송하고 #stock-error에 경고 Embed를 전송한다.
"""

from pathlib import Path

CHARTS_DIR = Path("logs/reports/charts")


def render_portfolio_return_chart(dates: list[str], returns: list[float]) -> Path:
    """포트폴리오 누적 수익률 라인차트."""
    raise NotImplementedError


def render_asset_value_chart(dates: list[str], values: list[float]) -> Path:
    """총 자산 KRW 추이."""
    raise NotImplementedError


def render_index_comparison_chart(kospi: list[float], nasdaq: list[float]) -> Path:
    """KOSPI·NASDAQ 정규화 비교."""
    raise NotImplementedError


def render_holdings_pie_chart(holdings: dict[str, float]) -> Path:
    """보유 종목 비중 파이차트."""
    raise NotImplementedError


def render_sector_distribution_chart(sectors: dict[str, float]) -> Path:
    """업종 분포 바차트."""
    raise NotImplementedError


def render_volume_histogram(symbols: dict[str, float]) -> Path:
    """관심 종목 거래량 변화 히스토그램."""
    raise NotImplementedError


def render_pnl_contribution_chart(pnl_by_symbol: dict[str, float]) -> Path:
    """종목별 손익 기여 바차트."""
    raise NotImplementedError


def render_cumulative_return_chart(dates: list[str], cumulative_returns: list[float]) -> Path:
    """시드 대비 누적 수익률 라인차트."""
    raise NotImplementedError
