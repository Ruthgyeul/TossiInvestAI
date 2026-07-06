"""Claude API 직접 호출 — Prompt Caching L1(1h)·L2(5m) 레이어 구성 테스트 (docs/BIN.md)."""

import json
from types import SimpleNamespace

import anthropic
import pytest

import core.gateway.claude as claude_module
from core.gateway.base import load_system_prompt
from core.models import StateSnapshot


def _make_state(market: str = "KR") -> StateSnapshot:
    return StateSnapshot(
        bot="Bin",
        market=market,  # type: ignore[arg-type]
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices={"005930": {"price": 75_000, "rsi_14": 58.3}},
        portfolio={
            "total_value_krw": 512_000,
            "operating_funds_krw": 435_200,
            "cash_buffer_krw": 76_800,
            "holdings": [
                {"symbol": "005930", "quantity": 2, "avg_price": 74_800, "unrealized_pnl": 800}
            ],
            "open_orders": [],
            "today_realized_pnl_krw": 0,
            "api_cost_month_krw": 4_200,
        },
    )


def test_load_system_prompt_reads_market_specific_file() -> None:
    assert "한국장(KRX)" in load_system_prompt("KR")
    assert "미국장" in load_system_prompt("US")


@pytest.mark.asyncio
async def test_decide_sends_prompt_caching_layers_and_records_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_json = json.dumps(
        {
            "action": "BUY",
            "symbol": "005930",
            "quantity": 2,
            "order_type": "LIMIT",
            "price": 75_000,
            "confidence": 0.8,
            "reason": "RSI 반등 + 거래량 확인",
            "risk_level": "LOW",
        }
    )
    fake_usage = SimpleNamespace(
        input_tokens=1842,
        output_tokens=312,
        cache_read_input_tokens=2300,
        cache_creation_input_tokens=0,
    )
    fake_response = SimpleNamespace(
        content=[anthropic.types.TextBlock(text=decision_json, type="text")],
        usage=fake_usage,
    )

    captured_create_kwargs: dict = {}

    async def _fake_create(**kwargs):
        captured_create_kwargs.update(kwargs)
        return fake_response

    async def _fake_long_term_memory(market: str) -> dict:
        return {"trade_count": 3, "win_rate": 0.66, "reflection_summary": "양호"}

    captured_usage_kwargs: dict = {}

    async def _fake_record_api_usage(**kwargs):
        captured_usage_kwargs.update(kwargs)

    monkeypatch.setattr(claude_module._client.messages, "create", _fake_create)
    monkeypatch.setattr(claude_module.db, "get_long_term_memory", _fake_long_term_memory)
    monkeypatch.setattr(
        claude_module.fund_manager, "record_api_usage", _fake_record_api_usage
    )

    state = _make_state()
    result = await claude_module.claude_gateway.decide(state)

    # L1 — 시스템 프롬프트는 1h 캐시
    system_blocks = captured_create_kwargs["system"]
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "한국장(KRX)" in system_blocks[0]["text"]

    # L2 — 장기 기억은 5m(기본) 캐시, L3·L4는 캐시 없음
    content_blocks = captured_create_kwargs["messages"][0]["content"]
    assert content_blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "[장기 기억]" in content_blocks[0]["text"]
    assert "cache_control" not in content_blocks[1]
    assert "[실시간 시장 데이터]" in content_blocks[1]["text"]
    assert "cache_control" not in content_blocks[2]
    assert "[포트폴리오]" in content_blocks[2]["text"]

    # 사용량은 FundManager로 위임 + Decision은 JSON 파싱 결과와 일치
    assert captured_usage_kwargs == {
        "model": "claude-sonnet-4-6",
        "input_tokens": 1842,
        "output_tokens": 312,
        "cache_read_tokens": 2300,
        "cache_write_tokens": 0,
    }
    assert result.action == "BUY"
    assert result.symbol == "005930"
    assert result.quantity == 2
