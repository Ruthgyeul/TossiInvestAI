"""리포트 그래프 생성 단위 테스트 (docs/REPORT.md "그래프"). 실데이터 소스가 있는 7종을 검증한다."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.report.generator as generator_module
from core.config import settings


@pytest.fixture(autouse=True)
def _stub_market_news(monkeypatch: pytest.MonkeyPatch) -> None:
    """리포트 생성 시 fetch_market_news가 실제 Redis/네트워크를 건드리지 않도록 기본 stub.
    시장 뉴스 내용을 검증하는 테스트는 본문에서 다시 setattr로 덮어쓴다."""

    async def _no_news(market: str) -> list[str]:
        return []

    monkeypatch.setattr(generator_module, "fetch_market_news", _no_news)


@pytest.mark.asyncio
async def test_generate_and_publish_renders_holdings_pnl_and_volume_charts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", False)  # run_mode == "LIVE"
    monkeypatch.setattr(generator_module, "_REPORTS_DIR", tmp_path)

    async def _get_watchlist(market: str) -> list[dict]:
        return [{"symbol": "005930"}]

    async def _collect_market_snapshot(market: str, symbols: list[str]) -> dict:
        return {
            "prices": {
                "005930": {
                    "price": 75_000,
                    "volume_ratio": 2.4,
                    "news_summary": "삼성전자 3분기 실적 개선 전망",
                }
            },
            "holdings": [],
            "exchange_rate_krw_usd": 1_382.0,
        }

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "holdings": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "quantity": 2,
                    "avgPrice": 74_000.0,
                    "currentPrice": 75_000.0,
                    "pnlPct": 0.0135,
                }
            ],
            "cashBufferKrw": 75_000,
            "cumulativePnlPct": 0.02,
            "totalValueKrw": 510_000,
            "todayPnlKrw": 1_000,
        }

    async def _get_recent_live_snapshots(limit: int = 30) -> list[dict]:
        return []

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(
        generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status
    )
    monkeypatch.setattr(generator_module.db, "get_recent_live_snapshots", _get_recent_live_snapshots)
    monkeypatch.setattr(generator_module.db, "insert", _insert)

    rendered: list[str] = []

    def _fake_chart(name):
        def _render(*args, **kwargs):
            rendered.append(name)
            return Path(f"/tmp/{name}.png")
        return _render

    monkeypatch.setattr(generator_module.chart, "render_holdings_pie_chart", _fake_chart("pie"))
    monkeypatch.setattr(generator_module.chart, "render_pnl_contribution_chart", _fake_chart("pnl"))
    monkeypatch.setattr(generator_module.chart, "render_volume_histogram", _fake_chart("volume"))

    published: dict = {}

    async def _fake_publish_event(event_type: str, **kwargs):
        published["event_type"] = event_type
        published.update(kwargs)

    monkeypatch.setattr(generator_module, "publish_event", _fake_publish_event)

    await generator_module.generate_and_publish("KR", "on_demand")

    assert rendered == ["pie", "pnl", "volume"]
    assert published["payload"]["chartPaths"] == ["/tmp/pie.png", "/tmp/pnl.png", "/tmp/volume.png"]

    # HTML 문서도 함께 생성돼 htmlPath로 실려야 한다 (docs/REPORT.md "HTML 리포트 문서").
    html_path = Path(published["payload"]["htmlPath"])
    assert html_path.exists() and html_path.suffix == ".html"
    html = html_path.read_text(encoding="utf-8")
    assert "빈 <span>· Bin</span>" in html
    assert "005930" in html  # 관심 종목 표
    assert "<!doctype html>" in html


@pytest.mark.asyncio
async def test_generate_and_publish_renders_timeseries_charts_in_simulation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)  # run_mode == "SIMULATION"
    monkeypatch.setattr(generator_module, "_REPORTS_DIR", tmp_path)

    async def _get_watchlist(market: str) -> list[dict]:
        return []

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "holdings": [],
            "cashBufferKrw": 75_000,
            "cumulativePnlPct": 0.02,
            "totalValueKrw": 510_000,
            "todayPnlKrw": 1_000,
        }

    async def _get_recent_simulation_snapshots(limit: int = 30) -> list[dict]:
        return [
            {"total_value_krw": 500_000, "cash_krw": 75_000, "snapshot_at": datetime(2026, 7, 1, tzinfo=UTC)},
            {"total_value_krw": 512_000, "cash_krw": 75_000, "snapshot_at": datetime(2026, 7, 2, tzinfo=UTC)},
        ]

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(
        generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status
    )
    monkeypatch.setattr(generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots)
    monkeypatch.setattr(generator_module.db, "insert", _insert)

    rendered: list[str] = []

    def _fake_chart(name):
        def _render(*args, **kwargs):
            rendered.append(name)
            return Path(f"/tmp/{name}.png")
        return _render

    monkeypatch.setattr(generator_module.chart, "render_asset_value_chart", _fake_chart("asset_value"))
    monkeypatch.setattr(generator_module.chart, "render_portfolio_return_chart", _fake_chart("portfolio_return"))
    monkeypatch.setattr(generator_module.chart, "render_cumulative_return_chart", _fake_chart("cumulative_return"))

    async def _fake_publish_event(event_type: str, **kwargs):
        pass

    monkeypatch.setattr(generator_module, "publish_event", _fake_publish_event)

    await generator_module.generate_and_publish("KR", "on_demand")

    assert rendered == ["asset_value", "portfolio_return", "cumulative_return"]


@pytest.mark.asyncio
async def test_generate_and_publish_renders_timeseries_charts_in_live_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """live_portfolio_snapshots가 쌓이면 LIVE 모드에서도 자산 추이 차트가 생성돼야 한다
    (예전에는 SIMULATION 스냅샷만 있어 LIVE에서 항상 비어 있었다)."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", False)  # run_mode == "LIVE"
    monkeypatch.setattr(generator_module, "_REPORTS_DIR", tmp_path)

    async def _get_watchlist(market: str) -> list[dict]:
        return []

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "holdings": [],
            "cashBufferKrw": 75_000,
            "cumulativePnlPct": 0.02,
            "totalValueKrw": 610_000,
            "todayPnlKrw": 1_000,
        }

    async def _get_recent_live_snapshots(limit: int = 30) -> list[dict]:
        return [
            {"total_value_krw": 600_000, "cash_krw": 50_000, "snapshot_at": datetime(2026, 7, 1, tzinfo=UTC)},
            {"total_value_krw": 610_000, "cash_krw": 50_000, "snapshot_at": datetime(2026, 7, 2, tzinfo=UTC)},
        ]

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.db, "get_recent_live_snapshots", _get_recent_live_snapshots)
    monkeypatch.setattr(generator_module.db, "insert", _insert)

    rendered: list[str] = []

    def _fake_chart(name):
        def _render(*args, **kwargs):
            rendered.append(name)
            return Path(f"/tmp/{name}.png")
        return _render

    monkeypatch.setattr(generator_module.chart, "render_asset_value_chart", _fake_chart("asset_value"))
    monkeypatch.setattr(generator_module.chart, "render_portfolio_return_chart", _fake_chart("portfolio_return"))
    monkeypatch.setattr(generator_module.chart, "render_cumulative_return_chart", _fake_chart("cumulative_return"))

    async def _fake_publish_event(event_type: str, **kwargs):
        pass

    monkeypatch.setattr(generator_module, "publish_event", _fake_publish_event)

    await generator_module.generate_and_publish("KR", "on_demand")

    assert rendered == ["asset_value", "portfolio_return", "cumulative_return"]


@pytest.mark.asyncio
async def test_generate_and_publish_renders_index_comparison_for_all_markets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """관심 종목 일봉 종가 평균으로 만든 지수 비교 대체 차트 — market="ALL"(KR+US)일 때만 생성."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)
    monkeypatch.setattr(generator_module, "_REPORTS_DIR", tmp_path)

    async def _get_watchlist(market: str) -> list[dict]:
        return [{"symbol": "005930" if market == "KR" else "AAPL"}]

    async def _collect_market_snapshot(market: str, symbols: list[str]) -> dict:
        return {"prices": {}, "holdings": [], "exchange_rate_krw_usd": 1_382.0}

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "holdings": [],
            "cashBufferKrw": 75_000,
            "cumulativePnlPct": 0.0,
            "totalValueKrw": 500_000,
            "todayPnlKrw": 0,
        }

    async def _get_candles(symbol: str, timeframe: str) -> list[dict]:
        return [{"close": 100.0}, {"close": 110.0}]

    async def _get_recent_simulation_snapshots(limit: int = 30) -> list[dict]:
        return []

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.toss_market, "get_candles", _get_candles)
    monkeypatch.setattr(
        generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots
    )
    monkeypatch.setattr(generator_module.db, "insert", _insert)

    rendered: list[tuple] = []

    def _fake_index_chart(kospi, nasdaq):
        rendered.append((kospi, nasdaq))
        return Path("/tmp/index_comparison.png")

    monkeypatch.setattr(generator_module.chart, "render_index_comparison_chart", _fake_index_chart)

    async def _fake_publish_event(event_type: str, **kwargs):
        pass

    monkeypatch.setattr(generator_module, "publish_event", _fake_publish_event)

    await generator_module.generate_and_publish("ALL", "on_demand")

    assert rendered == [([100.0, 110.0], [100.0, 110.0])]


@pytest.mark.asyncio
async def test_market_composite_series_averages_equal_weighted_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_watchlist(market: str) -> list[dict]:
        return [{"symbol": "005930"}, {"symbol": "000660"}]

    async def _get_candles(symbol: str, timeframe: str) -> list[dict]:
        return {"005930": [{"close": 100.0}, {"close": 200.0}], "000660": [{"close": 50.0}, {"close": 100.0}]}[symbol]

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module.toss_market, "get_candles", _get_candles)

    series = await generator_module._market_composite_series("KR")

    assert series == [75.0, 150.0]


@pytest.mark.asyncio
async def test_market_composite_series_none_when_watchlist_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_watchlist(market: str) -> list[dict]:
        return []

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)

    assert await generator_module._market_composite_series("KR") is None


@pytest.mark.asyncio
async def test_generate_report_shows_fear_greed_and_popular_from_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """예전에는 "데이터 소스 미연동" 고정 텍스트였다 — collector가 채운 대체 지표를
    실제로 리포트에 반영해야 한다."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)

    async def _get_watchlist(market: str) -> list[dict]:
        return [{"symbol": "005930"}]

    async def _collect_market_snapshot(market: str, symbols: list[str]) -> dict:
        return {
            "prices": {"005930": {"price": 75_000}},
            "holdings": [],
            "exchange_rate_krw_usd": 1_382.0,
            "toss_popular_top10": ["005930", "000660"],
            "fear_greed_index": 62,
        }

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {"holdings": [], "cashBufferKrw": 75_000, "cumulativePnlPct": 0.0, "totalValueKrw": 500_000, "todayPnlKrw": 0}

    async def _market_news(market: str) -> list[str]:
        return ["한국은행 기준금리 동결", "코스피 외국인 순매수"]

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module, "fetch_market_news", _market_news)

    content = await generator_module.generate_report("KR", "on_demand")

    assert "62 / 100" in content
    assert "005930, 000660" in content
    # 시장 경제 뉴스 섹션에 헤드라인이 실려야 한다.
    assert "### 시장 경제 뉴스" in content
    assert "한국은행 기준금리 동결" in content


@pytest.mark.asyncio
async def test_generate_weekly_report_includes_performance_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/REPORT.md "주간 성과 리포트" 필수 지표(승률·평균 수익률·최대 손익·MDD·샤프·
    수익 팩터·평균 보유 기간·다음 주 전략 방향)가 실데이터로 채워져야 한다 (예전에는
    총자산·누적수익률·자금 정산 3줄뿐이었다)."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)  # run_mode == "SIMULATION"

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "totalValueKrw": 512_000,
            "cumulativePnlPct": 0.024,
            "cumulativePnlKrw": 12_000,
            "cashBufferKrw": 76_800,
            "todayPnlKrw": 0,
            "holdings": [],
        }

    from core.fund.manager import RebalanceResult

    async def _weekly_rebalance(mode):  # noqa: ANN001
        return RebalanceResult(api_cost_covered_krw=4_200, reinvested_krw=32_000, buffer_added_krw=8_000)

    async def _get_operating_funds_krw(mode):  # noqa: ANN001
        return 435_200.0

    now = datetime.now(UTC)
    all_trades = [
        {
            "symbol": "005930",
            "action": "BUY",
            "quantity": 2,
            "fill_price": 74_800,
            "pnl_krw": None,
            "created_at": now - timedelta(days=2),
        },
        {
            "symbol": "005930",
            "action": "SELL",
            "quantity": 2,
            "fill_price": 76_200,
            "pnl_krw": 2_572,
            "created_at": now - timedelta(days=1),
        },
        {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 1,
            "fill_price": 210.0,
            "pnl_krw": None,
            "created_at": now - timedelta(days=3),
        },
        {
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 1,
            "fill_price": 205.0,
            "pnl_krw": -500,
            "created_at": now - timedelta(days=1),
        },
    ]

    async def _get_all_trades(mode):  # noqa: ANN001
        return all_trades

    async def _get_recent_simulation_snapshots(limit: int = 30) -> list[dict]:
        return [
            {"total_value_krw": 500_000, "cash_krw": 75_000, "snapshot_at": now - timedelta(days=6)},
            {"total_value_krw": 512_000, "cash_krw": 75_000, "snapshot_at": now - timedelta(days=1)},
        ]

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.fund_manager, "weekly_rebalance", _weekly_rebalance)
    monkeypatch.setattr(generator_module.fund_manager, "get_operating_funds_krw", _get_operating_funds_krw)
    monkeypatch.setattr(generator_module.db, "get_all_trades", _get_all_trades)
    monkeypatch.setattr(
        generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots
    )
    monkeypatch.setattr(generator_module.db, "insert", _insert)

    content = await generator_module.generate_weekly_report()

    assert "총 거래 횟수    4회 (매수 2 / 매도 2)" in content
    assert "승률            50.0%" in content
    assert "최대 단일 손실" in content
    assert "최대 단일 수익" in content
    assert "MDD" in content
    assert "샤프 지수" in content
    assert "수익 팩터" in content
    assert "평균 보유 기간" in content
    assert "운용 자금         435,200 KRW" in content
    assert "Claude API 비용   -4,200 KRW" in content
    assert "순수익 재투자     +32,000 KRW" in content
    assert "다음 주 전략 방향" in content


@pytest.mark.asyncio
async def test_generate_weekly_report_flags_no_sells_for_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이번 주 매도 체결이 없으면 승률 등 계산이 불가능하므로 관망 문구를 반환해야 한다."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "totalValueKrw": 500_000,
            "cumulativePnlPct": 0.0,
            "cumulativePnlKrw": 0,
            "cashBufferKrw": 75_000,
            "todayPnlKrw": 0,
            "holdings": [],
        }

    from core.fund.manager import RebalanceResult

    async def _weekly_rebalance(mode):  # noqa: ANN001
        return RebalanceResult(api_cost_covered_krw=0, reinvested_krw=0, buffer_added_krw=0)

    async def _get_operating_funds_krw(mode):  # noqa: ANN001
        return 425_000.0

    async def _get_all_trades(mode):  # noqa: ANN001
        return []

    async def _get_recent_simulation_snapshots(limit: int = 30) -> list[dict]:
        return []

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.fund_manager, "weekly_rebalance", _weekly_rebalance)
    monkeypatch.setattr(generator_module.fund_manager, "get_operating_funds_krw", _get_operating_funds_krw)
    monkeypatch.setattr(generator_module.db, "get_all_trades", _get_all_trades)
    monkeypatch.setattr(
        generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots
    )
    monkeypatch.setattr(generator_module.db, "insert", _insert)

    content = await generator_module.generate_weekly_report()

    assert "이번 주 체결된 매도가 없어" in content


@pytest.mark.asyncio
async def test_generate_report_includes_holdings_news(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """보유 종목 분석에 스냅샷의 종목별 뉴스 요약이 붙고, '뉴스 없음' 폴백은 제외돼야 한다."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)

    async def _get_watchlist(market: str) -> list[dict]:
        return [{"symbol": "005930"}, {"symbol": "000660"}]

    async def _collect_market_snapshot(market: str, symbols: list[str]) -> dict:
        return {
            "prices": {
                "005930": {"price": 78_400, "news_summary": "반도체 업황 개선 기대"},
                "000660": {"price": 213_000, "news_summary": "뉴스 없음"},
            },
            "holdings": [],
            "exchange_rate_krw_usd": 1_384.0,
            "toss_popular_top10": [],
            "fear_greed_index": 50,
        }

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "holdings": [
                {"symbol": "005930", "market": "KR", "quantity": 1, "avgPrice": 74_000.0,
                 "currentPrice": 78_400.0, "pnlPct": 0.0595},
                {"symbol": "000660", "market": "KR", "quantity": 1, "avgPrice": 195_000.0,
                 "currentPrice": 213_000.0, "pnlPct": 0.0923},
            ],
            "cashBufferKrw": 75_000, "cumulativePnlPct": 0.0, "totalValueKrw": 500_000, "todayPnlKrw": 0,
        }

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)

    content = await generator_module.generate_report("KR", "on_demand")

    assert "📰 반도체 업황 개선 기대" in content  # 뉴스 있는 종목
    assert "📰 뉴스 없음" not in content  # 종목 뉴스 폴백 요약은 노출하지 않는다


@pytest.mark.asyncio
async def test_generate_weekly_and_publish_writes_html_and_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """주간 리포트도 HTML 문서를 저장하고 report_ready payload에 htmlPath를 실어야 한다."""
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", True)
    monkeypatch.setattr(generator_module, "_REPORTS_DIR", tmp_path)

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "totalValueKrw": 512_000, "cumulativePnlPct": 0.024, "cumulativePnlKrw": 12_000,
            "cashBufferKrw": 76_800, "todayPnlKrw": 0, "holdings": [],
        }

    from core.fund.manager import RebalanceResult

    async def _weekly_rebalance(mode):  # noqa: ANN001
        return RebalanceResult(api_cost_covered_krw=4_200, reinvested_krw=32_000, buffer_added_krw=8_000)

    async def _get_operating_funds_krw(mode):  # noqa: ANN001
        return 435_200.0

    async def _get_all_trades(mode):  # noqa: ANN001
        return []

    async def _get_recent_simulation_snapshots(limit: int = 30) -> list[dict]:
        return []

    async def _insert(table: str, values: dict) -> dict:
        return values

    published: dict = {}

    async def _publish_event(event_type: str, **kwargs):
        published["event_type"] = event_type
        published.update(kwargs)

    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.fund_manager, "weekly_rebalance", _weekly_rebalance)
    monkeypatch.setattr(generator_module.fund_manager, "get_operating_funds_krw", _get_operating_funds_krw)
    monkeypatch.setattr(generator_module.db, "get_all_trades", _get_all_trades)
    monkeypatch.setattr(
        generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots
    )
    monkeypatch.setattr(generator_module.db, "insert", _insert)
    monkeypatch.setattr(generator_module, "publish_event", _publish_event)

    await generator_module.generate_weekly_and_publish()

    assert published["event_type"] == "report_ready"
    assert published["payload"]["reportType"] == "weekly"
    html_path = Path(published["payload"]["htmlPath"])
    assert html_path.exists() and html_path.suffix == ".html"
    html = html_path.read_text(encoding="utf-8")
    assert "주간 성과 지표" in html
    assert "다음 주 방향" in html
