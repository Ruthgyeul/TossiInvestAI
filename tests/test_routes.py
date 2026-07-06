"""내부 API 핸들러 단위 테스트 — `/status`·`/fund`·`/health` (docs/CODING_RULES.md Phase 4 검증 대상).

DB·토스 API·FundManager 등 실제 협력 객체는 monkeypatch로 격리하고 aiohttp 핸들러 함수를
`make_mocked_request`로 직접 호출해 응답 바디만 검증한다.
"""

import json as json_lib

import pytest
from aiohttp.test_utils import make_mocked_request

from core.api import routes
from core.config import settings
from core.fund.manager import fund_manager
from core.monitoring.health import HEALTH_REDIS_KEY


@pytest.mark.asyncio
async def test_get_health_returns_defaults_when_no_snapshot_cached(
    fake_redis,  # noqa: ANN001 — tests/conftest.py fixture
) -> None:
    request = make_mocked_request("GET", "/api/v1/health")

    response = await routes.get_health(request)
    body = json_lib.loads(response.body)

    assert body["mode"] == settings.run_mode
    assert body["cpuPct"] == 0.0
    assert body["tossApiReachable"] is False


@pytest.mark.asyncio
async def test_get_health_returns_cached_snapshot(fake_redis) -> None:  # noqa: ANN001
    await fake_redis.set(
        HEALTH_REDIS_KEY,
        json_lib.dumps(
            {
                "cpu_pct": 42.5,
                "memory_pct": 55.0,
                "disk_pct": 60.0,
                "temp_c": 65.0,
                "toss_api_reachable": True,
            }
        ),
    )

    request = make_mocked_request("GET", "/api/v1/health")
    response = await routes.get_health(request)
    body = json_lib.loads(response.body)

    assert body["cpuPct"] == 42.5
    assert body["tossApiReachable"] is True


@pytest.mark.asyncio
async def test_get_status_returns_live_null_in_simulation_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SIMULATION", True)
    monkeypatch.setattr(settings, "DRY_RUN", False)

    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        assert mode == "SIMULATION"
        return {"totalValueKrw": 512_000, "holdings": []}

    monkeypatch.setattr(fund_manager, "get_portfolio_status", _get_portfolio_status)

    request = make_mocked_request("GET", "/api/v1/status")
    response = await routes.get_status(request)
    body = json_lib.loads(response.body)

    assert body["live"] is None
    assert body["simulation"]["totalValueKrw"] == 512_000


@pytest.mark.asyncio
async def test_get_fund_computes_position_ratios(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_portfolio_status(mode, market=None):  # noqa: ANN001
        return {
            "holdings": [{"symbol": "005930", "quantity": 2, "currentPrice": 75_000}],
            "cashBufferKrw": 75_000,
            "cumulativePnlPct": 0.05,
        }

    async def _get_operating_funds_krw():
        return 425_000.0

    monkeypatch.setattr(fund_manager, "get_portfolio_status", _get_portfolio_status)
    monkeypatch.setattr(fund_manager, "get_operating_funds_krw", _get_operating_funds_krw)

    request = make_mocked_request("GET", "/api/v1/fund")
    response = await routes.get_fund(request)
    body = json_lib.loads(response.body)

    assert body["operatingFundsKrw"] == 425_000
    assert body["cashBufferKrw"] == 75_000
    assert body["positionRatios"] == [
        {"symbol": "005930", "ratio": pytest.approx(150_000 / 425_000)}
    ]
