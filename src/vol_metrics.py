from __future__ import annotations

import numpy as np
import pandas as pd


def log_returns(price_series) -> pd.Series:
    prices = pd.Series(price_series, dtype="float64")
    return np.log(prices / prices.shift(1))


def realized_vol(price_series, window: int, annualization: int = 252) -> pd.Series:
    returns = log_returns(price_series)
    return returns.rolling(window=window, min_periods=window).std(ddof=1) * np.sqrt(annualization)


def iv_rank(iv_series, lookback: int = 252) -> pd.Series:
    iv = pd.Series(iv_series, dtype="float64")
    rolling_min = iv.rolling(window=lookback, min_periods=lookback).min()
    rolling_max = iv.rolling(window=lookback, min_periods=lookback).max()
    denominator = rolling_max - rolling_min
    rank = (iv - rolling_min) / denominator
    return rank.where(denominator != 0)


def iv_percentile(iv_series, lookback: int = 252) -> pd.Series:
    iv = pd.Series(iv_series, dtype="float64")

    def percentile(window: np.ndarray) -> float:
        current = window[-1]
        valid = window[np.isfinite(window)]
        if len(valid) < lookback or not np.isfinite(current):
            return np.nan
        return float(np.mean(valid < current))

    return iv.rolling(window=lookback, min_periods=lookback).apply(percentile, raw=True)


def iv_minus_rv(iv, rv):
    return pd.Series(iv, dtype="float64") - pd.Series(rv, dtype="float64")

