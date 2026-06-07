from __future__ import annotations

import numpy as np
import pandas as pd


EVENT_TYPES = [
    "down_shock",
    "up_shock",
    "gap_event",
    "trend_vol_expansion",
    "iv_expansion_event",
    "iv_crush_event",
    "noise_theta_decay",
]

EVENT_COLUMNS = [
    "signal_date",
    "holding_days",
    "event_type",
    "classification_reason",
    "future_index_return",
    "future_abs_return",
    "future_gap_return_next_open",
    "future_rv_5d",
    "signal_rv20",
    "rv_expansion_ratio",
    "call_leg_pnl",
    "put_leg_pnl",
    "straddle_return",
    "iv_change",
]


def event_thresholds(config: dict | None = None) -> dict:
    raw = dict((config or {}).get("event_thresholds", {}))
    return {
        "shock_return_threshold": float(raw.get("shock_return_threshold", 0.025)),
        "gap_threshold": float(raw.get("gap_threshold", 0.012)),
        "rv_expansion_threshold": float(raw.get("rv_expansion_threshold", 1.2)),
        "iv_expansion_vol_point": float(raw.get("iv_expansion_vol_point", 0.03)),
        "iv_crush_vol_point": float(raw.get("iv_crush_vol_point", -0.03)),
        "leg_pnl_dominance_ratio": float(raw.get("leg_pnl_dominance_ratio", 1.2)),
        "theta_decay_abs_return_threshold": float(raw.get("theta_decay_abs_return_threshold", 0.01)),
    }


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _date(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


def _leg_pnl(trades: pd.DataFrame, side: str) -> pd.Series:
    entry_col = f"entry_{side}_open"
    exit_col = f"exit_{side}_close"
    legacy_entry = f"entry_{side}_price"
    legacy_exit = f"exit_{side}_price"
    entry = _num(trades, entry_col).combine_first(_num(trades, legacy_entry))
    exit_ = _num(trades, exit_col).combine_first(_num(trades, legacy_exit))
    return exit_ - entry


def _merge_labels(trades: pd.DataFrame, label_table: pd.DataFrame) -> pd.DataFrame:
    if label_table is None or label_table.empty:
        return trades.copy()
    labels = label_table.copy()
    labels["signal_date"] = _date(labels, "signal_date")
    merged = trades.copy()
    for holding in sorted(merged["holding_days"].dropna().astype(int).unique()):
        mask = merged["holding_days"].astype(int).eq(int(holding))
        fields = [
            "signal_date",
            f"future_abs_return_{holding}d",
            f"future_direction_{holding}d",
            "future_gap_return_next_open",
            "future_rv_5d",
        ]
        available = [field for field in fields if field in labels.columns]
        if len(available) <= 1:
            continue
        subset = labels[available].rename(
            columns={
                f"future_abs_return_{holding}d": "future_abs_return",
                f"future_direction_{holding}d": "future_direction",
            }
        )
        merged_part = merged.loc[mask, ["signal_date"]].merge(subset, on="signal_date", how="left")
        for column in [c for c in subset.columns if c != "signal_date"]:
            merged.loc[mask, column] = merged_part[column].to_numpy()
    return merged


def _merge_features(trades: pd.DataFrame, feature_table: pd.DataFrame | None) -> pd.DataFrame:
    if feature_table is None or feature_table.empty:
        trades["signal_rv20"] = _num(trades, "rv20")
        return trades
    features = feature_table.copy()
    features["signal_date"] = _date(features, "signal_date")
    keep = ["signal_date"]
    rename = {}
    if "rv20" in features.columns:
        keep.append("rv20")
        rename["rv20"] = "signal_rv20"
    if "is_iv_warmup" in features.columns:
        keep.append("is_iv_warmup")
    output = trades.merge(features[keep].rename(columns=rename), on="signal_date", how="left")
    output["signal_rv20"] = output["signal_rv20"].combine_first(_num(output, "rv20"))
    return output


def classify_event_row(row: pd.Series, thresholds: dict) -> tuple[str, str]:
    shock = thresholds["shock_return_threshold"]
    gap = thresholds["gap_threshold"]
    rv_expansion = thresholds["rv_expansion_threshold"]
    iv_expansion = thresholds["iv_expansion_vol_point"]
    iv_crush = thresholds["iv_crush_vol_point"]
    dominance = thresholds["leg_pnl_dominance_ratio"]
    theta_abs = thresholds["theta_decay_abs_return_threshold"]

    future_return = row.get("future_index_return", np.nan)
    future_abs = row.get("future_abs_return", np.nan)
    gap_return = row.get("future_gap_return_next_open", np.nan)
    rv_ratio = row.get("rv_expansion_ratio", np.nan)
    call_pnl = row.get("call_leg_pnl", np.nan)
    put_pnl = row.get("put_leg_pnl", np.nan)
    straddle_return = row.get("straddle_return", np.nan)
    iv_change = row.get("iv_change", np.nan)

    if np.isfinite(gap_return) and abs(float(gap_return)) >= gap:
        return "gap_event", "next-open gap exceeded threshold"

    call_ref = max(abs(float(call_pnl)), 1e-12) if np.isfinite(call_pnl) else np.nan
    put_ref = max(abs(float(put_pnl)), 1e-12) if np.isfinite(put_pnl) else np.nan
    if (
        np.isfinite(future_return)
        and float(future_return) <= -shock
        and np.isfinite(put_pnl)
        and float(put_pnl) > 0
        and (not np.isfinite(call_ref) or float(put_pnl) >= dominance * call_ref)
    ):
        return "down_shock", "negative future return with dominant put leg"
    if (
        np.isfinite(future_return)
        and float(future_return) >= shock
        and np.isfinite(call_pnl)
        and float(call_pnl) > 0
        and (not np.isfinite(put_ref) or float(call_pnl) >= dominance * put_ref)
    ):
        return "up_shock", "positive future return with dominant call leg"

    if np.isfinite(iv_change) and float(iv_change) >= iv_expansion:
        return "iv_expansion_event", "exit ATM IV rose from entry"
    if (
        np.isfinite(iv_change)
        and float(iv_change) <= iv_crush
        and (not np.isfinite(straddle_return) or float(straddle_return) <= 0)
    ):
        return "iv_crush_event", "ATM IV fell and straddle return was weak"

    if np.isfinite(rv_ratio) and float(rv_ratio) >= rv_expansion:
        return "trend_vol_expansion", "future RV expanded versus signal RV20"
    if np.isfinite(future_abs) and float(future_abs) >= shock:
        return "trend_vol_expansion", "large future move without single-leg shock dominance"
    if (
        (np.isfinite(future_abs) and float(future_abs) <= theta_abs)
        or (np.isfinite(straddle_return) and float(straddle_return) <= 0)
    ):
        return "noise_theta_decay", "muted realized move or negative straddle return"
    return "noise_theta_decay", "default muted/noise bucket"


def classify_events(
    trade_details: pd.DataFrame,
    label_table: pd.DataFrame | None = None,
    feature_table: pd.DataFrame | None = None,
    config: dict | None = None,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    if trade_details.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    trades = trade_details.copy()
    trades["signal_date"] = _date(trades, "signal_date")
    trades["holding_days"] = _num(trades, "holding_days").astype("Int64")
    trades = trades.loc[trades["holding_days"].isin(list(horizons))].copy()
    if trades.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    trades = _merge_labels(trades, label_table if label_table is not None else pd.DataFrame())
    trades = _merge_features(trades, feature_table)
    trades["future_index_return"] = _num(trades, "future_direction") * _num(trades, "future_abs_return")
    trades["call_leg_pnl"] = _leg_pnl(trades, "call")
    trades["put_leg_pnl"] = _leg_pnl(trades, "put")
    trades["straddle_return"] = _num(trades, "return_on_premium")
    trades["rv_expansion_ratio"] = _num(trades, "future_rv_5d") / _num(trades, "signal_rv20").replace(0, np.nan)

    if "exit_atm_iv" in trades.columns:
        trades["iv_change"] = _num(trades, "exit_atm_iv") - _num(trades, "atm_iv")
    else:
        trades["iv_change"] = np.nan

    thresholds = event_thresholds(config)
    classified = [classify_event_row(row, thresholds) for _, row in trades.iterrows()]
    trades["event_type"] = [item[0] for item in classified]
    trades["classification_reason"] = [item[1] for item in classified]

    for column in EVENT_COLUMNS:
        if column not in trades.columns:
            trades[column] = np.nan
    return trades[EVENT_COLUMNS].sort_values(["signal_date", "holding_days"]).reset_index(drop=True)


def summarize_event_types(events: pd.DataFrame, trade_details: pd.DataFrame | None = None) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(
            columns=[
                "event_type",
                "holding_days",
                "trade_count",
                "win_rate",
                "avg_return",
                "median_return",
                "max_loss",
                "max_win",
            ]
        )
    frame = events.copy()
    if trade_details is not None and not trade_details.empty and "return_on_premium" not in frame.columns:
        trades = trade_details.copy()
        trades["signal_date"] = _date(trades, "signal_date")
        trades["holding_days"] = _num(trades, "holding_days").astype("Int64")
        frame = frame.merge(
            trades[["signal_date", "holding_days", "return_on_premium", "net_pnl"]],
            on=["signal_date", "holding_days"],
            how="left",
        )
    pnl = _num(frame, "net_pnl")
    ret = _num(frame, "return_on_premium").combine_first(_num(frame, "straddle_return"))
    frame = frame.assign(_pnl=pnl, _ret=ret)
    grouped = frame.groupby(["event_type", "holding_days"], dropna=False, observed=False)
    return grouped.agg(
        trade_count=("signal_date", "size"),
        win_rate=("_pnl", lambda x: float((x > 0).mean()) if len(x) else np.nan),
        avg_return=("_ret", "mean"),
        median_return=("_ret", "median"),
        max_loss=("_pnl", "min"),
        max_win=("_pnl", "max"),
    ).reset_index()
