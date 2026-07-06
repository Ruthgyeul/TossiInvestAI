"""전략 클래스 단위 테스트 — decision.py가 위임하는 실제 신호 생성 로직 (docs/CODING_RULES.md 확장성 원칙)."""

import pytest

from core.models import StateSnapshot
from core.strategy.kr.mean_reversion import MeanReversionStrategy
from core.strategy.kr.momentum import MomentumStrategy as KRMomentumStrategy
from core.strategy.us.momentum import MomentumStrategy as USMomentumStrategy
from core.strategy.us.overnight import OvernightStrategy
from core.trading import decision as decision_module


def _make_state(market: str, prices: dict, holdings: list | None = None) -> StateSnapshot:
    return StateSnapshot(
        bot="Bin",
        market=market,  # type: ignore[arg-type]
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices=prices,
        portfolio={"holdings": holdings or []},
    )


@pytest.mark.asyncio
async def test_mean_reversion_buys_on_oversold_rsi() -> None:
    state = _make_state("KR", {"005930": {"price": 7_000, "rsi_14": 20.0}})

    signal = await MeanReversionStrategy().generate_signal(state)

    assert signal is not None
    assert signal.action == "BUY"
    assert signal.symbol == "005930"
    assert signal.confidence == 1.0


@pytest.mark.asyncio
async def test_mean_reversion_skips_oversold_buy_when_vi_triggered() -> None:
    state = _make_state(
        "KR", {"005930": {"price": 7_000, "rsi_14": 20.0, "vi_triggered": True}}
    )

    assert await MeanReversionStrategy().generate_signal(state) is None


@pytest.mark.asyncio
async def test_kr_momentum_buys_on_volume_surge_and_ema_breakout() -> None:
    state = _make_state(
        "KR",
        {"005930": {"price": 7_000, "volume_ratio": 2.5, "ema_20": 7_100, "ema_60": 6_900}},
    )

    signal = await KRMomentumStrategy().generate_signal(state)

    assert signal is not None
    assert signal.action == "BUY"
    assert "거래량" in signal.reason


@pytest.mark.asyncio
async def test_momentum_skips_symbol_already_held() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 200.0, "volume_ratio": 3.0, "ema_20": 210.0, "ema_60": 190.0}},
        holdings=[{"symbol": "AAPL", "quantity": 1}],
    )

    assert await USMomentumStrategy().generate_signal(state) is None


@pytest.mark.asyncio
async def test_momentum_skips_when_volume_below_surge_threshold() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 200.0, "volume_ratio": 1.2, "ema_20": 210.0, "ema_60": 190.0}},
    )

    assert await USMomentumStrategy().generate_signal(state) is None


@pytest.mark.asyncio
async def test_overnight_sells_on_gap_up_take_profit() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 220.0, "day_open": 218.0, "gap_pct": 6.0}},
        holdings=[{"symbol": "AAPL", "quantity": 3}],
    )

    signal = await OvernightStrategy().generate_signal(state)

    assert signal is not None
    assert signal.action == "SELL"
    assert signal.quantity == 3
    assert "차익 실현" in signal.reason


@pytest.mark.asyncio
async def test_overnight_sells_on_gap_up_reversal_below_open() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 209.0, "day_open": 210.0, "gap_pct": 2.0}},
        holdings=[{"symbol": "AAPL", "quantity": 3}],
    )

    signal = await OvernightStrategy().generate_signal(state)

    assert signal is not None
    assert signal.action == "SELL"
    assert "추세 반전" in signal.reason


@pytest.mark.asyncio
async def test_overnight_sells_on_gap_down_stop_loss() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 190.0, "day_open": 190.0, "gap_pct": -6.0}},
        holdings=[{"symbol": "AAPL", "quantity": 3}],
    )

    signal = await OvernightStrategy().generate_signal(state)

    assert signal is not None
    assert signal.action == "SELL"
    assert "원칙적 손절" in signal.reason


@pytest.mark.asyncio
async def test_overnight_holds_on_small_gap() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 201.0, "day_open": 200.0, "gap_pct": 1.0}},
        holdings=[{"symbol": "AAPL", "quantity": 3}],
    )

    assert await OvernightStrategy().generate_signal(state) is None


@pytest.mark.asyncio
async def test_overnight_ignores_unheld_symbols() -> None:
    state = _make_state("US", {"AAPL": {"price": 220.0, "day_open": 218.0, "gap_pct": 6.0}})

    assert await OvernightStrategy().generate_signal(state) is None


@pytest.mark.asyncio
async def test_decision_rule_based_filter_dispatches_overnight_before_momentum_for_us() -> None:
    state = _make_state(
        "US",
        {"AAPL": {"price": 220.0, "day_open": 218.0, "gap_pct": 6.0, "volume_ratio": 3.0, "ema_20": 210.0, "ema_60": 190.0}},
        holdings=[{"symbol": "AAPL", "quantity": 3}],
    )

    signal = await decision_module.rule_based_filter(state)

    assert signal is not None
    assert signal.action == "SELL"
    assert "차익 실현" in signal.reason


@pytest.mark.asyncio
async def test_decision_rule_based_filter_falls_through_to_momentum_for_kr() -> None:
    """RSI가 중립이라 mean_reversion은 통과하지만 거래량 급증 조건은 momentum이 잡아야 한다."""
    state = _make_state(
        "KR",
        {
            "005930": {
                "price": 7_000,
                "rsi_14": 50.0,
                "volume_ratio": 3.0,
                "ema_20": 71_000,
                "ema_60": 69_000,
            }
        },
    )

    signal = await decision_module.rule_based_filter(state)

    assert signal is not None
    assert signal.action == "BUY"
    assert "추세 돌파" in signal.reason
