"""DeepSeek Free Tier — Claude 폴백 호출 테스트 (docs/BIN.md)."""

import json
from types import SimpleNamespace

import pytest

import core.gateway.deepseek as deepseek_module
from core.gateway.deepseek import deepseek_gateway
from core.models import StateSnapshot


def _make_state() -> StateSnapshot:
    return StateSnapshot(
        bot="Bin",
        market="KR",
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices={"005930": {"price": 75_000, "rsi_14": 50.0}},
        portfolio={"holdings": []},
    )


@pytest.mark.asyncio
async def test_decide_parses_chat_completion_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_json = json.dumps(
        {
            "action": "HOLD",
            "symbol": "005930",
            "quantity": 0,
            "order_type": "MARKET",
            "price": 0,
            "confidence": 0.4,
            "reason": "신호 불확실 — Claude 폴백",
            "risk_level": "LOW",
        }
    )
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=decision_json))]
    )

    captured_kwargs: dict = {}

    async def _fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_response

    monkeypatch.setattr(
        deepseek_module._client.chat.completions, "create", _fake_create
    )

    result = await deepseek_gateway.decide(_make_state())

    assert captured_kwargs["model"] == deepseek_module.settings.DEEPSEEK_MODEL
    assert captured_kwargs["messages"][0]["role"] == "system"
    assert "한국장(KRX)" in captured_kwargs["messages"][0]["content"]
    assert captured_kwargs["messages"][1]["role"] == "user"
    assert "[실시간 시장 데이터]" in captured_kwargs["messages"][1]["content"]
    assert "[포트폴리오]" in captured_kwargs["messages"][1]["content"]

    assert result.action == "HOLD"
    assert result.symbol == "005930"
    assert result.price is None


@pytest.mark.asyncio
async def test_summarize_news_is_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        await deepseek_gateway.summarize_news(["기사"])
