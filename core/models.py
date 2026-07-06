"""core 전역에서 공유하는 도메인 모델. gateway/safety/trading 모듈이 공통으로 참조한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Market = Literal["KR", "US"]
Mode = Literal["LIVE", "SIMULATION", "DRY_RUN"]


@dataclass
class RunMode:
    mode: Mode
    market: Market


@dataclass
class Order:
    symbol: str
    market: Market
    action: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["LIMIT", "MARKET", "AMOUNT"]
    price: float | None
    amount_krw: int
    client_order_id: str


@dataclass
class Decision:
    decision_id: str
    action: Literal["BUY", "SELL", "HOLD"]
    symbol: str
    quantity: int
    order_type: Literal["LIMIT", "MARKET"]
    price: float | None
    confidence: float
    reason: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]

    def to_order(self, market: Market, client_order_id: str) -> Order:
        raise NotImplementedError


@dataclass
class GateResult:
    approved: bool
    reason: str | None = None

    @classmethod
    def approve(cls) -> "GateResult":
        return cls(approved=True)

    @classmethod
    def reject(cls, reason: str) -> "GateResult":
        return cls(approved=False, reason=reason)


@dataclass
class OrderResult:
    filled: bool
    order_id: str | None = None
    fill_price: float | None = None
    reason: str | None = None

    @classmethod
    def rejected(cls, reason: str) -> "OrderResult":
        return cls(filled=False, reason=reason)


@dataclass
class StateSnapshot:
    """docs/BIN.md — Claude 호출 시 주입되는 StateSnapshot."""

    bot: str
    market: Market
    mode: Mode
    strategy_version: str
    prompt_version: str
    timestamp: str
    exchange_rate_krw_usd: float
    prices: dict[str, Any]
    portfolio: dict[str, Any]
    toss_popular_top10: list[str] = field(default_factory=list)
    fear_greed_index: int | None = None
    market_events_today: list[dict[str, Any]] = field(default_factory=list)
