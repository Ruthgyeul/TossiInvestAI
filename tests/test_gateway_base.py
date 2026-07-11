"""Claude·DeepSeek 공용 프롬프트 조립·응답 파싱 헬퍼 테스트 (core/gateway/base.py)."""

import json

import pytest

from core.gateway.base import (
    build_portfolio_block,
    build_realtime_block,
    load_system_prompt,
    parse_decision_json,
)
from core.models import StateSnapshot


def test_parse_decision_json_extracts_fenced_json_block() -> None:
    text = (
        "판단 결과는 다음과 같습니다.\n"
        "```json\n"
        '{"action": "SELL", "symbol": "AAPL", "quantity": 1, '
        '"order_type": "LIMIT", "price": 210.5, "confidence": 0.7, '
        '"reason": "단기 과열", "risk_level": "MEDIUM"}\n'
        "```"
    )

    decision = parse_decision_json(text)

    assert decision.action == "SELL"
    assert decision.symbol == "AAPL"
    assert decision.price == 210.5
    assert decision.risk_level == "MEDIUM"
    assert decision.decision_id


def test_parse_decision_json_treats_zero_price_as_none() -> None:
    text = (
        '{"action": "HOLD", "symbol": "005930", "quantity": 0, '
        '"order_type": "MARKET", "price": 0, "confidence": 0.3, '
        '"reason": "관망", "risk_level": "LOW"}'
    )

    decision = parse_decision_json(text)

    assert decision.price is None


def _decision_payload(**overrides: object) -> str:
    data: dict = {
        "action": "BUY",
        "symbol": "005930",
        "quantity": 2,
        "order_type": "LIMIT",
        "price": 75_000,
        "confidence": 0.8,
        "reason": "테스트",
        "risk_level": "LOW",
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "SELLL"},                       # 스펙 밖 action
        {"action": "SELL "},                       # 공백 포함 — Safety Gate SELL 분기를 비껴간다
        {"symbol": "../etc/passwd"},               # 경로·특수문자 symbol
        {"symbol": ""},                            # 빈 symbol
        {"order_type": "AMOUNT"},                  # AI 결정에 허용되지 않는 주문 유형
        {"risk_level": "EXTREME"},                 # 스펙 밖 risk_level
        {"quantity": 0},                           # BUY/SELL 수량 0
        {"quantity": -3},                          # 음수 수량
        {"confidence": 1.5},                       # 범위 밖 confidence
        {"confidence": -0.1},
        {"price": -75_000},                        # 음수 가격
    ],
)
def test_parse_decision_json_rejects_out_of_spec_values(overrides: dict) -> None:
    with pytest.raises(ValueError):
        parse_decision_json(_decision_payload(**overrides))


def test_parse_decision_json_allows_zero_quantity_for_hold() -> None:
    decision = parse_decision_json(
        _decision_payload(action="HOLD", quantity=0, price=None)
    )
    assert decision.action == "HOLD"
    assert decision.quantity == 0


@pytest.mark.parametrize("version", ["../secrets", "a/b", "system_kr_v1\x00", ""])
def test_load_system_prompt_rejects_path_like_versions(version: str) -> None:
    with pytest.raises(ValueError):
        load_system_prompt(version)


def test_build_realtime_block_includes_indicators_and_events() -> None:
    state = StateSnapshot(
        bot="Bin",
        market="KR",
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices={"005930": {"price": 75_200, "rsi_14": 58.3}},
        portfolio={},
        toss_popular_top10=["005930"],
        fear_greed_index=62,
        market_events_today=[{"name": "FOMC"}],
    )

    block = build_realtime_block(state)

    assert "005930" in block
    assert "RSI 58.3" in block
    assert "FOMC" in block
    assert "공포탐욕지수: 62" in block


def test_build_portfolio_block_reports_no_holdings() -> None:
    state = StateSnapshot(
        bot="Bin",
        market="KR",
        mode="SIMULATION",
        strategy_version="v1.0.0",
        prompt_version="system_kr_v1",
        timestamp="2026-07-06T10:00:00+09:00",
        exchange_rate_krw_usd=1382.5,
        prices={},
        portfolio={"total_value_krw": 500_000, "holdings": []},
    )

    block = build_portfolio_block(state)

    assert "보유 종목 없음" in block
    assert "500,000" in block
