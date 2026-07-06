"""시세·캘린더·환율·종목 조회 (docs/TOSS_API.md)."""

from core.models import Market


async def get_price(symbol: str) -> dict:
    """GET /api/v1/prices — Redis `price:{symbol}` 10s 캐시 우선."""
    raise NotImplementedError


async def get_candles(symbol: str, timeframe: str) -> list[dict]:
    """GET /api/v1/candles — Redis `candle:{symbol}:{tf}` 60s 캐시 우선."""
    raise NotImplementedError


async def get_orderbook(symbol: str) -> dict:
    """GET /api/v1/orderbook."""
    raise NotImplementedError


async def get_price_limits(symbol: str) -> dict:
    """GET /api/v1/price-limits (KR 상·하한가)."""
    raise NotImplementedError


async def get_exchange_rate() -> float:
    """GET /api/v1/exchange-rate (KRW/USD)."""
    raise NotImplementedError


async def get_stock_warnings(symbol: str) -> dict:
    """GET /api/v1/stocks/{symbol}/warnings — VI·투자경고·정리매매 여부."""
    raise NotImplementedError


async def is_market_open(market: Market) -> bool:
    """GET /api/v1/market-calendar/{market} — 하드코딩 금지, 항상 API 기준 (CLAUDE.md 절대 규칙 4).

    Redis `market_open:{market}` 60s 캐시 우선.
    """
    raise NotImplementedError


async def is_regular_session(market: Market) -> bool:
    """정규장 여부 — 금액 주문(AMOUNT) 허용 판단에 사용. Redis `market_open:{market}` 캐시 공유."""
    raise NotImplementedError
