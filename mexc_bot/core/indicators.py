# Utility functions for technical indicator calculations
import pandas as pd
import numpy as np


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average"""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.clip(lower=1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> dict:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.rolling(window=period).mean()

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    smooth_plus_dm = plus_dm.rolling(window=period).mean()
    smooth_minus_dm = minus_dm.rolling(window=period).mean()

    plus_di = 100 * (smooth_plus_dm / atr.replace(0, 1e-10))
    minus_di = 100 * (smooth_minus_dm / atr.replace(0, 1e-10))

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10))
    adx = dx.rolling(window=period).mean()

    return {
        'ADX': adx,
        'Plus_DI': plus_di,
        'Minus_DI': minus_di
    }


def calculate_macd(series: pd.Series, fast_period: int, slow_period: int, signal_period: int) -> dict:
    fast_ema = series.ewm(span=fast_period, adjust=False).mean()
    slow_ema = series.ewm(span=slow_period, adjust=False).mean()

    macd = fast_ema - slow_ema
    macd_signal = macd.ewm(span=signal_period, adjust=False).mean()
    macd_hist = macd - macd_signal

    return {
        'MACD': macd,
        'MACD_Signal': macd_signal,
        'MACD_Hist': macd_hist
    }
