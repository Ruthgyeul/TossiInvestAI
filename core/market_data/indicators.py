"""기술적 지표 계산 — RSI·MACD·EMA·볼린저밴드 (`ta` 라이브러리 기반)."""

import statistics

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


def calculate_max_drawdown_pct(values: list[float]) -> float:
    """자산 시계열에서 고점 대비 최대 낙폭 (음수, 예: -0.032 = -3.2%).

    core/api/routes.py `/simstatus`와 core/strategy/backtest.py가 공유한다.
    """
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value - peak) / peak)
    return max_dd


def calculate_sharpe_ratio(values: list[float]) -> float:
    """일별 수익률 평균 / 표준편차 × √252 (연환산 샤프 지수).

    core/api/routes.py `/simstatus`와 core/strategy/backtest.py가 공유한다.
    """
    if len(values) < 2:
        return 0.0
    returns = [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]
    if len(returns) < 2:
        return 0.0
    stdev = statistics.pstdev(returns)
    if stdev == 0:
        return 0.0
    return statistics.mean(returns) / stdev * (252**0.5)
