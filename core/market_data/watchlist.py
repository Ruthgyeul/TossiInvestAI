"""관심 종목 관리. Claude가 자동 추가·제거하며, `/watchlist add`로 수동 추가도 가능 (docs/BIN.md)."""

from core.db import store as db


async def get_watchlist(market: str | None = None) -> list[dict]:
    filters = {"market": market} if market else None
    return await db.fetch_all("watchlist", filters, order_by="priority", descending=True)


async def add_symbol(symbol: str, market: str, priority: int = 0) -> None:
    await db.upsert("watchlist", {"symbol": symbol, "market": market, "priority": priority})


async def remove_symbol(symbol: str) -> None:
    await db.delete("watchlist", {"symbol": symbol})
