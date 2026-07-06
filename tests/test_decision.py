"""StateSnapshot → Decision JSON 통합 테스트 (docs/BIN.md)."""

import httpx
import pytest

from core import models
from core.gateway.claude import claude_gateway
from core.gateway.deepseek import deepseek_gateway
from core.trading import decision as decision_module


def _make_state(prices: dict, holdings: list | None = None) -> models.StateSnapshot:
    return models.StateSnapshot(
        bot="Bin",
        market="KR",
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices=prices,
        portfolio={"holdings": holdings or []},
    )


@pytest.mark.asyncio
async def test_rule_based_filter_skips_claude_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _decide_should_not_be_called(
        state: models.StateSnapshot,
    ) -> models.Decision:
        raise AssertionError("규칙 기반으로 처리 가능하면 Claude를 호출하지 않아야 한다")

    monkeypatch.setattr(claude_gateway, "decide", _decide_should_not_be_called)

    state = _make_state(
        prices={"005930": {"price": 75_000, "rsi_14": 80.0}},
        holdings=[{"symbol": "005930", "quantity": 2, "avg_price": 70_000}],
    )

    result = await decision_module.get_decision(state)

    assert result.action == "SELL"
    assert result.symbol == "005930"
    assert result.quantity == 2


@pytest.mark.asyncio
async def test_rule_based_filter_returns_none_when_signal_unclear() -> None:
    state = _make_state(prices={"005930": {"price": 75_000, "rsi_14": 50.0}})

    assert decision_module.rule_based_filter(state) is None


@pytest.mark.asyncio
async def test_claude_failure_falls_back_to_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    async def _claude_fails(state: models.StateSnapshot) -> models.Decision:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(500, request=request)
        raise anthropic.APIStatusError("boom", response=response, body=None)

    fallback_decision = models.Decision(
        decision_id="fallback-id",
        action="HOLD",
        symbol="005930",
        quantity=0,
        order_type="MARKET",
        price=None,
        confidence=0.5,
        reason="DeepSeek 폴백",
        risk_level="LOW",
    )

    async def _deepseek_decides(state: models.StateSnapshot) -> models.Decision:
        return fallback_decision

    monkeypatch.setattr(claude_gateway, "decide", _claude_fails)
    monkeypatch.setattr(deepseek_gateway, "decide", _deepseek_decides)

    state = _make_state(prices={"005930": {"price": 75_000, "rsi_14": 50.0}})

    result = await decision_module.get_decision(state)

    assert result is fallback_decision
