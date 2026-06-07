from __future__ import annotations

import numpy as np
import pandas as pd


EVENT_COLUMNS = [
    "event_date",
    "event_type",
    "daily_pnl",
    "trade_pnl",
    "contributing_trades",
    "signal_dates",
    "holding_days",
    "spot_return_before_event",
    "spot_return_on_event",
    "atm_iv_before_event",
    "rv20_before_event",
    "iv_minus_rv20_before_event",
    "range_percentile_before_event",
    "dte",
    "straddle_premium_to_spot",
    "old_vol_long_score",
]


def _prepare_dates(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in ["signal_date", "entry_date", "exit_date", "event_date"]:
        if column in output.columns:
            output[column] = pd.to_datetime(output[column]).dt.normalize()
    return output


def _feature_before(feature_table: pd.DataFrame, event_date: pd.Timestamp) -> pd.Series:
    features = _prepare_dates(feature_table).sort_values("signal_date")
    eligible = features.loc[features["signal_date"] <= event_date]
    if eligible.empty:
        return pd.Series(dtype="float64")
    return eligible.iloc[-1]


def _join_values(values) -> str:
    return "|".join(str(value) for value in sorted(pd.Series(values).dropna().astype(str).unique()))


def _event_record(
    event_date: pd.Timestamp,
    event_type: str,
    feature_table: pd.DataFrame,
    trades: pd.DataFrame,
    daily_pnl: float = np.nan,
    trade_pnl: float = np.nan,
) -> dict:
    before = _feature_before(feature_table, event_date)
    contributing = trades.loc[trades["exit_date"] == event_date]
    return {
        "event_date": event_date,
        "event_type": event_type,
        "daily_pnl": daily_pnl,
        "trade_pnl": trade_pnl,
        "contributing_trades": int(len(contributing)),
        "signal_dates": _join_values(contributing["signal_date"].dt.date if not contributing.empty else []),
        "holding_days": _join_values(contributing["holding_days"] if not contributing.empty else []),
        "spot_return_before_event": before.get("ret_5d", np.nan),
        "spot_return_on_event": before.get("ret_1d", np.nan),
        "atm_iv_before_event": before.get("atm_iv", np.nan),
        "rv20_before_event": before.get("rv20", np.nan),
        "iv_minus_rv20_before_event": before.get("iv_minus_rv20", np.nan),
        "range_percentile_before_event": before.get("range_percentile_252", np.nan),
        "dte": before.get("dte", np.nan),
        "straddle_premium_to_spot": before.get("straddle_premium_to_spot", np.nan),
        "old_vol_long_score": before.get("old_vol_long_score", np.nan),
    }


def event_windows(feature_table: pd.DataFrame, events: pd.DataFrame, pre: int = 10, post: int = 5) -> pd.DataFrame:
    features = _prepare_dates(feature_table).sort_values("signal_date").reset_index(drop=True)
    event_rows = []
    for _, event in _prepare_dates(events).iterrows():
        event_date = pd.Timestamp(event["event_date"])
        if event_date not in set(features["signal_date"]):
            anchor_candidates = features.index[features["signal_date"] <= event_date]
            if len(anchor_candidates) == 0:
                continue
            anchor_idx = int(anchor_candidates[-1])
        else:
            anchor_idx = int(features.index[features["signal_date"] == event_date][0])
        window = features.iloc[max(0, anchor_idx - pre) : min(len(features), anchor_idx + post + 1)].copy()
        window["event_date"] = event_date
        window["event_type"] = event["event_type"]
        window["relative_day"] = range(-min(pre, anchor_idx), -min(pre, anchor_idx) + len(window))
        event_rows.append(window)
    if not event_rows:
        return pd.DataFrame()
    return pd.concat(event_rows, ignore_index=True)


def top_daily_pnl_events(trade_details: pd.DataFrame, feature_table: pd.DataFrame, top_n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = _prepare_dates(trade_details)
    daily = trades.groupby("exit_date", as_index=False)["net_pnl"].sum().rename(
        columns={"exit_date": "event_date", "net_pnl": "daily_pnl"}
    )
    daily = daily.sort_values("daily_pnl", ascending=False).head(top_n)
    rows = [
        _event_record(pd.Timestamp(row["event_date"]), "top_daily_pnl", feature_table, trades, daily_pnl=float(row["daily_pnl"]))
        for _, row in daily.iterrows()
    ]
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    return events, event_windows(feature_table, events)


def top_trade_events(trade_details: pd.DataFrame, feature_table: pd.DataFrame, top_n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = _prepare_dates(trade_details)
    top = trades.sort_values("net_pnl", ascending=False).head(top_n)
    rows = []
    for _, trade in top.iterrows():
        rows.append(
            _event_record(
                pd.Timestamp(trade["exit_date"]),
                "top_single_trade",
                feature_table,
                trades,
                trade_pnl=float(trade["net_pnl"]),
            )
        )
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    return events, event_windows(feature_table, events)

