from __future__ import annotations

import numpy as np
import pandas as pd

from src.labels import build_label_table


HORIZON_LABEL_COLUMNS = [
    "signal_date",
    "forward_straddle_return_1d",
    "forward_straddle_return_3d",
    "forward_straddle_return_5d",
    "forward_straddle_net_pnl_1d",
    "forward_straddle_net_pnl_3d",
    "forward_straddle_net_pnl_5d",
    "is_top_10pct_straddle_return_1d",
    "is_top_10pct_straddle_return_3d",
    "is_top_10pct_straddle_return_5d",
    "is_top_5pct_straddle_return_1d",
    "is_top_5pct_straddle_return_3d",
    "is_top_5pct_straddle_return_5d",
    "future_abs_return_1d",
    "future_abs_return_3d",
    "future_abs_return_5d",
    "future_direction_1d",
    "future_direction_3d",
    "future_direction_5d",
    "future_gap_return_next_open",
    "future_intraday_range_1d",
    "future_rv_5d",
]


def _prepare_underlying(trade_details: pd.DataFrame, underlying_daily: pd.DataFrame | None) -> pd.DataFrame:
    if underlying_daily is not None and not underlying_daily.empty and "close" in underlying_daily.columns:
        frame = underlying_daily.copy()
        date_col = "date" if "date" in frame.columns else "signal_date"
        frame["signal_date"] = pd.to_datetime(frame[date_col]).dt.normalize()
        for column in ["open", "high", "low", "close"]:
            if column not in frame.columns:
                frame[column] = np.nan
        return frame[["signal_date", "open", "high", "low", "close"]].sort_values("signal_date").reset_index(drop=True)

    signals = (
        trade_details.copy()
        .assign(signal_date=lambda x: pd.to_datetime(x["signal_date"]).dt.normalize())
        .sort_values(["signal_date", "holding_days"])
        .drop_duplicates("signal_date")
    )
    frame = signals[["signal_date", "spot_at_signal"]].rename(columns={"spot_at_signal": "close"})
    frame["open"] = np.nan
    frame["high"] = np.nan
    frame["low"] = np.nan
    return frame[["signal_date", "open", "high", "low", "close"]].sort_values("signal_date").reset_index(drop=True)


def _future_direction(close: pd.Series, days: int) -> pd.Series:
    future_return = close.shift(-days) / close - 1.0
    return np.sign(future_return)


def build_label_table_by_horizon(
    trade_details: pd.DataFrame,
    underlying_daily: pd.DataFrame | None = None,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    if trade_details.empty:
        return pd.DataFrame(columns=HORIZON_LABEL_COLUMNS)

    labels = build_label_table(trade_details, underlying_daily=underlying_daily, holding_days=horizons)
    underlying = _prepare_underlying(trade_details, underlying_daily)
    close = pd.to_numeric(underlying["close"], errors="coerce")
    open_ = pd.to_numeric(underlying["open"], errors="coerce")
    high = pd.to_numeric(underlying["high"], errors="coerce")
    low = pd.to_numeric(underlying["low"], errors="coerce")
    by_date = pd.DataFrame({"signal_date": underlying["signal_date"]})

    for days in horizons:
        by_date[f"future_direction_{days}d"] = _future_direction(close, days)

    by_date["future_gap_return_next_open"] = open_.shift(-1) / close - 1.0
    by_date["future_intraday_range_1d"] = high.shift(-1) / low.shift(-1) - 1.0
    labels = labels.merge(by_date, on="signal_date", how="left")

    for column in HORIZON_LABEL_COLUMNS:
        if column not in labels.columns:
            labels[column] = np.nan
    return labels[HORIZON_LABEL_COLUMNS].sort_values("signal_date").reset_index(drop=True)
