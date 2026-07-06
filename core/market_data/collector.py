"""시세·뉴스 수집. 트레이딩 루프 STEP 2에서 호출된다 (docs/BIN.md)."""

import asyncio

import pandas as pd
import structlog

from core.market_data import indicators
from core.market_data.news import get_news_summary
from core.models import Market
from core.toss import account as toss_account
from core.toss import market as toss_market

log = structlog.get_logger(__name__)

_EMA_SHORT = 20
_EMA_LONG = 60


async def _collect_symbol(market: Market, symbol: str) -> dict:
    price_data = await toss_market.get_price(symbol)
    candles_15m = await toss_market.get_candles(symbol, "15m")
    candles_1d = await toss_market.get_candles(symbol, "1d")

    closes_1d = pd.Series([c["close"] for c in candles_1d])
    closes_15m = [c["close"] for c in candles_15m]

    entry: dict = {
        "price": price_data["price"],
        "candles_15m": closes_15m,
    }

    if len(closes_1d) >= 15:
        entry["rsi_14"] = indicators.calculate_rsi(closes_1d)
        macd, macd_signal = indicators.calculate_macd(closes_1d)
        entry["macd"] = macd
        entry["macd_signal"] = macd_signal
        bb_upper, bb_lower = indicators.calculate_bollinger_bands(closes_1d)
        entry["bb_upper"] = bb_upper
        entry["bb_lower"] = bb_lower
    if len(closes_1d) >= _EMA_SHORT:
        entry["ema_20"] = indicators.calculate_ema(closes_1d, _EMA_SHORT)
    if len(closes_1d) >= _EMA_LONG:
        entry["ema_60"] = indicators.calculate_ema(closes_1d, _EMA_LONG)

    if len(candles_1d) >= 2:
        entry["volume_ratio"] = indicators.calculate_volume_ratio(
            candles_1d[-1].get("volume", 0), candles_1d[-2].get("volume", 0)
        )

    if market == "KR":
        try:
            warnings = await toss_market.get_stock_warnings(symbol)
            entry["vi_triggered"] = bool(warnings.get("has_restriction"))
        except Exception as e:  # noqa: BLE001 — 경고 조회 실패는 스냅샷 수집을 막지 않는다
            log.warning("stock_warnings_fetch_failed", symbol=symbol, error=str(e))

    try:
        entry["news_summary"] = await get_news_summary(symbol)
    except Exception as e:  # noqa: BLE001 — 뉴스 소스 미구현/장애 시에도 루프는 계속되어야 한다
        log.warning("news_summary_fetch_failed", symbol=symbol, error=str(e))
        entry["news_summary"] = "뉴스 없음"

    return entry


async def collect_market_snapshot(market: Market, symbols: list[str]) -> dict:
    """관심 종목 현재가·캔들·거래량·보유 현황·인기 종목·오늘 이벤트를 한 번에 수집한다."""
    symbol_entries = await asyncio.gather(
        *(_collect_symbol(market, symbol) for symbol in symbols)
    )
    prices = dict(zip(symbols, symbol_entries))

    holdings = await toss_account.get_holdings()
    buying_power = await toss_account.get_buying_power()
    exchange_rate = await toss_market.get_exchange_rate()

    return {
        "prices": prices,
        "holdings": [h for h in holdings if h["market"] == market],
        "buying_power": buying_power,
        "exchange_rate_krw_usd": exchange_rate,
    }
