"""관심 종목 관리. Claude가 자동 추가·제거하며, `/watchlist add`로 수동 추가도 가능 (docs/BIN.md)."""


async def get_watchlist(market: str) -> list[dict]:
    raise NotImplementedError


async def add_symbol(symbol: str, market: str, priority: int = 0) -> None:
    raise NotImplementedError


async def remove_symbol(symbol: str) -> None:
    raise NotImplementedError
