"""시세·캘린더·환율·종목 조회 (docs/TOSS_API.md)."""

import json as json_lib
from typing import Any

from core.db.redis import get_redis
from core.models import Market
from core.toss import client

_PRICE_TTL = 10
_CANDLE_TTL = 60
_MARKET_CALENDAR_TTL = 60


async def get_price(symbol: str) -> dict:
    """GET /api/v1/prices — Redis `price:{symbol}` 10s 캐시 우선."""
    redis = get_redis()
    key = f"price:{symbol}"
    cached = await redis.get(key)
    if cached is not None:
        return json_lib.loads(cached)  # type: ignore[no-any-return]

    data = await client.request(
        "GET", "/api/v1/prices", "MARKET_DATA", params={"symbol": symbol}
    )
    await redis.set(key, json_lib.dumps(data), ex=_PRICE_TTL)
    return data


async def get_candles(symbol: str, timeframe: str) -> list[dict]:
    """GET /api/v1/candles — Redis `candle:{symbol}:{tf}` 60s 캐시 우선."""
    redis = get_redis()
    key = f"candle:{symbol}:{timeframe}"
    cached = await redis.get(key)
    if cached is not None:
        return json_lib.loads(cached)  # type: ignore[no-any-return]

    data = await client.request(
        "GET",
        "/api/v1/candles",
        "MARKET_DATA_CHART",
        params={"symbol": symbol, "timeframe": timeframe},
    )
    candles: list[dict] = data["candles"]
    await redis.set(key, json_lib.dumps(candles), ex=_CANDLE_TTL)
    return candles


async def get_orderbook(symbol: str) -> dict:
    """GET /api/v1/orderbook."""
    return await client.request(
        "GET", "/api/v1/orderbook", "MARKET_DATA", params={"symbol": symbol}
    )


async def get_price_limits(symbol: str) -> dict:
    """GET /api/v1/price-limits (KR 상·하한가)."""
    return await client.request(
        "GET", "/api/v1/price-limits", "MARKET_DATA", params={"symbol": symbol}
    )


async def get_exchange_rate() -> float:
    """GET /api/v1/exchange-rate (KRW/USD)."""
    data = await client.request("GET", "/api/v1/exchange-rate", "MARKET_INFO")
    return float(data["rate"])


async def get_stock_warnings(symbol: str) -> dict:
    """GET /api/v1/stocks/{symbol}/warnings — VI·투자경고·정리매매 여부."""
    return await client.request("GET", f"/api/v1/stocks/{symbol}/warnings", "STOCK")


async def get_stock_info(symbol: str) -> dict:
    """GET /api/v1/stocks — 종목 기본 정보 (docs/TOSS_API.md 전체 엔드포인트 표 "종목")."""
    return await client.request("GET", "/api/v1/stocks", "STOCK", params={"symbol": symbol})


async def get_recent_trades(symbol: str) -> list[dict]:
    """GET /api/v1/trades — 최근 체결 내역 (docs/TOSS_API.md 전체 엔드포인트 표 "체결")."""
    data = await client.request("GET", "/api/v1/trades", "MARKET_DATA", params={"symbol": symbol})
    return data["trades"]  # type: ignore[no-any-return]


async def _get_market_calendar(market: Market) -> dict[str, Any]:
    """GET /api/v1/market-calendar/{market} — Redis `market_open:{market}` 캐시를
    `is_market_open`·`is_regular_session`이 공유한다.
    """
    redis = get_redis()
    key = f"market_open:{market}"
    cached = await redis.get(key)
    if cached is not None:
        return json_lib.loads(cached)  # type: ignore[no-any-return]

    data = await client.request(
        "GET", f"/api/v1/market-calendar/{market}", "MARKET_INFO"
    )
    await redis.set(key, json_lib.dumps(data), ex=_MARKET_CALENDAR_TTL)
    return data


async def is_market_open(market: Market) -> bool:
    """GET /api/v1/market-calendar/{market} — 하드코딩 금지, 항상 API 기준 (CLAUDE.md 절대 규칙 4).

    Redis `market_open:{market}` 60s 캐시 우선.
    """
    data = await _get_market_calendar(market)
    return bool(data["isOpen"])


async def is_regular_session(market: Market) -> bool:
    """정규장 여부 — 금액 주문(AMOUNT) 허용 판단에 사용. Redis `market_open:{market}` 캐시 공유."""
    data = await _get_market_calendar(market)
    return bool(data.get("isRegularSession", False))
