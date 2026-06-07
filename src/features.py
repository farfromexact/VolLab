from __future__ import annotations

import logging
from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.vol_metrics import iv_percentile, iv_rank, realized_vol

logger = logging.getLogger(__name__)


FEATURE_COLUMNS = [
    "signal_date",
    "atm_iv",
    "rv5",
    "rv10",
    "rv20",
    "rv60",
    "iv_minus_rv20",
    "iv_rank",
    "iv_percentile",
    "iv_zscore_252",
    "winsorized_iv_rank_252",
    "iv_lookback_count",
    "is_iv_warmup",
    "rv5_minus_rv20",
    "rv20_change_5d",
    "rv20_change_10d",
    "rv20_percentile_252",
    "ret_1d",
    "ret_3d",
    "ret_5d",
    "abs_ret_1d",
    "abs_ret_5d",
    "high_low_range_5d",
    "high_low_range_10d",
    "range_percentile_252",
    "close_position_20d_range",
    "distance_to_20d_high",
    "distance_to_20d_low",
    "underlying_volume_zscore_20d",
    "option_total_volume",
    "option_total_open_interest",
    "call_volume",
    "put_volume",
    "put_call_volume_ratio",
    "put_call_oi_ratio",
    "signal_call_close",
    "signal_put_close",
    "signal_call_volume",
    "signal_put_volume",
    "signal_call_open_interest",
    "signal_put_open_interest",
    "signal_straddle_close",
    "signal_straddle_premium_to_spot",
    "entry_call_open",
    "entry_put_open",
    "entry_straddle_open",
    "exit_call_close",
    "exit_put_close",
    "exit_straddle_close",
    "signal_call_bid",
    "signal_call_ask",
    "signal_put_bid",
    "signal_put_ask",
    "call_bid_ask_spread",
    "put_bid_ask_spread",
    "dte",
    "strike",
    "straddle_close_price",
    "straddle_premium_to_spot",
    "call_close",
    "put_close",
]

OPTION_SNAPSHOT_COLUMNS = [
    "signal_call_close",
    "signal_put_close",
    "signal_call_volume",
    "signal_put_volume",
    "signal_call_open_interest",
    "signal_put_open_interest",
    "signal_straddle_close",
    "signal_straddle_premium_to_spot",
    "entry_call_open",
    "entry_put_open",
    "entry_straddle_open",
    "exit_call_close",
    "exit_put_close",
    "exit_straddle_close",
    "signal_call_bid",
    "signal_call_ask",
    "signal_put_bid",
    "signal_put_ask",
    "call_bid_ask_spread",
    "put_bid_ask_spread",
    "option_total_volume",
    "option_total_open_interest",
    "call_volume",
    "put_volume",
    "put_call_volume_ratio",
    "put_call_oi_ratio",
    "straddle_close_price",
    "straddle_premium_to_spot",
    "call_close",
    "put_close",
]


def _date_column(frame: pd.DataFrame, preferred: str) -> str:
    if preferred in frame.columns:
        return preferred
    if "date" in frame.columns:
        return "date"
    raise ValueError(f"Missing date column: {preferred!r}")


def _prepare_signal_rows(trade_details: pd.DataFrame) -> pd.DataFrame:
    if trade_details.empty:
        return pd.DataFrame(columns=["signal_date"])
    required = ["signal_date", "holding_days"]
    missing = [column for column in required if column not in trade_details.columns]
    if missing:
        raise ValueError(f"trade_details is missing required columns: {missing}")
    rows = trade_details.copy()
    rows["signal_date"] = pd.to_datetime(rows["signal_date"]).dt.normalize()
    rows = rows.sort_values(["signal_date", "holding_days"])
    return rows.drop_duplicates("signal_date", keep="first").reset_index(drop=True)


def _prepare_underlying(trade_signals: pd.DataFrame, underlying_daily: pd.DataFrame | None = None) -> pd.DataFrame:
    if underlying_daily is not None and not underlying_daily.empty:
        date_col = _date_column(underlying_daily, "date")
        underlying = underlying_daily.copy()
        underlying["signal_date"] = pd.to_datetime(underlying[date_col]).dt.normalize()
        rename = {}
        for column in ["open", "high", "low", "close", "volume"]:
            if column in underlying.columns:
                rename[column] = column
        keep = ["signal_date", *rename.keys()]
        return underlying[keep].rename(columns=rename).sort_values("signal_date").reset_index(drop=True)

    logger.warning("underlying_daily is missing; using spot_at_signal as close-only proxy.")
    base = trade_signals[["signal_date", "spot_at_signal"]].copy()
    base = base.rename(columns={"spot_at_signal": "close"})
    for column in ["open", "high", "low", "volume"]:
        base[column] = np.nan
    return base[["signal_date", "open", "high", "low", "close", "volume"]]


def _rolling_percentile(series: pd.Series, lookback: int) -> pd.Series:
    values = pd.Series(series, dtype="float64")

    def percentile(window: np.ndarray) -> float:
        current = window[-1]
        valid = window[np.isfinite(window)]
        if len(valid) < lookback or not np.isfinite(current):
            return np.nan
        return float(np.mean(valid < current))

    return values.rolling(window=lookback, min_periods=lookback).apply(percentile, raw=True)


def _rolling_zscore(series: pd.Series, lookback: int) -> pd.Series:
    values = pd.Series(series, dtype="float64")
    mean = values.rolling(lookback, min_periods=lookback).mean()
    std = values.rolling(lookback, min_periods=lookback).std(ddof=1)
    return (values - mean) / std.replace(0, np.nan)


def _winsorized_iv_rank(iv: pd.Series, lookback: int = 252, lower_q: float = 0.05, upper_q: float = 0.95) -> pd.Series:
    values = pd.Series(iv, dtype="float64")

    def rank_window(window: np.ndarray) -> float:
        current = window[-1]
        valid = window[np.isfinite(window)]
        if len(valid) < lookback or not np.isfinite(current):
            return np.nan
        low = float(np.quantile(valid, lower_q))
        high = float(np.quantile(valid, upper_q))
        if high == low:
            return np.nan
        clipped_current = float(np.clip(current, low, high))
        return (clipped_current - low) / (high - low)

    return values.rolling(lookback, min_periods=lookback).apply(rank_window, raw=True)


def _past_return(close: pd.Series, days: int) -> pd.Series:
    return close.astype(float) / close.astype(float).shift(days) - 1.0


def _range_percentile(range_series: pd.Series, lookback: int = 252) -> pd.Series:
    return _rolling_percentile(range_series, lookback)


def _merge_option_snapshot(features: pd.DataFrame, option_snapshot: pd.DataFrame | None) -> pd.DataFrame:
    output = features.copy()
    for column in OPTION_SNAPSHOT_COLUMNS:
        output[column] = np.nan

    if option_snapshot is None or option_snapshot.empty:
        logger.warning("option_snapshot is missing; option liquidity and signal close features are NaN.")
        return output

    snap = option_snapshot.copy()
    snap["signal_date"] = pd.to_datetime(snap["signal_date"]).dt.normalize()
    for column in OPTION_SNAPSHOT_COLUMNS:
        if column not in snap.columns:
            snap[column] = np.nan
    output = output.drop(columns=OPTION_SNAPSHOT_COLUMNS).merge(
        snap[["signal_date", *OPTION_SNAPSHOT_COLUMNS]],
        on="signal_date",
        how="left",
    )
    return output


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _option_snapshot_from_trades(trade_details: pd.DataFrame) -> pd.DataFrame:
    if trade_details.empty:
        return pd.DataFrame(columns=["signal_date", *OPTION_SNAPSHOT_COLUMNS])

    rows = trade_details.copy()
    rows["signal_date"] = pd.to_datetime(rows["signal_date"]).dt.normalize()
    rows = rows.sort_values(["signal_date", "holding_days"]).drop_duplicates("signal_date", keep="first")
    snapshot = pd.DataFrame({"signal_date": rows["signal_date"]}, index=rows.index)

    for column in OPTION_SNAPSHOT_COLUMNS:
        snapshot[column] = _numeric(rows, column)

    if snapshot["entry_call_open"].isna().all() and "entry_mode_used" in rows.columns:
        next_open = rows["entry_mode_used"].astype(str).str.lower().eq("next_open")
        snapshot.loc[next_open, "entry_call_open"] = _numeric(rows, "entry_call_price").loc[next_open]
        snapshot.loc[next_open, "entry_put_open"] = _numeric(rows, "entry_put_price").loc[next_open]
    if snapshot["exit_call_close"].isna().all():
        snapshot["exit_call_close"] = _numeric(rows, "exit_call_price")
    if snapshot["exit_put_close"].isna().all():
        snapshot["exit_put_close"] = _numeric(rows, "exit_put_price")

    if snapshot["entry_straddle_open"].isna().all():
        snapshot["entry_straddle_open"] = snapshot["entry_call_open"] + snapshot["entry_put_open"]
    if snapshot["exit_straddle_close"].isna().all():
        snapshot["exit_straddle_close"] = snapshot["exit_call_close"] + snapshot["exit_put_close"]
    if snapshot["signal_straddle_close"].isna().all():
        snapshot["signal_straddle_close"] = snapshot["signal_call_close"] + snapshot["signal_put_close"]
    if snapshot["signal_straddle_premium_to_spot"].isna().all():
        spot = _numeric(rows, "spot_at_signal").replace(0, np.nan)
        snapshot["signal_straddle_premium_to_spot"] = snapshot["signal_straddle_close"] / spot

    if snapshot["call_bid_ask_spread"].isna().all():
        snapshot["call_bid_ask_spread"] = snapshot["signal_call_ask"] - snapshot["signal_call_bid"]
    if snapshot["put_bid_ask_spread"].isna().all():
        snapshot["put_bid_ask_spread"] = snapshot["signal_put_ask"] - snapshot["signal_put_bid"]

    snapshot["call_volume"] = snapshot["call_volume"].combine_first(snapshot["signal_call_volume"])
    snapshot["put_volume"] = snapshot["put_volume"].combine_first(snapshot["signal_put_volume"])
    snapshot["option_total_volume"] = snapshot["option_total_volume"].combine_first(
        snapshot["call_volume"] + snapshot["put_volume"]
    )
    total_oi = snapshot["signal_call_open_interest"] + snapshot["signal_put_open_interest"]
    snapshot["option_total_open_interest"] = snapshot["option_total_open_interest"].combine_first(total_oi)
    snapshot["put_call_volume_ratio"] = snapshot["put_call_volume_ratio"].combine_first(
        snapshot["put_volume"] / snapshot["call_volume"].replace(0, np.nan)
    )
    snapshot["put_call_oi_ratio"] = snapshot["put_call_oi_ratio"].combine_first(
        snapshot["signal_put_open_interest"] / snapshot["signal_call_open_interest"].replace(0, np.nan)
    )
    snapshot["call_close"] = snapshot["call_close"].combine_first(snapshot["signal_call_close"])
    snapshot["put_close"] = snapshot["put_close"].combine_first(snapshot["signal_put_close"])
    snapshot["straddle_close_price"] = snapshot["straddle_close_price"].combine_first(snapshot["signal_straddle_close"])
    snapshot["straddle_premium_to_spot"] = snapshot["straddle_premium_to_spot"].combine_first(
        snapshot["signal_straddle_premium_to_spot"]
    )

    return snapshot[["signal_date", *OPTION_SNAPSHOT_COLUMNS]].reset_index(drop=True)


def build_feature_table(
    trade_details: pd.DataFrame,
    underlying_daily: pd.DataFrame | None = None,
    option_snapshot: pd.DataFrame | None = None,
    rv_windows: Iterable[int] = (5, 10, 20, 60),
    iv_lookback: int = 252,
) -> pd.DataFrame:
    """Build one point-in-time feature row per signal_date.

    All calculations use only data available on or before signal_date. Forward
    outcomes belong in labels, not here.
    """

    signal_rows = _prepare_signal_rows(trade_details)
    if signal_rows.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    underlying = _prepare_underlying(signal_rows, underlying_daily)
    frame = underlying.merge(
        signal_rows[
            [
                "signal_date",
                "spot_at_signal",
                "atm_iv",
                "rv20",
                "iv_rank",
                "iv_percentile",
                "iv_minus_rv20",
                "dte",
                "strike",
            ]
        ],
        on="signal_date",
        how="right",
    ).sort_values("signal_date")

    if "close" not in frame or frame["close"].isna().all():
        frame["close"] = frame["spot_at_signal"]

    close = frame["close"].astype(float)
    for window in rv_windows:
        frame[f"rv{int(window)}"] = realized_vol(close, int(window)).to_numpy()
    if "rv20" in signal_rows.columns:
        frame["rv20"] = frame["rv20"].combine_first(signal_rows.drop_duplicates("signal_date").set_index("signal_date")["rv20"].reindex(frame["signal_date"]).reset_index(drop=True))

    atm_iv = frame["atm_iv"].astype(float)
    frame["iv_minus_rv20"] = atm_iv - frame["rv20"].astype(float)
    frame["iv_rank"] = iv_rank(atm_iv, lookback=iv_lookback).to_numpy()
    frame["iv_percentile"] = iv_percentile(atm_iv, lookback=iv_lookback).to_numpy()
    frame["iv_zscore_252"] = _rolling_zscore(atm_iv, iv_lookback).to_numpy()
    frame["winsorized_iv_rank_252"] = _winsorized_iv_rank(atm_iv, iv_lookback).to_numpy()
    frame["iv_lookback_count"] = atm_iv.rolling(iv_lookback, min_periods=1).count().to_numpy()
    frame["is_iv_warmup"] = frame["iv_lookback_count"] < iv_lookback

    frame["rv5_minus_rv20"] = frame["rv5"] - frame["rv20"]
    frame["rv20_change_5d"] = frame["rv20"] - frame["rv20"].shift(5)
    frame["rv20_change_10d"] = frame["rv20"] - frame["rv20"].shift(10)
    frame["rv20_percentile_252"] = _rolling_percentile(frame["rv20"], iv_lookback).to_numpy()

    for days in [1, 3, 5]:
        frame[f"ret_{days}d"] = _past_return(close, days)
    frame["abs_ret_1d"] = frame["ret_1d"].abs()
    frame["abs_ret_5d"] = frame["ret_5d"].abs()

    if {"high", "low"}.issubset(frame.columns) and not frame[["high", "low"]].isna().all().all():
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        range_5 = high.rolling(5, min_periods=5).max() / low.rolling(5, min_periods=5).min() - 1.0
        range_10 = high.rolling(10, min_periods=10).max() / low.rolling(10, min_periods=10).min() - 1.0
        high20 = high.rolling(20, min_periods=20).max()
        low20 = low.rolling(20, min_periods=20).min()
        denom = (high20 - low20).replace(0, np.nan)
        frame["high_low_range_5d"] = range_5
        frame["high_low_range_10d"] = range_10
        frame["range_percentile_252"] = _range_percentile(range_5, iv_lookback)
        frame["close_position_20d_range"] = (close - low20) / denom
        frame["distance_to_20d_high"] = close / high20 - 1.0
        frame["distance_to_20d_low"] = close / low20 - 1.0
    else:
        logger.warning("underlying high/low is missing; range features are NaN.")
        for column in [
            "high_low_range_5d",
            "high_low_range_10d",
            "range_percentile_252",
            "close_position_20d_range",
            "distance_to_20d_high",
            "distance_to_20d_low",
        ]:
            frame[column] = np.nan

    if "volume" in frame.columns and not frame["volume"].isna().all():
        volume = frame["volume"].astype(float)
        vol_mean = volume.rolling(20, min_periods=20).mean()
        vol_std = volume.rolling(20, min_periods=20).std(ddof=1)
        frame["underlying_volume_zscore_20d"] = (volume - vol_mean) / vol_std.replace(0, np.nan)
    else:
        logger.warning("underlying volume is missing; volume z-score is NaN.")
        frame["underlying_volume_zscore_20d"] = np.nan

    if option_snapshot is None:
        option_snapshot = _option_snapshot_from_trades(signal_rows)
    frame = _merge_option_snapshot(frame, option_snapshot)

    for column in FEATURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame[FEATURE_COLUMNS].sort_values("signal_date").reset_index(drop=True)

