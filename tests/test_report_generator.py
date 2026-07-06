"""리포트 그래프 생성 단위 테스트 (docs/REPORT.md "그래프"). 실데이터 소스가 있는 6종만 검증한다."""

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

    monkeypatch.setattr(generator_module, "get_watchlist", _get_watchlist)
    monkeypatch.setattr(generator_module, "collect_market_snapshot", _collect_market_snapshot)
    monkeypatch.setattr(
        generator_module.fund_manager, "get_portfolio_status", _get_portfolio_status
    )

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
