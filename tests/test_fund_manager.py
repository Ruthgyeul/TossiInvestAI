"""FundManager 자금 배분·API 비용 기록 단위 테스트 (docs/FUND_MANAGER.md)."""

import pytest

from core.config import settings
from core.fund.manager import FundManager
from core.simulation.portfolio import SimPosition, SimulationPortfolio
from core.toss import account as toss_account
from core.toss import market as toss_market


@pytest.fixture
def fund_manager() -> FundManager:
    return FundManager()


@pytest.mark.asyncio
async def test_can_allocate_rejects_over_position_ratio(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _operating_funds(mode: str = "LIVE") -> float:
        return 425_000.0

    async def _position_value(symbol: str, mode: str = "LIVE") -> float:
        return 150_000.0  # 이미 운용 자금의 약 35% 보유 중

    monkeypatch.setattr(fund_manager, "get_operating_funds_krw", _operating_funds)
    monkeypatch.setattr(fund_manager, "_get_position_value_krw", _position_value)

    # 150,000 + 100,000 = 250,000 / 425,000 ≈ 58.8% > MAX_POSITION_RATIO(50%)
    allowed, reason = await fund_manager.can_allocate(100_000, "005930")

    assert allowed is False
    assert "종목당 상한" in reason


@pytest.mark.asyncio
async def test_can_allocate_allows_order_within_ratio(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _operating_funds(mode: str = "LIVE") -> float:
        return 425_000.0

    async def _position_value(symbol: str, mode: str = "LIVE") -> float:
        return 0.0

    monkeypatch.setattr(fund_manager, "get_operating_funds_krw", _operating_funds)
    monkeypatch.setattr(fund_manager, "_get_position_value_krw", _position_value)

    allowed, reason = await fund_manager.can_allocate(100_000, "005930")

    assert allowed is True


@pytest.mark.asyncio
async def test_can_allocate_rejects_when_no_operating_funds(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _operating_funds(mode: str = "LIVE") -> float:
        return 0.0

    monkeypatch.setattr(fund_manager, "get_operating_funds_krw", _operating_funds)

    allowed, reason = await fund_manager.can_allocate(10_000, "005930")

    assert allowed is False
    assert "운용 자금 부족" in reason


@pytest.mark.asyncio
async def test_get_position_ratio(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _operating_funds(mode: str = "LIVE") -> float:
        return 425_000.0

    async def _position_value(symbol: str, mode: str = "LIVE") -> float:
        return 85_000.0

    monkeypatch.setattr(fund_manager, "get_operating_funds_krw", _operating_funds)
    monkeypatch.setattr(fund_manager, "_get_position_value_krw", _position_value)

    ratio = await fund_manager.get_position_ratio("005930")

    assert ratio == pytest.approx(85_000 / 425_000)


@pytest.mark.asyncio
async def test_record_api_usage_applies_cache_pricing(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: dict = {}

    async def _insert_api_usage(
        model: str,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
    ) -> None:
        recorded.update(
            model=model,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

    monkeypatch.setattr(fund_manager, "_insert_api_usage", _insert_api_usage)

    await fund_manager.record_api_usage(
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=500,
        cache_write_tokens=300,
    )

    p_in = settings.claude_input_price_per_mtok / 1_000_000
    p_out = settings.claude_output_price_per_mtok / 1_000_000
    expected_cost_usd = (
        1000 * p_in + 300 * p_in * 1.25 + 500 * p_in * 0.10 + 200 * p_out
    )

    assert recorded["model"] == "claude-sonnet-4-6"
    assert recorded["cost_usd"] == pytest.approx(expected_cost_usd)
    assert recorded["input_tokens"] == 1000
    assert recorded["output_tokens"] == 200
    assert recorded["cache_read_tokens"] == 500
    assert recorded["cache_write_tokens"] == 300


@pytest.mark.asyncio
async def test_weekly_rebalance_splits_net_profit_80_20(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _estimated_api_cost_krw() -> float:
        return 8_000.0

    async def _weekly_net_profit_krw(mode: str = "LIVE") -> int:
        return 40_000

    async def _total_value_krw(mode: str = "LIVE") -> float:
        return 550_000.0

    async def _cash_buffer_krw(mode: str = "LIVE") -> float:
        return 75_000.0

    monkeypatch.setattr(fund_manager, "estimated_api_cost_krw", _estimated_api_cost_krw)
    monkeypatch.setattr(fund_manager, "get_total_value_krw", _total_value_krw)
    monkeypatch.setattr(fund_manager, "get_cash_buffer_krw", _cash_buffer_krw)

    import core.fund.manager as manager_module

    monkeypatch.setattr(
        manager_module.db, "get_weekly_net_profit_krw", _weekly_net_profit_krw
    )
    inserted: list[tuple[str, dict]] = []

    async def _insert(table: str, values: dict) -> dict:
        inserted.append((table, values))
        return values

    monkeypatch.setattr(manager_module.db, "insert", _insert)

    result = await fund_manager.weekly_rebalance()

    # remaining = 40,000 - 8,000 = 32,000 → 80% 재투자(25,600) / 20% 버퍼(6,400)
    assert result.api_cost_covered_krw == 8_000
    assert result.reinvested_krw == 25_600
    assert result.buffer_added_krw == 6_400

    # 계산 결과가 감사 가능한 이력으로 영구 기록되어야 한다 (docs/FUND_MANAGER.md).
    assert inserted[0][0] == "fund_rebalances"
    assert inserted[0][1]["reinvested_krw"] == 25_600
    assert inserted[0][1]["buffer_added_krw"] == 6_400
    assert inserted[0][1]["total_value_krw"] == 550_000


@pytest.mark.asyncio
async def test_weekly_rebalance_moves_buffer_overflow_to_operating_funds(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _estimated_api_cost_krw() -> float:
        return 0.0

    async def _weekly_net_profit_krw(mode: str = "LIVE") -> int:
        return 100_000

    async def _total_value_krw(mode: str = "LIVE") -> float:
        return 500_000.0  # 버퍼 상한 = 100,000

    async def _cash_buffer_krw(mode: str = "LIVE") -> float:
        return 95_000.0  # 이미 상한에 근접

    monkeypatch.setattr(fund_manager, "estimated_api_cost_krw", _estimated_api_cost_krw)
    monkeypatch.setattr(fund_manager, "get_total_value_krw", _total_value_krw)
    monkeypatch.setattr(fund_manager, "get_cash_buffer_krw", _cash_buffer_krw)

    import core.fund.manager as manager_module

    monkeypatch.setattr(
        manager_module.db, "get_weekly_net_profit_krw", _weekly_net_profit_krw
    )

    async def _insert(table: str, values: dict) -> dict:
        return values

    monkeypatch.setattr(manager_module.db, "insert", _insert)

    result = await fund_manager.weekly_rebalance()

    # remaining=100,000 → 재투자 80,000 / 버퍼 20,000 → 버퍼 합계 115,000 > 상한 100,000
    # 초과분 15,000은 운용 자금으로 이동
    assert result.buffer_added_krw == 5_000
    assert result.reinvested_krw == 95_000


@pytest.mark.asyncio
async def test_get_last_rebalance_returns_most_recent_record(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.fund.manager as manager_module

    async def _fetch_all(table, filters=None, *, order_by=None, descending=False, limit=None):  # noqa: ANN001
        assert table == "fund_rebalances"
        assert filters == {"mode": "LIVE"}
        assert order_by == "created_at" and descending is True and limit == 1
        return [{"reinvested_krw": 25_600, "buffer_added_krw": 6_400}]

    monkeypatch.setattr(manager_module.db, "fetch_all", _fetch_all)

    last = await fund_manager.get_last_rebalance()

    assert last == {"reinvested_krw": 25_600, "buffer_added_krw": 6_400}


@pytest.mark.asyncio
async def test_simulation_mode_never_touches_live_toss_account(
    fund_manager: FundManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SIMULATION 모드에서는 실계좌(toss_account)를 절대 조회하지 않아야 한다

    (CLAUDE.md 규칙 11 — 실전 DB와 시뮬레이션 DB 절대 혼용 금지)."""

    async def _fail_get_holdings() -> list[dict]:
        raise AssertionError("SIMULATION 모드에서 실계좌 보유종목을 조회하면 안 된다")

    async def _fail_get_buying_power() -> float:
        raise AssertionError("SIMULATION 모드에서 실계좌 예수금을 조회하면 안 된다")

    monkeypatch.setattr(toss_account, "get_holdings", _fail_get_holdings)
    monkeypatch.setattr(toss_account, "get_buying_power", _fail_get_buying_power)

    sim_portfolio = SimulationPortfolio(cash=100_000.0)
    sim_portfolio.positions["005930"] = SimPosition(qty=10, avg_price=70_000.0, market="KR")

    async def _load() -> SimulationPortfolio:
        return sim_portfolio

    monkeypatch.setattr(SimulationPortfolio, "load", _load)

    async def _get_price(symbol: str) -> dict:
        return {"price": 75_000.0}

    async def _get_exchange_rate() -> float:
        return 1_382.0

    monkeypatch.setattr(toss_market, "get_price", _get_price)
    monkeypatch.setattr(toss_market, "get_exchange_rate", _get_exchange_rate)

    total_value = await fund_manager.get_total_value_krw("SIMULATION")

    assert total_value == pytest.approx(100_000.0 + 10 * 75_000.0)
