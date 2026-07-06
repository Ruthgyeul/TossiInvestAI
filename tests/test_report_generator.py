"""리포트 그래프 생성 단위 테스트 (docs/REPORT.md "그래프"). 실데이터 소스가 있는 7종을 검증한다."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

import core.report.generator as generator_module
from core.config import settings


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
            "prices": {"005930": {"price": 75_000, "volume_ratio": 2.4}},
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

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(
        generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status
    )
    monkeypatch.setattr(generator_module.db, "get_recent_live_snapshots", _get_recent_live_snapshots)

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
            {"total_value_krw": 500_000, "cash_krw": 75_000, "snapshot_at": datetime(2026, 7, 1, tzinfo=timezone.utc)},
            {"total_value_krw": 512_000, "cash_krw": 75_000, "snapshot_at": datetime(2026, 7, 2, tzinfo=timezone.utc)},
        ]

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(
        generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status
    )
    monkeypatch.setattr(generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots)

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
            {"total_value_krw": 600_000, "cash_krw": 50_000, "snapshot_at": datetime(2026, 7, 1, tzinfo=timezone.utc)},
            {"total_value_krw": 610_000, "cash_krw": 50_000, "snapshot_at": datetime(2026, 7, 2, tzinfo=timezone.utc)},
        ]

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.db, "get_recent_live_snapshots", _get_recent_live_snapshots)

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

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(generator_module.toss_market, "get_candles", _get_candles)
    monkeypatch.setattr(
        generator_module.db, "get_recent_simulation_snapshots", _get_recent_simulation_snapshots
    )

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

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status)

    content = await generator_module.generate_report("KR", "on_demand")

    assert "62 / 100" in content
    assert "005930, 000660" in content
