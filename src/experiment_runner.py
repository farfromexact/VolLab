from __future__ import annotations

import numpy as np
import pandas as pd

from src.rule_filters import apply_rule


EXPERIMENT_COLUMNS = [
    "rule_name",
    "mode",
    "holding_days",
    "eligible_signal_dates",
    "trades",
    "win_rate",
    "avg_return",
    "median_return",
    "avg_net_pnl",
    "total_net_pnl",
    "max_trade_loss",
    "max_trade_profit",
    "profit_factor",
    "top_5_wins_to_total_pnl",
    "top_10pct_capture_ratio",
    "flat_ratio",
]


def _prepare_trades(trade_details: pd.DataFrame) -> pd.DataFrame:
    trades = trade_details.copy()
    for column in ["signal_date", "entry_date", "exit_date"]:
        trades[column] = pd.to_datetime(trades[column]).dt.normalize()
    return trades.sort_values(["entry_date", "exit_date", "holding_days"]).reset_index(drop=True)


def _non_overlapping(trades: pd.DataFrame) -> pd.DataFrame:
    selected = []
    last_exit_by_holding: dict[int, pd.Timestamp] = {}
    for idx, trade in trades.sort_values(["holding_days", "entry_date", "exit_date"]).iterrows():
        holding = int(trade["holding_days"])
        last_exit = last_exit_by_holding.get(holding)
        if last_exit is None or pd.Timestamp(trade["entry_date"]) > last_exit:
            selected.append(idx)
            last_exit_by_holding[holding] = pd.Timestamp(trade["exit_date"])
    return trades.loc[selected].sort_values(["entry_date", "holding_days"]).reset_index(drop=True)


def _one_position_at_a_time(trades: pd.DataFrame) -> pd.DataFrame:
    selected = []
    active_exit: pd.Timestamp | None = None
    for idx, trade in trades.sort_values(["entry_date", "exit_date", "holding_days"]).iterrows():
        entry = pd.Timestamp(trade["entry_date"])
        if active_exit is None or entry > active_exit:
            selected.append(idx)
            active_exit = pd.Timestamp(trade["exit_date"])
    return trades.loc[selected].sort_values(["entry_date", "holding_days"]).reset_index(drop=True)


def apply_execution_mode(trades: pd.DataFrame, mode: str) -> pd.DataFrame:
    mode = str(mode)
    if mode == "daily_rolling":
        return trades.copy()
    if mode == "non_overlapping":
        return _non_overlapping(trades)
    if mode == "one_position_at_a_time":
        return _one_position_at_a_time(trades)
    raise ValueError(f"Unsupported experiment mode: {mode!r}")


def _profit_factor(pnl: pd.Series) -> float:
    gains = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    if losses == 0:
        return np.inf if gains > 0 else np.nan
    return float(gains / abs(losses))


def _top_wins_share(pnl: pd.Series, n: int = 5) -> float:
    total = pnl.sum()
    if total == 0:
        return np.nan
    return float(pnl.sort_values(ascending=False).head(n).sum() / total)


def _capture_ratio(selected: pd.DataFrame, label_table: pd.DataFrame) -> float:
    if selected.empty or label_table.empty:
        return np.nan
    labels = label_table.copy()
    labels["signal_date"] = pd.to_datetime(labels["signal_date"]).dt.normalize()
    merged = selected[["signal_date", "holding_days"]].merge(labels, on="signal_date", how="left")
    captures = []
    totals = []
    for holding in sorted(selected["holding_days"].dropna().astype(int).unique()):
        field = f"is_top_10pct_straddle_return_{holding}d"
        if field not in labels.columns:
            continue
        total_events = labels[field].fillna(False).sum()
        captured = merged.loc[merged["holding_days"].astype(int) == holding, field].fillna(False).sum()
        captures.append(captured)
        totals.append(total_events)
    total = float(np.sum(totals))
    if total == 0:
        return np.nan
    return float(np.sum(captures) / total)


def summarize_selected_trades(
    selected: pd.DataFrame,
    label_table: pd.DataFrame,
    rule_name: str,
    mode: str,
    holding_days: int | str = "all",
    eligible_signal_dates: int = 0,
    total_signal_dates: int = 0,
) -> dict:
    pnl = selected["net_pnl"].astype(float) if not selected.empty else pd.Series(dtype="float64")
    returns = selected["return_on_premium"].astype(float) if not selected.empty else pd.Series(dtype="float64")
    return {
        "rule_name": rule_name,
        "mode": mode,
        "holding_days": holding_days,
        "eligible_signal_dates": int(eligible_signal_dates),
        "trades": int(len(selected)),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
        "avg_return": float(returns.mean()) if len(returns) else np.nan,
        "median_return": float(returns.median()) if len(returns) else np.nan,
        "avg_net_pnl": float(pnl.mean()) if len(pnl) else np.nan,
        "total_net_pnl": float(pnl.sum()) if len(pnl) else 0.0,
        "max_trade_loss": float(pnl.min()) if len(pnl) else np.nan,
        "max_trade_profit": float(pnl.max()) if len(pnl) else np.nan,
        "profit_factor": _profit_factor(pnl) if len(pnl) else np.nan,
        "top_5_wins_to_total_pnl": _top_wins_share(pnl) if len(pnl) else np.nan,
        "top_10pct_capture_ratio": _capture_ratio(selected, label_table),
        "flat_ratio": 1.0 - (eligible_signal_dates / total_signal_dates) if total_signal_dates else np.nan,
    }


def run_timing_experiments(
    feature_table: pd.DataFrame,
    label_table: pd.DataFrame,
    trade_details: pd.DataFrame,
    rules: list[dict],
    modes: list[str] | tuple[str, ...] = ("daily_rolling", "non_overlapping", "one_position_at_a_time"),
) -> pd.DataFrame:
    features = feature_table.copy()
    features["signal_date"] = pd.to_datetime(features["signal_date"]).dt.normalize()
    trades = _prepare_trades(trade_details)
    total_signal_dates = int(features["signal_date"].nunique())
    rows = []

    for rule in rules:
        rule_name = str(rule.get("name", "unnamed_rule"))
        eligible_features = features.loc[apply_rule(features, rule)]
        eligible_dates = set(eligible_features["signal_date"])
        eligible_count = len(eligible_dates)
        rule_trades = trades.loc[trades["signal_date"].isin(eligible_dates)].copy()

        for mode in modes:
            mode_trades = apply_execution_mode(rule_trades, mode)
            rows.append(
                summarize_selected_trades(
                    mode_trades,
                    label_table,
                    rule_name,
                    mode,
                    "all",
                    eligible_count,
                    total_signal_dates,
                )
            )
            for holding in sorted(rule_trades["holding_days"].dropna().astype(int).unique()):
                subset = apply_execution_mode(rule_trades.loc[rule_trades["holding_days"].astype(int) == holding], mode)
                rows.append(
                    summarize_selected_trades(
                        subset,
                        label_table,
                        rule_name,
                        mode,
                        int(holding),
                        eligible_count,
                        total_signal_dates,
                    )
                )

    return pd.DataFrame(rows, columns=EXPERIMENT_COLUMNS)

