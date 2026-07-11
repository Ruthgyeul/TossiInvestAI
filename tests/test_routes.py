"""내부 API 핸들러 단위 테스트 — `/status`·`/fund`·`/health` (docs/CODING_RULES.md Phase 4 검증 대상).

DB·토스 API·FundManager 등 실제 협력 객체는 monkeypatch로 격리하고 aiohttp 핸들러 함수를
`make_mocked_request`로 직접 호출해 응답 바디만 검증한다.
"""

import asyncio
import json as json_lib
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from aiohttp import streams
from aiohttp.test_utils import make_mocked_request

from core.api import routes
from core.config import settings
from core.fund.manager import fund_manager
from core.monitoring.health import HEALTH_REDIS_KEY


def _mocked_post_request(path: str, body: dict, match_info: dict | None = None) -> object:
    """JSON 바디를 읽을 수 있는 POST 목 요청 — make_mocked_request의 payload는
    StreamReader 프로토콜(`at_eof`/`read`)을 요구해 bytes를 직접 넘길 수 없다."""
    protocol = mock.Mock()
    protocol._reading_paused = False
    reader = streams.StreamReader(protocol, 2**16, loop=asyncio.get_event_loop())
    reader.feed_data(json_lib.dumps(body).encode())
    reader.feed_eof()
    kwargs = {"match_info": match_info} if match_info is not None else {}
    return make_mocked_request("POST", path, payload=reader, **kwargs)


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

    async def _get_operating_funds_krw(mode=None):  # noqa: ANN001
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


@pytest.mark.asyncio
async def test_post_stop_persists_flags_to_db_and_redis(
    fake_redis,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    monkeypatch.setattr(settings, "KR_STOP", False)
    monkeypatch.setattr(settings, "US_STOP", False)

    persisted: dict = {}

    async def _set_control_flags(*, emergency_stop: bool, kr_stop: bool, us_stop: bool) -> None:
        persisted.update(
            emergency_stop=emergency_stop, kr_stop=kr_stop, us_stop=us_stop
        )

    monkeypatch.setattr(routes.db, "set_control_flags", _set_control_flags)

    request = _mocked_post_request("/api/v1/control/stop", {})
    response = await routes.post_stop(request)
    body = json_lib.loads(response.body)

    assert body["emergencyStop"] is True
    assert settings.EMERGENCY_STOP is True
    assert persisted == {"emergency_stop": True, "kr_stop": False, "us_stop": False}

    cached = json_lib.loads(await fake_redis.get(routes._CONTROL_FLAGS_REDIS_KEY))
    assert cached["emergencyStop"] is True


@pytest.mark.asyncio
async def test_post_stop_cancels_open_orders_in_live_mode(
    fake_redis,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SIMULATION", False)  # run_mode == "LIVE"

    async def _set_control_flags(**_: object) -> None:
        return None

    monkeypatch.setattr(routes.db, "set_control_flags", _set_control_flags)

    async def _get_orders(status: str | None = None) -> list[dict]:
        return [
            {"orderId": "o-1", "symbol": "005930", "market": "KR"},
            {"orderId": "o-2", "symbol": "AAPL", "market": "US"},
        ]

    cancelled_ids: list[str] = []

    async def _cancel(order_id: str) -> dict:
        cancelled_ids.append(order_id)
        return {"orderId": order_id}

    monkeypatch.setattr(routes.toss_order, "get_orders", _get_orders)
    monkeypatch.setattr(routes.toss_order, "cancel", _cancel)

    request = _mocked_post_request("/api/v1/control/stop", {"market": "KR"})
    response = await routes.post_stop(request)
    body = json_lib.loads(response.body)

    assert cancelled_ids == ["o-1"]
    assert body["cancelledOrders"] == [{"orderId": "o-1", "symbol": "005930"}]


@pytest.mark.asyncio
async def test_post_resume_clears_and_persists_flags(
    fake_redis,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMERGENCY_STOP", True)
    monkeypatch.setattr(settings, "KR_STOP", True)
    monkeypatch.setattr(settings, "US_STOP", True)

    persisted: dict = {}

    async def _set_control_flags(*, emergency_stop: bool, kr_stop: bool, us_stop: bool) -> None:
        persisted.update(
            emergency_stop=emergency_stop, kr_stop=kr_stop, us_stop=us_stop
        )

    monkeypatch.setattr(routes.db, "set_control_flags", _set_control_flags)

    request = make_mocked_request("POST", "/api/v1/control/resume")
    response = await routes.post_resume(request)
    body = json_lib.loads(response.body)

    assert body["success"] is True
    assert settings.EMERGENCY_STOP is False
    assert persisted == {"emergency_stop": False, "kr_stop": False, "us_stop": False}


def test_average_holding_days_matches_fifo_buy_sell_pairs() -> None:
    trades = [
        {
            "symbol": "005930",
            "action": "BUY",
            "quantity": 10,
            "created_at": datetime(2026, 7, 1, tzinfo=UTC),
        },
        {
            "symbol": "005930",
            "action": "SELL",
            "quantity": 10,
            "created_at": datetime(2026, 7, 3, tzinfo=UTC),
        },
        {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 5,
            "created_at": datetime(2026, 7, 1, tzinfo=UTC),
        },
        {
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 5,
            "created_at": datetime(2026, 7, 2, tzinfo=UTC),
        },
    ]

    # 005930: 10주 2일 보유, AAPL: 5주 1일 보유 → 가중평균 (10*2 + 5*1) / 15 = 25/15
    assert routes._average_holding_days(trades) == pytest.approx(25 / 15)


def test_average_holding_days_zero_when_no_completed_round_trip() -> None:
    trades = [
        {
            "symbol": "005930",
            "action": "BUY",
            "quantity": 10,
            "created_at": datetime(2026, 7, 1, tzinfo=UTC),
        }
    ]

    assert routes._average_holding_days(trades) == 0.0


@pytest.mark.asyncio
async def test_get_orders_returns_action_quantity_price(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fetch_all(table, filters=None, *, order_by=None, descending=False, limit=None):  # noqa: ANN001
        assert table == "orders"
        return [
            {
                "client_order_id": "BIN-KR-ABC123",
                "symbol": "005930",
                "market": "KR",
                "action": "BUY",
                "quantity": 2,
                "price": 74_800.0,
                "status": "FILLED",
                "created_at": datetime(2026, 7, 6, tzinfo=UTC),
            }
        ]

    monkeypatch.setattr(routes.db, "fetch_all", _fetch_all)

    request = make_mocked_request("GET", "/api/v1/orders")
    response = await routes.get_orders(request)
    body = json_lib.loads(response.body)

    assert body["orders"] == [
        {
            "orderId": "BIN-KR-ABC123",
            "symbol": "005930",
            "market": "KR",
            "action": "BUY",
            "quantity": 2,
            "price": 74_800.0,
            "status": "FILLED",
            "createdAt": "2026-07-06T00:00:00+00:00",
        }
    ]


@pytest.mark.asyncio
async def test_get_simstatus_includes_avg_holding_days(monkeypatch: pytest.MonkeyPatch) -> None:
    trades = [
        {
            "symbol": "005930",
            "market": "KR",
            "action": "BUY",
            "quantity": 10,
            "fill_price": 74_000.0,
            "commission_krw": 100,
            "pnl_krw": None,
            "created_at": datetime(2026, 7, 1, tzinfo=UTC),
        },
        {
            "symbol": "005930",
            "market": "KR",
            "action": "SELL",
            "quantity": 10,
            "fill_price": 75_000.0,
            "commission_krw": 100,
            "pnl_krw": 9_800,
            "created_at": datetime(2026, 7, 3, tzinfo=UTC),
        },
    ]

    async def _fetch_all(table, filters=None, *, order_by=None, descending=False, limit=None):  # noqa: ANN001
        if table == "simulation_trades":
            return trades
        if table == "simulation_portfolio_snapshots":
            return []
        if table == "safety_rejections":
            return []
        if table == "simulation_positions":
            return []
        raise AssertionError(f"예상치 못한 테이블 조회: {table}")

    async def _get_api_usage_month_summary() -> dict:
        return {"cost_krw": 1_000, "call_count": 5}

    monkeypatch.setattr(routes.db, "fetch_all", _fetch_all)
    monkeypatch.setattr(routes.db, "get_api_usage_month_summary", _get_api_usage_month_summary)

    request = make_mocked_request("GET", "/api/v1/simstatus")
    response = await routes.get_simstatus(request)
    body = json_lib.loads(response.body)

    assert body["avgHoldingDays"] == pytest.approx(2.0)
    assert body["tradeCount"] == 2
    assert body["winRate"] == 1.0


@pytest.mark.asyncio
async def test_post_simulate_off_rejected_before_two_weeks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/SAFETY.md·CLAUDE.md 규칙 11 — SIMULATION 2주 미만이면 LIVE 전환을 거부한다."""
    monkeypatch.setattr(settings, "SIMULATION", True)

    async def _get_simulation_started_at() -> datetime:
        return datetime.now(UTC) - timedelta(days=5)

    monkeypatch.setattr(routes.db, "get_simulation_started_at", _get_simulation_started_at)

    request = _mocked_post_request("/api/v1/control/simulate", {"state": "off"})
    response = await routes.post_simulate(request)
    body = json_lib.loads(response.body)

    assert body["success"] is False
    assert body["simulation"] is True
    assert "14" in body["reason"]
    assert settings.SIMULATION is True


@pytest.mark.asyncio
async def test_post_simulate_off_allowed_after_two_weeks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SIMULATION", True)

    async def _get_simulation_started_at() -> datetime:
        return datetime.now(UTC) - timedelta(days=15)

    monkeypatch.setattr(routes.db, "get_simulation_started_at", _get_simulation_started_at)

    request = _mocked_post_request("/api/v1/control/simulate", {"state": "off"})
    response = await routes.post_simulate(request)
    body = json_lib.loads(response.body)

    assert body["success"] is True
    assert body["simulation"] is False
    assert settings.SIMULATION is False


@pytest.mark.asyncio
async def test_post_simulate_on_records_start_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SIMULATION", False)
    recorded: list[datetime] = []

    async def _set_simulation_started_at(started_at: datetime) -> None:
        recorded.append(started_at)

    monkeypatch.setattr(routes.db, "set_simulation_started_at", _set_simulation_started_at)

    request = _mocked_post_request("/api/v1/control/simulate", {"state": "on"})
    response = await routes.post_simulate(request)
    body = json_lib.loads(response.body)

    assert body["success"] is True
    assert body["simulation"] is True
    assert settings.SIMULATION is True
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_get_version_returns_default_when_no_deployed_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_latest_deployed(market=None):  # noqa: ANN001
        return None

    monkeypatch.setattr(routes.db, "get_latest_deployed_strategy_version", _get_latest_deployed)

    request = make_mocked_request("GET", "/api/v1/version")
    response = await routes.get_version(request)
    body = json_lib.loads(response.body)

    assert body["strategyVersion"] == "v1.0.0"
    assert body["deployedAt"] is None


@pytest.mark.asyncio
async def test_get_version_candidates_lists_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_pending(market=None):  # noqa: ANN001
        return [
            {
                "id": 1,
                "market": "KR",
                "strategy_version": "v1.1.0",
                "prompt_version": "system_kr_v1",
                "based_on": "v1.0.0",
                "change_summary": "RSI 임계값 조정",
                "backtest_result": {"win_rate": 0.6},
                "proposed_at": datetime(2026, 7, 6, tzinfo=UTC),
            }
        ]

    monkeypatch.setattr(routes.db, "get_pending_strategy_candidates", _get_pending)

    request = make_mocked_request("GET", "/api/v1/version/candidates")
    response = await routes.get_version_candidates(request)
    body = json_lib.loads(response.body)

    assert body["candidates"][0]["id"] == 1
    assert body["candidates"][0]["changeSummary"] == "RSI 임계값 조정"
    assert body["candidates"][0]["backtestResult"] == {"win_rate": 0.6}


@pytest.mark.asyncio
async def test_post_version_approve_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _approve(version_id, approved_by):  # noqa: ANN001
        assert version_id == 1
        assert approved_by == "discord:Ruthgyeul"
        return {"id": 1, "approved_by": approved_by}

    monkeypatch.setattr(routes.db, "approve_strategy_version", _approve)

    request = _mocked_post_request(
        "/api/v1/version/1/approve", {"approvedBy": "discord:Ruthgyeul"}, match_info={"id": "1"}
    )
    response = await routes.post_version_approve(request)
    body = json_lib.loads(response.body)

    assert body["success"] is True


@pytest.mark.asyncio
async def test_post_version_approve_missing_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _approve(version_id, approved_by):  # noqa: ANN001
        return None

    monkeypatch.setattr(routes.db, "approve_strategy_version", _approve)

    request = _mocked_post_request(
        "/api/v1/version/999/approve", {"approvedBy": "discord:Ruthgyeul"}, match_info={"id": "999"}
    )
    response = await routes.post_version_approve(request)
    body = json_lib.loads(response.body)

    assert body["success"] is False


@pytest.mark.asyncio
async def test_post_version_reject_deletes_pending_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fetch_one(table, filters):  # noqa: ANN001
        assert table == "strategy_versions"
        assert filters == {"id": 1}
        return {"id": 1, "approved_by": None}

    deleted: list[dict] = []

    async def _delete(table, filters):  # noqa: ANN001
        deleted.append(filters)

    monkeypatch.setattr(routes.db, "fetch_one", _fetch_one)
    monkeypatch.setattr(routes.db, "delete", _delete)

    request = _mocked_post_request("/api/v1/version/1/reject", {}, match_info={"id": "1"})
    response = await routes.post_version_reject(request)
    body = json_lib.loads(response.body)

    assert body["success"] is True
    assert deleted == [{"id": 1}]


@pytest.mark.asyncio
async def test_post_version_reject_refuses_already_deployed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fetch_one(table, filters):  # noqa: ANN001
        return {"id": 1, "approved_by": "discord:Ruthgyeul"}

    async def _delete_should_not_be_called(table, filters):  # noqa: ANN001
        raise AssertionError("이미 배포된 버전은 삭제하면 안 된다")

    monkeypatch.setattr(routes.db, "fetch_one", _fetch_one)
    monkeypatch.setattr(routes.db, "delete", _delete_should_not_be_called)

    request = _mocked_post_request("/api/v1/version/1/reject", {}, match_info={"id": "1"})
    response = await routes.post_version_reject(request)
    body = json_lib.loads(response.body)

    assert body["success"] is False


@pytest.mark.asyncio
async def test_post_version_rollback_reinserts_target_as_new_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_deployed_by_name(strategy_version):  # noqa: ANN001
        assert strategy_version == "v1.0.0"
        return {
            "market": "KR",
            "strategy_version": "v1.0.0",
            "prompt_version": "system_kr_v1",
            "backtest_result": {"win_rate": 0.65},
        }

    async def _get_latest_deployed(market):  # noqa: ANN001
        return {"strategy_version": "v1.1.0"}

    inserted: list[dict] = []

    async def _insert(table, values):  # noqa: ANN001
        inserted.append(values)
        return values

    monkeypatch.setattr(routes.db, "get_deployed_strategy_version_by_name", _get_deployed_by_name)
    monkeypatch.setattr(routes.db, "get_latest_deployed_strategy_version", _get_latest_deployed)
    monkeypatch.setattr(routes.db, "insert", _insert)

    request = _mocked_post_request(
        "/api/v1/version/rollback",
        {"strategyVersion": "v1.0.0", "approvedBy": "discord:Ruthgyeul"},
    )
    response = await routes.post_version_rollback(request)
    body = json_lib.loads(response.body)

    assert body["success"] is True
    assert inserted[0]["strategy_version"] == "v1.0.0"
    assert inserted[0]["based_on"] == "v1.1.0"
    assert inserted[0]["approved_by"] == "discord:Ruthgyeul"
    assert inserted[0]["deployed_at"] is not None


@pytest.mark.asyncio
async def test_post_buy_order_rejects_non_positive_quantity(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _execute_should_not_be_called(decision, mode, **kwargs):  # noqa: ANN001
        raise AssertionError("수량 검증에 실패하면 execute()를 호출하면 안 된다")

    monkeypatch.setattr(routes, "execute", _execute_should_not_be_called)

    request = _mocked_post_request("/api/v1/orders/buy", {"symbol": "005930", "quantity": 0})
    response = await routes.post_buy_order(request)
    body = json_lib.loads(response.body)

    assert response.status == 400
    assert body["approved"] is False


@pytest.mark.asyncio
async def test_post_sell_order_rejects_negative_price(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _execute_should_not_be_called(decision, mode, **kwargs):  # noqa: ANN001
        raise AssertionError("가격 검증에 실패하면 execute()를 호출하면 안 된다")

    monkeypatch.setattr(routes, "execute", _execute_should_not_be_called)

    request = _mocked_post_request(
        "/api/v1/orders/sell", {"symbol": "005930", "quantity": 1, "price": -100}
    )
    response = await routes.post_sell_order(request)
    body = json_lib.loads(response.body)

    assert response.status == 400
    assert body["approved"] is False


@pytest.mark.asyncio
async def test_post_buy_order_rejects_malformed_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _execute_should_not_be_called(decision, mode, **kwargs):  # noqa: ANN001
        raise AssertionError("종목 코드 검증에 실패하면 execute()를 호출하면 안 된다")

    monkeypatch.setattr(routes, "execute", _execute_should_not_be_called)

    for bad_symbol in ["../etc", "005930;DROP", "A" * 13, ""]:
        request = _mocked_post_request(
            "/api/v1/orders/buy", {"symbol": bad_symbol, "quantity": 1}
        )
        response = await routes.post_buy_order(request)
        body = json_lib.loads(response.body)

        assert response.status == 400
        assert body["approved"] is False


@pytest.mark.asyncio
async def test_post_buy_order_rejects_missing_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _execute_should_not_be_called(decision, mode, **kwargs):  # noqa: ANN001
        raise AssertionError("바디 검증에 실패하면 execute()를 호출하면 안 된다")

    monkeypatch.setattr(routes, "execute", _execute_should_not_be_called)

    request = _mocked_post_request("/api/v1/orders/buy", {"quantity": 1})
    response = await routes.post_buy_order(request)

    assert response.status == 400


@pytest.mark.asyncio
async def test_post_buy_order_executes_with_valid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.models import OrderResult

    captured: dict = {}

    async def _execute(decision, mode, **kwargs):  # noqa: ANN001
        captured["decision"] = decision
        captured["mode"] = mode
        return OrderResult(filled=True, order_id="BIN-KR-ABC123", fill_price=74_800.0)

    monkeypatch.setattr(routes, "execute", _execute)

    request = _mocked_post_request("/api/v1/orders/buy", {"symbol": "005930", "quantity": 2})
    response = await routes.post_buy_order(request)
    body = json_lib.loads(response.body)

    assert response.status == 200
    assert body["approved"] is True
    assert body["orderId"] == "BIN-KR-ABC123"
    assert captured["decision"].quantity == 2
    assert captured["mode"].market == "KR"


@pytest.mark.asyncio
async def test_post_version_rollback_rejects_unknown_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_deployed_by_name(strategy_version):  # noqa: ANN001
        return None

    monkeypatch.setattr(routes.db, "get_deployed_strategy_version_by_name", _get_deployed_by_name)

    request = _mocked_post_request(
        "/api/v1/version/rollback",
        {"strategyVersion": "v9.9.9", "approvedBy": "discord:Ruthgyeul"},
    )
    response = await routes.post_version_rollback(request)
    body = json_lib.loads(response.body)

    assert body["success"] is False
