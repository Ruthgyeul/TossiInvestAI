"""기술적 지표 계산 — RSI·MACD·EMA·볼린저밴드 (`ta` 라이브러리 기반)."""

import pandas as pd


def calculate_rsi(candles: pd.Series, period: int = 14) -> float:
    raise NotImplementedError


def calculate_macd(candles: pd.Series) -> tuple[float, float]:
    """(macd, macd_signal) 반환."""
    raise NotImplementedError


def calculate_ema(candles: pd.Series, period: int) -> float:
    raise NotImplementedError


def calculate_bollinger_bands(candles: pd.Series) -> tuple[float, float]:
    """(bb_upper, bb_lower) 반환."""
    raise NotImplementedError


def calculate_volume_ratio(today_volume: float, prev_day_volume: float) -> float:
    raise NotImplementedError
