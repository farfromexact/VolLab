import math

import numpy as np
import pandas as pd

from src.vol_metrics import iv_minus_rv, iv_percentile, iv_rank, log_returns, realized_vol


def test_log_returns():
    returns = log_returns(pd.Series([100, 105, 110]))
    assert math.isnan(returns.iloc[0])
    assert math.isclose(returns.iloc[1], math.log(1.05))


def test_realized_vol_annualizes_log_return_std():
    prices = pd.Series([100, 101, 102, 103, 104, 105])
    rv = realized_vol(prices, window=3)
    expected = log_returns(prices).rolling(3, min_periods=3).std(ddof=1).iloc[-1] * np.sqrt(252)
    assert math.isclose(rv.iloc[-1], expected)


def test_iv_rank_and_percentile():
    iv = pd.Series([0.10, 0.20, 0.30, 0.25])
    rank = iv_rank(iv, lookback=4)
    percentile = iv_percentile(iv, lookback=4)
    assert math.isclose(rank.iloc[-1], 0.75)
    assert math.isclose(percentile.iloc[-1], 0.5)


def test_iv_minus_rv():
    result = iv_minus_rv(pd.Series([0.2]), pd.Series([0.15]))
    assert math.isclose(result.iloc[0], 0.05)

