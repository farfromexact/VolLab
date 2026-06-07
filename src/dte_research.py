from __future__ import annotations

import math

import numpy as np
import pandas as pd


DTE_BUCKETS = [
    ("7-10", 7, 10),
    ("10-14", 10, 14),
    ("15-21", 14, 21),
    ("22-30", 21, 30),
    ("31-45", 30, 45),
]

DTE_SUMMARY_COLUMNS = [
    "scope",
    "holding_days",
    "dte_bucket",
    "event_type",
    "post_warmup_only",
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
    "top10_capture",
    "flat_ratio",
]


def bucket_dte(value) -> str | float:
    if pd.isna(value):
        return np.nan
    dte = float(value)
    for idx, (label, lower, upper) in enumerate(DTE_BUCKETS):
        if idx == 0:
            if lower <= dte <= upper:
                return label
        elif lower < dte <= upper:
            return label
    return np.nan


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _date(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


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


def _expected_shortfall(pnl: pd.Series, percentile: float = 0.05) -> float:
    pnl = pnl.dropna().sort_values()
    if pnl.empty:
        return np.nan
    count = max(1, int(math.ceil(len(pnl) * percentile)))
    return float(pnl.head(count).mean())


def _prepare_frame(
    trade_details: pd.DataFrame,
    label_table: pd.DataFrame | None = None,
    event_classification: pd.DataFrame | None = None,
    feature_table: pd.DataFrame | None = None,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    trades = trade_details.copy()
    trades["signal_date"] = _date(trades, "signal_date")
    trades["holding_days"] = _num(trades, "holding_days").astype("Int64")
    trades = trades.loc[trades["holding_days"].isin(list(horizons))].copy()
    trades["dte_bucket"] = trades["dte"].apply(bucket_dte)
    trades["event_type"] = "unclassified"
    trades["is_iv_warmup"] = False
    trades["is_top10"] = False

    if feature_table is not None and not feature_table.empty:
        features = feature_table.copy()
        features["signal_date"] = _date(features, "signal_date")
        keep = [c for c in ["signal_date", "is_iv_warmup"] if c in features.columns]
        if len(keep) > 1:
            trades = trades.drop(columns=["is_iv_warmup"]).merge(features[keep], on="signal_date", how="left")
            trades["is_iv_warmup"] = trades["is_iv_warmup"].fillna(False).astype(bool)

    if event_classification is not None and not event_classification.empty:
        events = event_classification.copy()
        events["signal_date"] = _date(events, "signal_date")
        events["holding_days"] = _num(events, "holding_days").astype("Int64")
        trades = trades.drop(columns=["event_type"]).merge(
            events[["signal_date", "holding_days", "event_type"]],
            on=["signal_date", "holding_days"],
            how="left",
        )
        trades["event_type"] = trades["event_type"].fillna("unclassified")

    if label_table is not None and not label_table.empty:
        labels = label_table.copy()
        labels["signal_date"] = _date(labels, "signal_date")
        for holding in horizons:
            field = f"is_top_10pct_straddle_return_{holding}d"
            if field not in labels.columns:
                continue
            mapping = labels.set_index("signal_date")[field].fillna(False).astype(bool)
            mask = trades["holding_days"].astype("Int64").eq(int(holding))
            trades.loc[mask, "is_top10"] = trades.loc[mask, "signal_date"].map(mapping).fillna(False).to_numpy()
    return trades


def _summarize_subset(selected: pd.DataFrame, denominator: pd.DataFrame) -> dict:
    pnl = _num(selected, "net_pnl").dropna()
    returns = _num(selected, "return_on_premium").dropna()
    total_top10 = int(denominator["is_top10"].fillna(False).sum()) if "is_top10" in denominator else 0
    selected_top10 = int(selected["is_top10"].fillna(False).sum()) if "is_top10" in selected else 0
    eligible_signals = int(denominator["signal_date"].nunique()) if "signal_date" in denominator else 0
    selected_signals = int(selected["signal_date"].nunique()) if "signal_date" in selected else 0
    return {
        "trade_count": int(len(selected)),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
        "avg_return": float(returns.mean()) if len(returns) else np.nan,
        "median_return": float(returns.median()) if len(returns) else np.nan,
        "avg_net_pnl": float(pnl.mean()) if len(pnl) else np.nan,
        "total_net_pnl": float(pnl.sum()) if len(pnl) else 0.0,
        "max_loss": float(pnl.min()) if len(pnl) else np.nan,
        "max_win": float(pnl.max()) if len(pnl) else np.nan,
        "profit_factor": _profit_factor(pnl) if len(pnl) else np.nan,
        "top_5_wins_to_total_pnl": _top_wins_share(pnl) if len(pnl) else np.nan,
        "expected_shortfall_5pct": _expected_shortfall(pnl) if len(pnl) else np.nan,
        "top10_capture": float(selected_top10 / total_top10) if total_top10 else np.nan,
        "flat_ratio": float(1.0 - selected_signals / eligible_signals) if eligible_signals else np.nan,
    }


def run_dte_research(
    trade_details: pd.DataFrame,
    label_table: pd.DataFrame | None = None,
    event_classification: pd.DataFrame | None = None,
    feature_table: pd.DataFrame | None = None,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    frame = _prepare_frame(trade_details, label_table, event_classification, feature_table, horizons)
    rows = []
    for post_warmup_only in [False, True]:
        base = frame.loc[~frame["is_iv_warmup"].astype(bool)].copy() if post_warmup_only else frame.copy()
        for holding in horizons:
            holding_base = base.loc[base["holding_days"].astype("Int64").eq(int(holding))].copy()
            holding_base = holding_base.loc[holding_base["dte_bucket"].notna()]
            if holding_base.empty:
                continue
            for dte_bucket, selected in holding_base.groupby("dte_bucket", dropna=False, observed=False):
                row = {
                    "scope": "holding_dte",
                    "holding_days": int(holding),
                    "dte_bucket": dte_bucket,
                    "event_type": "all",
                    "post_warmup_only": bool(post_warmup_only),
                }
                row.update(_summarize_subset(selected, holding_base))
                rows.append(row)

            for (dte_bucket, event_type), selected in holding_base.groupby(
                ["dte_bucket", "event_type"], dropna=False, observed=False
            ):
                row = {
                    "scope": "holding_dte_event_type",
                    "holding_days": int(holding),
                    "dte_bucket": dte_bucket,
                    "event_type": event_type,
                    "post_warmup_only": bool(post_warmup_only),
                }
                row.update(_summarize_subset(selected, holding_base))
                rows.append(row)

    return pd.DataFrame(rows, columns=DTE_SUMMARY_COLUMNS)
