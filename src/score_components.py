from __future__ import annotations

import numpy as np
import pandas as pd


SCORE_COLUMNS = [
    "valuation_score",
    "compression_score",
    "trigger_score",
    "liquidity_score",
    "old_vol_long_score",
]


def _clip_score(values) -> pd.Series:
    return pd.Series(values, dtype="float64").clip(lower=0, upper=100)


def _linear_low_is_good(series: pd.Series, low_good: float, high_bad: float) -> pd.Series:
    values = pd.Series(series, dtype="float64")
    return _clip_score((high_bad - values) / (high_bad - low_good) * 100.0)


def _linear_high_is_good(series: pd.Series, low_bad: float, high_good: float) -> pd.Series:
    values = pd.Series(series, dtype="float64")
    return _clip_score((values - low_bad) / (high_good - low_bad) * 100.0)


def _row_mean(frame: pd.DataFrame) -> pd.Series:
    return frame.mean(axis=1, skipna=True)


def _expanding_percentile(series: pd.Series, min_periods: int = 20) -> pd.Series:
    values = pd.Series(series, dtype="float64")
    out = []
    for idx in range(len(values)):
        window = values.iloc[: idx + 1].dropna()
        current = values.iloc[idx]
        if len(window) < min_periods or pd.isna(current):
            out.append(np.nan)
        else:
            out.append(float((window < current).mean() * 100.0))
    return pd.Series(out, index=values.index)


def old_vol_long_score(features: pd.DataFrame) -> pd.Series:
    score = pd.Series(50.0, index=features.index)
    if "iv_percentile" in features:
        score += (0.5 - features["iv_percentile"].astype(float)).fillna(0.0) * 45.0
    if "iv_minus_rv20" in features:
        score += (-features["iv_minus_rv20"].astype(float) * 180.0).clip(-20, 20).fillna(0.0)
    if "rv20_change_5d" in features:
        score += (features["rv20_change_5d"].astype(float) > 0).astype(float) * 10.0
    liquidity_ok = pd.Series(False, index=features.index)
    for column in ["call_volume", "put_volume", "option_total_open_interest"]:
        if column in features:
            liquidity_ok |= features[column].fillna(0).astype(float) > 0
    score += liquidity_ok.astype(float) * 5.0
    return _clip_score(score)


def add_score_components(feature_table: pd.DataFrame) -> pd.DataFrame:
    features = feature_table.copy()

    valuation_parts = pd.DataFrame(index=features.index)
    if "iv_minus_rv20" in features:
        valuation_parts["iv_minus_rv20"] = _linear_low_is_good(features["iv_minus_rv20"], -0.08, 0.08)
    if "iv_percentile" in features:
        valuation_parts["iv_percentile"] = (1.0 - features["iv_percentile"].astype(float)).clip(0, 1) * 100.0
    if "straddle_premium_to_spot" in features:
        valuation_parts["premium"] = _linear_low_is_good(features["straddle_premium_to_spot"], 0.02, 0.08)
    features["valuation_score"] = _row_mean(valuation_parts)

    compression_parts = pd.DataFrame(index=features.index)
    if "range_percentile_252" in features:
        compression_parts["range"] = (1.0 - features["range_percentile_252"].astype(float)).clip(0, 1) * 100.0
    if "rv5_minus_rv20" in features:
        compression_parts["rv5_minus_rv20"] = _linear_low_is_good(features["rv5_minus_rv20"], -0.06, 0.06)
    if "close_position_20d_range" in features:
        compression_parts["range_edge"] = (features["close_position_20d_range"].astype(float) - 0.5).abs().clip(0, 0.5) * 200.0
    features["compression_score"] = _row_mean(compression_parts)

    trigger_parts = pd.DataFrame(index=features.index)
    if "rv20_change_5d" in features:
        trigger_parts["rv20_change_5d"] = _linear_high_is_good(features["rv20_change_5d"], -0.05, 0.05)
    if "underlying_volume_zscore_20d" in features:
        trigger_parts["volume_z"] = _linear_high_is_good(features["underlying_volume_zscore_20d"], -1.0, 2.0)
    if "abs_ret_1d" in features:
        trigger_parts["abs_ret_1d"] = _linear_high_is_good(features["abs_ret_1d"], 0.0, 0.03)
    if "option_total_volume" in features:
        trigger_parts["option_volume"] = _expanding_percentile(features["option_total_volume"])
    features["trigger_score"] = _row_mean(trigger_parts)

    liquidity_parts = pd.DataFrame(index=features.index)
    if "call_volume" in features:
        liquidity_parts["call_volume"] = (features["call_volume"].fillna(0).astype(float) > 0).astype(float) * 100.0
    if "put_volume" in features:
        liquidity_parts["put_volume"] = (features["put_volume"].fillna(0).astype(float) > 0).astype(float) * 100.0
    if "option_total_open_interest" in features:
        liquidity_parts["oi"] = (features["option_total_open_interest"].fillna(0).astype(float) > 0).astype(float) * 100.0
    features["liquidity_score"] = _row_mean(liquidity_parts)

    features["old_vol_long_score"] = old_vol_long_score(features)
    return features

