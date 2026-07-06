"""시세·뉴스 수집. 트레이딩 루프 STEP 2에서 호출된다 (docs/BIN.md)."""

import asyncio

import pandas as pd
import structlog

from core.config import settings
from core.events.publisher import publish_event
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
        prev_close = candles_1d[-2].get("close")
        last_close = candles_1d[-1].get("close")
        if prev_close:
            entry["day_change_pct"] = (last_close - prev_close) / prev_close * 100

            # 익일 갭 대응(core/strategy/us/overnight.py)이 사용하는 시가 갭 비율·당일 시가.
            day_open = candles_1d[-1].get("open")
            if day_open:
                entry["day_open"] = day_open
                entry["gap_pct"] = (day_open - prev_close) / prev_close * 100

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

    # docs/DISCORD.md "#stock-news: 종목 관련 뉴스 요약 — 뉴스 수집마다" — 실제 요약이
    # 나온 경우에만 발행한다 (뉴스 없음/미구현 폴백은 채널 스팸을 막기 위해 제외).
    if entry["news_summary"] and entry["news_summary"] != "뉴스 없음":
        await publish_event(
            "news_summary",
            mode=settings.run_mode,
            market=market,
            payload={"symbol": symbol, "summary": entry["news_summary"]},
        )

    return entry


def _popular_top10(prices: dict[str, dict]) -> list[str]:
    """관심 종목 중 거래량 급증(`volume_ratio`) 상위 10종목.

    docs/TOSS_API.md에는 시장 전체의 "인기 종목" 랭킹 엔드포인트가 없다 — 토스증권 Open API가
    제공하는 데이터만으로는 관심 종목 범위 내에서의 거래량 급증 상위 종목을 대체 지표로 쓴다.
    """
    ranked = sorted(
        prices.items(),
        key=lambda item: item[1].get("volume_ratio", 0.0),
        reverse=True,
    )
    return [symbol for symbol, entry in ranked if "volume_ratio" in entry][:10]


def _fear_greed_index(prices: dict[str, dict]) -> int | None:
    """관심 종목 등락 비율(advance/decline breadth) 기반 0~100 대체 지표.

    CNN Fear & Greed Index와 달리 시장 전체 데이터(옵션 풋/콜 비율·VIX 등)가 아닌 토스
    Open API로 조회 가능한 관심 종목의 등락 비율만 사용한다 — 0에 가까울수록 관심 종목
    대부분이 하락(공포), 100에 가까울수록 대부분이 상승(탐욕)했음을 뜻한다.
    """
    changes = [entry["day_change_pct"] for entry in prices.values() if "day_change_pct" in entry]
    if not changes:
        return None
    advancing = sum(1 for change in changes if change > 0)
    return round(100 * advancing / len(changes))


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
        "toss_popular_top10": _popular_top10(prices),
        "fear_greed_index": _fear_greed_index(prices),
    }
