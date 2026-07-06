"""시세·캘린더 조회 단위 테스트 (docs/CODING_RULES.md Phase 1 4~5)."""

import json

import pytest
from aioresponses import aioresponses

from core.toss import market

_BASE_URL = "https://openapi.tossinvest.com"


@pytest.fixture(autouse=True)
def _stub_token(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_token() -> str:
        return "test-token"

    monkeypatch.setattr(market.client, "get_access_token", _fake_token)


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["005930", "AAPL"])
async def test_get_price_kr_and_us(fake_redis, symbol: str) -> None:
    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/prices?symbol={symbol}",
            payload={"symbol": symbol, "price": 100.0},
        )
        data = await market.get_price(symbol)

    assert data == {"symbol": symbol, "price": 100.0}
    cached = await fake_redis.get(f"price:{symbol}")
    assert json.loads(cached) == data


@pytest.mark.asyncio
async def test_get_price_uses_cache_without_second_http_call(fake_redis) -> None:
    await fake_redis.set(
        "price:005930", json.dumps({"symbol": "005930", "price": 1.0}), ex=10
    )

    with aioresponses():  # 등록된 목업이 없으므로 실제 호출이 발생하면 예외가 난다.
        data = await market.get_price("005930")

    assert data == {"symbol": "005930", "price": 1.0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "market_code,is_open,is_regular",
    [("KR", True, True), ("US", False, False)],
)
async def test_market_calendar_parsing(
    fake_redis, market_code: str, is_open: bool, is_regular: bool
) -> None:
    with aioresponses() as mocked:
        mocked.get(
            f"{_BASE_URL}/api/v1/market-calendar/{market_code}",
            payload={"isOpen": is_open, "isRegularSession": is_regular},
        )
        open_result = await market.is_market_open(market_code)  # type: ignore[arg-type]

    # is_regular_session은 is_market_open이 채워둔 market_open:{market} 캐시를 공유한다.
    with aioresponses():
        regular_result = await market.is_regular_session(market_code)  # type: ignore[arg-type]

    assert open_result is is_open
    assert regular_result is is_regular
