"""기술적 지표 계산 — RSI·MACD·EMA·볼린저밴드 (`ta` 라이브러리 기반)."""

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands


def calculate_rsi(candles: pd.Series, period: int = 14) -> float:
    return float(RSIIndicator(candles, window=period).rsi().iloc[-1])


def calculate_macd(candles: pd.Series) -> tuple[float, float]:
    """(macd, macd_signal) 반환."""
    macd_indicator = MACD(candles)
    return (
        float(macd_indicator.macd().iloc[-1]),
        float(macd_indicator.macd_signal().iloc[-1]),
    )


def calculate_ema(candles: pd.Series, period: int) -> float:
    return float(EMAIndicator(candles, window=period).ema_indicator().iloc[-1])


def calculate_bollinger_bands(candles: pd.Series) -> tuple[float, float]:
    """(bb_upper, bb_lower) 반환."""
    bands = BollingerBands(candles)
    return float(bands.bollinger_hband().iloc[-1]), float(bands.bollinger_lband().iloc[-1])


def calculate_volume_ratio(today_volume: float, prev_day_volume: float) -> float:
    if prev_day_volume <= 0:
        return 0.0
    return today_volume / prev_day_volume
