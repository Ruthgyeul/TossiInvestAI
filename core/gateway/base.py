"""AIGateway 추상 인터페이스. 모든 AI 호출은 core/gateway/ 모듈에서만 수행한다 (CODING_RULES.md).

Claude·DeepSeek이 공유하는 프롬프트 조립·응답 파싱 헬퍼도 여기에 둔다 —
둘 다 core/trading/prompts/*.md 시스템 프롬프트와 동일한 Decision JSON 스펙을 사용한다.
"""

import json
import re
import uuid
from abc import ABC, abstractmethod
from functools import cache
from pathlib import Path

from core.models import Decision, StateSnapshot

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "trading" / "prompts"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# prompt_version은 DB(strategy_versions.prompt_version)를 거쳐 파일명으로 쓰인다 —
# 경로 구분자·".." 등이 섞이면 prompts/ 밖의 파일을 읽게 되므로 형식을 강제한다.
_PROMPT_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")

# KR 종목코드(숫자 6자리)·US 티커(BRK.B, BF-B 등)를 모두 포괄하는 보수적 형식.
_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")

_VALID_ACTIONS = {"BUY", "SELL", "HOLD"}
_VALID_ORDER_TYPES = {"LIMIT", "MARKET"}
_VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


class AIGateway(ABC):
    @abstractmethod
    async def decide(self, state: StateSnapshot) -> Decision: ...

    @abstractmethod
    async def summarize_news(self, articles: list[str]) -> str: ...


@cache
def load_system_prompt(prompt_version: str) -> str:
    """L1 — `prompt_version`이 곧 파일명이다 (예: `system_kr_v1` → prompts/system_kr_v1.md).

    docs/SELF_IMPROVEMENT.md "버전 관리 및 롤백"이 요구하는 대로 프롬프트 파일명에 항상
    버전이 드러나야 하며, `strategy_versions.prompt_version`에 저장된 값을 그대로 파일명으로
    사용해 별도 마이그레이션 없이 배포된 버전의 파일을 로드한다.
    """
    if not _PROMPT_VERSION_PATTERN.fullmatch(prompt_version):
        raise ValueError(f"잘못된 prompt_version 형식: {prompt_version!r}")
    return (_PROMPTS_DIR / f"{prompt_version}.md").read_text(encoding="utf-8")


@cache
def load_reflection_prompt() -> str:
    """prompts/reflection.md — core/trading/reflection.py 자기평가 시스템 프롬프트."""
    return (_PROMPTS_DIR / "reflection.md").read_text(encoding="utf-8")


def build_realtime_block(state: StateSnapshot) -> str:
    """L3 — 현재가·지표·뉴스·환율·이벤트 (StateSnapshot, docs/BIN.md)."""
    lines = [f"환율(KRW/USD): {state.exchange_rate_krw_usd}"]

    for symbol, data in state.prices.items():
        lines.append(
            f"[{symbol}] 현재가 {data.get('price')} | RSI {data.get('rsi_14')} | "
            f"MACD {data.get('macd')}/{data.get('macd_signal')} | "
            f"EMA20 {data.get('ema_20')} / EMA60 {data.get('ema_60')} | "
            f"BB {data.get('bb_lower')}~{data.get('bb_upper')} | "
            f"거래량비 {data.get('volume_ratio')} | "
            f"뉴스: {data.get('news_summary', '없음')}"
        )

    if state.toss_popular_top10:
        lines.append(f"토스 인기 종목: {', '.join(state.toss_popular_top10)}")
    if state.fear_greed_index is not None:
        lines.append(f"공포탐욕지수: {state.fear_greed_index}")
    if state.market_events_today:
        events = ", ".join(str(e.get("name", e)) for e in state.market_events_today)
        lines.append(f"오늘 시장 이벤트: {events}")

    return "\n".join(lines)


def build_portfolio_block(state: StateSnapshot) -> str:
    """L4 — 보유 종목·잔고·손익·미체결 주문 (StateSnapshot, docs/BIN.md)."""
    portfolio = state.portfolio
    lines = [
        f"총 자산: {portfolio.get('total_value_krw', 0):,} KRW",
        f"운용 자금: {portfolio.get('operating_funds_krw', 0):,} KRW",
        f"현금 버퍼: {portfolio.get('cash_buffer_krw', 0):,} KRW",
        f"오늘 실현 손익: {portfolio.get('today_realized_pnl_krw', 0):,} KRW",
        f"이번 달 API 비용: {portfolio.get('api_cost_month_krw', 0):,} KRW",
    ]

    holdings = portfolio.get("holdings", [])
    if not holdings:
        lines.append("보유 종목 없음")
    for holding in holdings:
        lines.append(
            f"보유: {holding['symbol']} {holding['quantity']}주 "
            f"@ {holding['avg_price']:,} "
            f"(평가손익 {holding.get('unrealized_pnl', 0):,})"
        )

    open_orders = portfolio.get("open_orders", [])
    if open_orders:
        lines.append(f"미체결 주문 {len(open_orders)}건")

    return "\n".join(lines)


def parse_decision_json(text: str) -> Decision:
    """system_kr.md/system_us.md 출력 JSON 스펙 → Decision. Claude·DeepSeek 공용.

    Decision은 dataclass라 Literal 타입이 런타임에 강제되지 않는다 — 모델 출력은
    외부 데이터(뉴스 헤드라인 등)의 영향을 받는 신뢰할 수 없는 입력이므로, 여기서
    스펙을 벗어난 값을 전부 거부해 Safety Gate·토스 API로 흘러가지 않게 한다.
    """
    match = _JSON_BLOCK.search(text)
    if match is None:
        raise ValueError(f"모델 응답에서 JSON을 찾을 수 없음: {text!r}")

    data = json.loads(match.group(0))

    action = data["action"]
    if action not in _VALID_ACTIONS:
        raise ValueError(f"잘못된 action: {action!r}")

    symbol = data["symbol"]
    if not isinstance(symbol, str) or not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError(f"잘못된 symbol 형식: {symbol!r}")

    order_type = data["order_type"]
    if order_type not in _VALID_ORDER_TYPES:
        raise ValueError(f"잘못된 order_type: {order_type!r}")

    risk_level = data["risk_level"]
    if risk_level not in _VALID_RISK_LEVELS:
        raise ValueError(f"잘못된 risk_level: {risk_level!r}")

    quantity = int(data["quantity"])
    if action != "HOLD" and quantity <= 0:
        raise ValueError(f"BUY/SELL 수량은 1 이상이어야 함: {quantity}")

    confidence = float(data["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence는 0~1 범위여야 함: {confidence}")

    price = data.get("price")
    price = float(price) if price else None
    if price is not None and price <= 0:
        raise ValueError(f"price는 0보다 커야 함: {price}")

    return Decision(
        decision_id=str(uuid.uuid4()),
        action=action,
        symbol=symbol,
        quantity=quantity,
        order_type=order_type,
        price=price,
        confidence=confidence,
        reason=str(data["reason"]),
        risk_level=risk_level,
    )
