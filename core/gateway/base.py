"""AIGateway 추상 인터페이스. 모든 AI 호출은 core/gateway/ 모듈에서만 수행한다 (CODING_RULES.md).

Claude·DeepSeek이 공유하는 프롬프트 조립·응답 파싱 헬퍼도 여기에 둔다 —
둘 다 core/trading/prompts/*.md 시스템 프롬프트와 동일한 Decision JSON 스펙을 사용한다.
"""

import json
import re
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from core.models import Decision, StateSnapshot

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "trading" / "prompts"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class AIGateway(ABC):
    @abstractmethod
    async def decide(self, state: StateSnapshot) -> Decision: ...

    @abstractmethod
    async def summarize_news(self, articles: list[str]) -> str: ...


@lru_cache(maxsize=None)
def load_system_prompt(market: str) -> str:
    """L1 — prompts/system_kr.md 또는 system_us.md (docs/BIN.md)."""
    filename = "system_kr.md" if market == "KR" else "system_us.md"
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


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
    """system_kr.md/system_us.md 출력 JSON 스펙 → Decision. Claude·DeepSeek 공용."""
    match = _JSON_BLOCK.search(text)
    if match is None:
        raise ValueError(f"모델 응답에서 JSON을 찾을 수 없음: {text!r}")

    data = json.loads(match.group(0))
    price = data.get("price")
    return Decision(
        decision_id=str(uuid.uuid4()),
        action=data["action"],
        symbol=data["symbol"],
        quantity=int(data["quantity"]),
        order_type=data["order_type"],
        price=float(price) if price else None,
        confidence=float(data["confidence"]),
        reason=data["reason"],
        risk_level=data["risk_level"],
    )
