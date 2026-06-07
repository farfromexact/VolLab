from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src.dte_research import bucket_dte


EXIT_POLICIES = [
    "fixed_hold_1d",
    "fixed_hold_3d",
    "fixed_hold_5d",
    "take_profit_30pct",
    "take_profit_50pct",
    "take_profit_100pct",
    "stop_loss_30pct",
    "stop_loss_50pct",
    "time_stop_1d_no_move",
    "time_stop_2d_no_move",
    "iv_stop_loss",
    "take_profit_50pct_or_stop_loss_30pct",
    "take_profit_100pct_or_stop_loss_50pct",
    "time_stop_1d_no_move_else_hold_5d",
]

EXIT_RESULT_COLUMNS = [
    "signal_date",
    "policy",
    "exit_date",
    "exit_day",
    "exit_reason",
    "return_on_premium",
    "net_pnl",
    "dte",
    "dte_bucket",
    "event_type",
]

EXIT_SUMMARY_COLUMNS = [
    "policy",
    "group",
    "group_value",
    "trade_count",
    "win_rate",
    "avg_return",
    "median_return",
    "avg_net_pnl",
    "total_net_pnl",
    "max_loss",
    "max_win",
    "profit_factor",
    "top_5_wins_to_total_pnl",
    "expected_shortfall_5pct",
    "avg_exit_day",
]


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _date(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index)
    return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


def _threshold_from_name(name: str, token: str) -> float | None:
    match = re.search(rf"{token}_(\d+)pct", name)
    if not match:
        return None
    return float(match.group(1)) / 100.0


def _fixed_days_from_name(name: str) -> int | None:
    match = re.search(r"fixed_hold_(\d+)d", name)
    if not match:
        return None
    return int(match.group(1))


def _time_stop_from_name(name: str) -> int | None:
    match = re.search(r"time_stop_(\d+)d_no_move", name)
    if not match:
        return None
    return int(match.group(1))


def _policy_params(policy: str) -> dict:
    params = {
        "fixed_days": _fixed_days_from_name(policy),
        "take_profit": _threshold_from_name(policy, "take_profit"),
        "stop_loss": _threshold_from_name(policy, "stop_loss"),
        "time_stop_day": _time_stop_from_name(policy),
        "iv_stop": policy == "iv_stop_loss",
        "max_hold_days": 5,
    }
    if policy in {"take_profit_30pct", "take_profit_50pct", "take_profit_100pct", "stop_loss_30pct", "stop_loss_50pct"}:
        params["max_hold_days"] = 5
    if policy == "time_stop_1d_no_move_else_hold_5d":
        params["time_stop_day"] = 1
        params["max_hold_days"] = 5
    return params


def _first_at_or_after(path: pd.DataFrame, day: int) -> pd.Series:
    eligible = path.loc[path["day"].astype(int) >= int(day)]
    if eligible.empty:
        return path.sort_values("day").iloc[-1]
    return eligible.sort_values("day").iloc[0]


def _return_result(path: pd.DataFrame, row: pd.Series, policy: str, reason: str, return_override=None) -> dict:
    ret = float(return_override) if return_override is not None and np.isfinite(return_override) else row.get("straddle_return", np.nan)
    notional = row.get("entry_notional", np.nan)
    if np.isfinite(ret) and np.isfinite(notional):
        net_pnl = float(ret) * float(notional)
    else:
        net_pnl = row.get("net_pnl", np.nan)
    first = path.sort_values("day").iloc[0]
    return {
        "signal_date": first.get("signal_date"),
        "policy": policy,
        "exit_date": row.get("date"),
        "exit_day": int(row.get("day")),
        "exit_reason": reason,
        "return_on_premium": ret,
        "net_pnl": net_pnl,
        "dte": first.get("dte", np.nan),
        "dte_bucket": bucket_dte(first.get("dte", np.nan)),
        "event_type": first.get("event_type", "unclassified"),
    }


def evaluate_exit_policy(path: pd.DataFrame, policy: str, config: dict | None = None) -> dict:
    if path.empty:
        raise ValueError("path is empty")
    cfg = dict((config or {}).get("event_thresholds", {}))
    no_move_threshold = float(cfg.get("no_move_return_threshold", 0.05))
    iv_stop_threshold = float(cfg.get("iv_stop_loss_vol_point", -0.03))
    params = _policy_params(policy)
    ordered = path.copy().sort_values("day").reset_index(drop=True)
    ordered["high_return"] = _num(ordered, "high_return").combine_first(_num(ordered, "straddle_return"))
    ordered["low_return"] = _num(ordered, "low_return").combine_first(_num(ordered, "straddle_return"))

    if params["fixed_days"] is not None:
        row = _first_at_or_after(ordered, params["fixed_days"])
        return _return_result(ordered, row, policy, f"fixed_hold_{params['fixed_days']}d")

    max_hold = int(params["max_hold_days"])
    take_profit = params["take_profit"]
    stop_loss = params["stop_loss"]
    time_stop_day = params["time_stop_day"]
    iv_stop = params["iv_stop"]

    for _, row in ordered.iterrows():
        day = int(row["day"])
        if day > max_hold:
            break

        stop_hit = stop_loss is not None and np.isfinite(row["low_return"]) and float(row["low_return"]) <= -stop_loss
        take_hit = take_profit is not None and np.isfinite(row["high_return"]) and float(row["high_return"]) >= take_profit
        if stop_hit:
            return _return_result(ordered, row, policy, f"stop_loss_{int(stop_loss * 100)}pct", -stop_loss)
        if take_hit:
            return _return_result(ordered, row, policy, f"take_profit_{int(take_profit * 100)}pct", take_profit)

        if iv_stop and "iv_change" in ordered.columns and np.isfinite(row.get("iv_change", np.nan)):
            if float(row["iv_change"]) <= iv_stop_threshold:
                return _return_result(ordered, row, policy, "iv_stop_loss")

        if time_stop_day is not None and day >= time_stop_day:
            ret = row.get("straddle_return", np.nan)
            if np.isfinite(ret) and abs(float(ret)) <= no_move_threshold:
                return _return_result(ordered, row, policy, f"time_stop_{time_stop_day}d_no_move")

    row = _first_at_or_after(ordered, max_hold)
    return _return_result(ordered, row, policy, f"hold_{max_hold}d")


def build_trade_paths(
    trade_details: pd.DataFrame,
    event_classification: pd.DataFrame | None = None,
    contract_multiplier: float = 100.0,
) -> dict[pd.Timestamp, pd.DataFrame]:
    trades = trade_details.copy()
    trades["signal_date"] = _date(trades, "signal_date")
    trades["date"] = _date(trades, "exit_date")
    trades["day"] = _num(trades, "holding_days").astype("Int64")
    trades["straddle_return"] = _num(trades, "return_on_premium")
    trades["high_return"] = trades["straddle_return"]
    trades["low_return"] = trades["straddle_return"]
    trades["entry_notional"] = _num(trades, "entry_premium") * float(contract_multiplier)
    trades["event_type"] = "unclassified"

    if event_classification is not None and not event_classification.empty:
        events = event_classification.copy()
        events["signal_date"] = _date(events, "signal_date")
        events["holding_days"] = _num(events, "holding_days").astype("Int64")
        trades = trades.merge(
            events[["signal_date", "holding_days", "event_type"]],
            left_on=["signal_date", "day"],
            right_on=["signal_date", "holding_days"],
            how="left",
            suffixes=("", "_event"),
        )
        trades["event_type"] = trades["event_type_event"].combine_first(trades["event_type"])
        trades = trades.drop(columns=[c for c in ["holding_days_event", "event_type_event"] if c in trades.columns])

    paths = {}
    for signal_date, path in trades.groupby("signal_date", dropna=False):
        path = path.loc[path["day"].notna()].sort_values("day")
        if not path.empty:
            paths[pd.Timestamp(signal_date).normalize()] = path
    return paths


def _profit_factor(pnl: pd.Series) -> float:
    gains = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    if losses == 0:
        return np.inf if gains > 0 else np.nan
    return float(gains / abs(losses))


def _top_wins_share(pnl: pd.Series) -> float:
    total = pnl.sum()
    if total == 0:
        return np.nan
    return float(pnl.sort_values(ascending=False).head(5).sum() / total)


def _expected_shortfall(pnl: pd.Series) -> float:
    pnl = pnl.dropna().sort_values()
    if pnl.empty:
        return np.nan
    count = max(1, int(np.ceil(len(pnl) * 0.05)))
    return float(pnl.head(count).mean())


def summarize_exit_results(results: pd.DataFrame, group: str = "all") -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame(columns=EXIT_SUMMARY_COLUMNS)
    group_cols = ["policy"] if group == "all" else ["policy", group]
    rows = []
    for keys, selected in results.groupby(group_cols, dropna=False, observed=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        policy = keys[0]
        group_value = "all" if group == "all" else keys[1]
        pnl = _num(selected, "net_pnl").dropna()
        ret = _num(selected, "return_on_premium").dropna()
        rows.append(
            {
                "policy": policy,
                "group": group,
                "group_value": group_value,
                "trade_count": int(len(selected)),
                "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
                "avg_return": float(ret.mean()) if len(ret) else np.nan,
                "median_return": float(ret.median()) if len(ret) else np.nan,
                "avg_net_pnl": float(pnl.mean()) if len(pnl) else np.nan,
                "total_net_pnl": float(pnl.sum()) if len(pnl) else 0.0,
                "max_loss": float(pnl.min()) if len(pnl) else np.nan,
                "max_win": float(pnl.max()) if len(pnl) else np.nan,
                "profit_factor": _profit_factor(pnl) if len(pnl) else np.nan,
                "top_5_wins_to_total_pnl": _top_wins_share(pnl) if len(pnl) else np.nan,
                "expected_shortfall_5pct": _expected_shortfall(pnl) if len(pnl) else np.nan,
                "avg_exit_day": float(_num(selected, "exit_day").mean()) if len(selected) else np.nan,
            }
        )
    return pd.DataFrame(rows, columns=EXIT_SUMMARY_COLUMNS)


def run_exit_policy_experiments(
    trade_details: pd.DataFrame,
    event_classification: pd.DataFrame | None = None,
    config: dict | None = None,
    policies: list[str] | tuple[str, ...] = tuple(EXIT_POLICIES),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    contract_multiplier = float((config or {}).get("contract_multiplier", 100.0))
    paths = build_trade_paths(trade_details, event_classification, contract_multiplier=contract_multiplier)
    rows = []
    for policy in policies:
        for path in paths.values():
            rows.append(evaluate_exit_policy(path, policy, config))
    results = pd.DataFrame(rows, columns=EXIT_RESULT_COLUMNS)
    summary = summarize_exit_results(results, "all")
    by_event = summarize_exit_results(results, "event_type")
    by_dte = summarize_exit_results(results, "dte_bucket")
    return results, summary, by_event, by_dte
