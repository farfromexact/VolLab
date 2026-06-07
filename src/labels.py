from __future__ import annotations

import numpy as np
import pandas as pd


LABEL_COLUMNS = [
    "signal_date",
    "forward_straddle_return_1d",
    "forward_straddle_return_2d",
    "forward_straddle_return_3d",
    "forward_straddle_return_5d",
    "forward_straddle_net_pnl_1d",
    "forward_straddle_net_pnl_2d",
    "forward_straddle_net_pnl_3d",
    "forward_straddle_net_pnl_5d",
    "future_abs_return_1d",
    "future_abs_return_3d",
    "future_abs_return_5d",
    "future_rv_5d",
    "is_top_10pct_straddle_return_1d",
    "is_top_10pct_straddle_return_3d",
    "is_top_10pct_straddle_return_5d",
    "is_top_5pct_straddle_return_1d",
    "is_top_5pct_straddle_return_3d",
    "is_top_5pct_straddle_return_5d",
]


def _prepare_signal_close(trade_details: pd.DataFrame, underlying_daily: pd.DataFrame | None = None) -> pd.DataFrame:
    signals = (
        trade_details.copy()
        .assign(signal_date=lambda x: pd.to_datetime(x["signal_date"]).dt.normalize())
        .sort_values(["signal_date", "holding_days"])
        .drop_duplicates("signal_date")
    )
    base = signals[["signal_date", "spot_at_signal"]].rename(columns={"spot_at_signal": "close"})

    if underlying_daily is None or underlying_daily.empty or "close" not in underlying_daily.columns:
        return base.sort_values("signal_date").reset_index(drop=True)

    underlying = underlying_daily.copy()
    date_col = "date" if "date" in underlying.columns else "signal_date"
    underlying["signal_date"] = pd.to_datetime(underlying[date_col]).dt.normalize()
    return underlying[["signal_date", "close"]].sort_values("signal_date").reset_index(drop=True)


def _future_abs_return(close: pd.Series, periods: int) -> pd.Series:
    return (close.shift(-periods) / close - 1.0).abs()


def _future_rv(close: pd.Series, window: int = 5, annualization: int = 252) -> pd.Series:
    log_ret = np.log(close.shift(-1) / close)
    values = []
    for idx in range(len(close)):
        future = log_ret.iloc[idx : idx + window].dropna()
        if len(future) < window:
            values.append(np.nan)
        else:
            values.append(float(future.std(ddof=1) * np.sqrt(annualization)))
    return pd.Series(values, index=close.index)


def build_label_table(
    trade_details: pd.DataFrame,
    underlying_daily: pd.DataFrame | None = None,
    holding_days: list[int] | tuple[int, ...] = (1, 2, 3, 5),
) -> pd.DataFrame:
    if trade_details.empty:
        return pd.DataFrame(columns=LABEL_COLUMNS)

    trades = trade_details.copy()
    trades["signal_date"] = pd.to_datetime(trades["signal_date"]).dt.normalize()
    labels = trades[["signal_date"]].drop_duplicates().sort_values("signal_date").reset_index(drop=True)

    for days in holding_days:
        subset = trades.loc[trades["holding_days"].astype(int) == int(days)]
        values = subset.set_index("signal_date")
        labels[f"forward_straddle_return_{days}d"] = labels["signal_date"].map(values["return_on_premium"])
        labels[f"forward_straddle_net_pnl_{days}d"] = labels["signal_date"].map(values["net_pnl"])

    close_frame = _prepare_signal_close(trades, underlying_daily)
    close = close_frame["close"].astype(float)
    close_by_date = close_frame.assign(close=close).set_index("signal_date")["close"]
    aligned_close = labels["signal_date"].map(close_by_date)
    for days in [1, 3, 5]:
        temp = pd.DataFrame({"signal_date": close_frame["signal_date"], "close": close})
        temp[f"future_abs_return_{days}d"] = _future_abs_return(temp["close"], days)
        labels[f"future_abs_return_{days}d"] = labels["signal_date"].map(
            temp.set_index("signal_date")[f"future_abs_return_{days}d"]
        )
    temp = pd.DataFrame({"signal_date": close_frame["signal_date"], "close": close})
    temp["future_rv_5d"] = _future_rv(temp["close"], 5)
    labels["future_rv_5d"] = labels["signal_date"].map(temp.set_index("signal_date")["future_rv_5d"])

    for days in [1, 3, 5]:
        return_col = f"forward_straddle_return_{days}d"
        if return_col not in labels.columns:
            labels[return_col] = np.nan
            labels[f"forward_straddle_net_pnl_{days}d"] = np.nan
        returns = labels[return_col]
        if returns.notna().any():
            q90 = returns.quantile(0.90)
            q95 = returns.quantile(0.95)
            labels[f"is_top_10pct_straddle_return_{days}d"] = returns >= q90
            labels[f"is_top_5pct_straddle_return_{days}d"] = returns >= q95
        else:
            labels[f"is_top_10pct_straddle_return_{days}d"] = False
            labels[f"is_top_5pct_straddle_return_{days}d"] = False

    for column in LABEL_COLUMNS:
        if column not in labels.columns:
            labels[column] = np.nan
    return labels[LABEL_COLUMNS].sort_values("signal_date").reset_index(drop=True)
