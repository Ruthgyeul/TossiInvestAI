"""시세·뉴스 수집. 트레이딩 루프 STEP 2에서 호출된다 (docs/BIN.md)."""

from core.models import Market


async def collect_market_snapshot(market: Market, symbols: list[str]) -> dict:
    """관심 종목 현재가·캔들·거래량·보유 현황·인기 종목·오늘 이벤트를 한 번에 수집한다."""
    raise NotImplementedError
