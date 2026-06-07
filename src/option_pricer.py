from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def _option_type(option_type: str) -> str:
    value = str(option_type).upper()
    if value not in {"C", "P"}:
        raise ValueError("option_type must be 'C' or 'P'")
    return value


def _intrinsic(S: float, K: float, option_type: str) -> float:
    if option_type == "C":
        return max(float(S) - float(K), 0.0)
    return max(float(K) - float(S), 0.0)


def _zero_vol_price(S: float, K: float, T: float, r: float, option_type: str) -> float:
    discounted_strike = float(K) * math.exp(-float(r) * max(float(T), 0.0))
    if option_type == "C":
        return max(float(S) - discounted_strike, 0.0)
    return max(discounted_strike - float(S), 0.0)


def _valid_spot_strike(S: float, K: float) -> bool:
    return np.isfinite(S) and np.isfinite(K) and float(S) > 0 and float(K) > 0


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    sqrt_t = math.sqrt(float(T))
    d1 = (math.log(float(S) / float(K)) + (float(r) + 0.5 * float(sigma) ** 2) * float(T)) / (
        float(sigma) * sqrt_t
    )
    d2 = d1 - float(sigma) * sqrt_t
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    option = _option_type(option_type)
    if not _valid_spot_strike(S, K):
        return np.nan
    if not np.isfinite(T) or float(T) <= 0:
        return _intrinsic(S, K, option)
    if not np.isfinite(sigma) or float(sigma) <= 0:
        return _zero_vol_price(S, K, T, r, option)

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    discounted_strike = float(K) * math.exp(-float(r) * float(T))
    if option == "C":
        return float(S) * norm.cdf(d1) - discounted_strike * norm.cdf(d2)
    return discounted_strike * norm.cdf(-d2) - float(S) * norm.cdf(-d1)


def bs_delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    option = _option_type(option_type)
    if not _valid_spot_strike(S, K):
        return np.nan
    if not np.isfinite(T) or float(T) <= 0 or not np.isfinite(sigma) or float(sigma) <= 0:
        if option == "C":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return norm.cdf(d1) if option == "C" else norm.cdf(d1) - 1.0


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if not _valid_spot_strike(S, K):
        return np.nan
    if not np.isfinite(T) or float(T) <= 0 or not np.isfinite(sigma) or float(sigma) <= 0:
        return 0.0
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return norm.pdf(d1) / (float(S) * float(sigma) * math.sqrt(float(T)))


def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if not _valid_spot_strike(S, K):
        return np.nan
    if not np.isfinite(T) or float(T) <= 0 or not np.isfinite(sigma) or float(sigma) <= 0:
        return 0.0
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return float(S) * norm.pdf(d1) * math.sqrt(float(T))


def bs_theta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    option = _option_type(option_type)
    if not _valid_spot_strike(S, K):
        return np.nan
    if not np.isfinite(T) or float(T) <= 0 or not np.isfinite(sigma) or float(sigma) <= 0:
        return 0.0

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    first = -(float(S) * norm.pdf(d1) * float(sigma)) / (2.0 * math.sqrt(float(T)))
    discounted_strike = float(K) * math.exp(-float(r) * float(T))
    if option == "C":
        return first - float(r) * discounted_strike * norm.cdf(d2)
    return first + float(r) * discounted_strike * norm.cdf(-d2)


def implied_vol(price: float, S: float, K: float, T: float, r: float, option_type: str) -> float:
    option = _option_type(option_type)
    if not np.isfinite(price) or float(price) <= 0:
        return np.nan
    if not _valid_spot_strike(S, K) or not np.isfinite(T) or float(T) <= 0:
        return np.nan

    lower_bound = _zero_vol_price(S, K, T, r, option)
    upper_bound = float(S) if option == "C" else float(K) * math.exp(-float(r) * float(T))
    if float(price) <= lower_bound + 1e-10:
        return 0.0
    if float(price) > upper_bound + 1e-8:
        return np.nan

    def objective(vol: float) -> float:
        return bs_price(S, K, T, r, vol, option) - float(price)

    low = 1e-6
    high = 5.0
    try:
        if objective(high) < 0:
            high = 10.0
        if objective(high) < 0:
            return np.nan
        return brentq(objective, low, high, xtol=1e-10, rtol=1e-10, maxiter=200)
    except (ValueError, RuntimeError, OverflowError):
        return np.nan

