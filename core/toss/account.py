"""계좌·보유주식·매수가능금액 조회 (docs/TOSS_API.md)."""


async def get_accounts() -> list[dict]:
    """GET /api/v1/accounts."""
    raise NotImplementedError


async def get_holdings() -> list[dict]:
    """GET /api/v1/holdings — KR·US 통합 보유 주식."""
    raise NotImplementedError


async def get_buying_power() -> float:
    """GET /api/v1/buying-power."""
    raise NotImplementedError


async def get_sellable_quantity(symbol: str) -> int:
    """GET /api/v1/sellable-quantity."""
    raise NotImplementedError


async def get_commissions(market: str) -> dict:
    """GET /api/v1/commissions — KR·US 요율이 다르다."""
    raise NotImplementedError
