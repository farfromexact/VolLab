from __future__ import annotations

import numpy as np
import pandas as pd

from src.option_pricer import bs_delta, bs_gamma, bs_theta, bs_vega


def straddle_greeks(S: float, K: float, T: float, r: float, sigma: float) -> dict[str, float]:
    return {
        "portfolio_delta": bs_delta(S, K, T, r, sigma, "C") + bs_delta(S, K, T, r, sigma, "P"),
        "portfolio_gamma": bs_gamma(S, K, T, r, sigma) * 2.0,
        "portfolio_vega": bs_vega(S, K, T, r, sigma) * 2.0,
        "portfolio_theta": bs_theta(S, K, T, r, sigma, "C") + bs_theta(S, K, T, r, sigma, "P"),
    }


def add_entry_greeks(trade_details: pd.DataFrame, config: dict) -> pd.DataFrame:
    if trade_details.empty:
        return trade_details.copy()
    r = float(config.get("risk_free_rate", 0.02))
    rows = []
    for _, trade in trade_details.iterrows():
        T = max(float(trade["dte"]) / 252.0, 1.0 / 252.0)
        sigma = float(trade["atm_iv"]) if pd.notna(trade["atm_iv"]) else np.nan
        if not np.isfinite(sigma) or sigma <= 0:
            greeks = {
                "portfolio_delta": np.nan,
                "portfolio_gamma": np.nan,
                "portfolio_vega": np.nan,
                "portfolio_theta": np.nan,
            }
        else:
            greeks = straddle_greeks(float(trade["spot_at_signal"]), float(trade["strike"]), T, r, sigma)
        rows.append(greeks)
    greek_df = pd.DataFrame(rows, index=trade_details.index)
    return pd.concat([trade_details.copy(), greek_df], axis=1)

