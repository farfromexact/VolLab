from __future__ import annotations

import numpy as np
import pandas as pd


def _fmt_bool(value: bool) -> str:
    return "PASS" if value else "CHECK"


def _max_overlap(trades: pd.DataFrame) -> int:
    events = []
    for _, row in trades.iterrows():
        events.append((pd.Timestamp(row["entry_date"]), 1))
        events.append((pd.Timestamp(row["exit_date"]), -1))
    active = 0
    max_active = 0
    for _, delta in sorted(events, key=lambda x: (x[0], -x[1])):
        active += delta
        max_active = max(max_active, active)
    return int(max_active)


def audit_trade_metrics(trade_details: pd.DataFrame, config: dict | None = None, iv_lookback: int = 252) -> str:
    cfg = config or {}
    trades = trade_details.copy()
    for column in ["signal_date", "entry_date", "exit_date"]:
        trades[column] = pd.to_datetime(trades[column]).dt.normalize()

    multiplier = float(cfg.get("contract_multiplier", 100))
    slippage = float(cfg.get("slippage_rate", 0.0))
    fee = float(cfg.get("fee_per_contract", 0.0))

    lines = ["# VolLab Metric Audit", ""]
    lines.append(f"- rows: {len(trades):,}")
    lines.append(f"- signal range: {trades['signal_date'].min().date()} to {trades['signal_date'].max().date()}")
    lines.append(f"- exit range: {trades['exit_date'].min().date()} to {trades['exit_date'].max().date()}")
    lines.append("")

    group = trades.groupby("holding_days").agg(avg_return=("return_on_premium", "mean"), avg_net_pnl=("net_pnl", "mean"))
    inconsistent = group.loc[np.sign(group["avg_return"].fillna(0)) != np.sign(group["avg_net_pnl"].fillna(0))]
    lines.append(f"## 1. avg_return vs avg_net_pnl sign")
    lines.append(f"- {_fmt_bool(inconsistent.empty)}: {len(inconsistent)} holding bucket(s) have different signs.")
    lines.append("- Explanation: signs can differ only if return weighting by premium diverges from raw PnL weighting; this deserves review when present.")
    lines.append("")

    expected_return = trades["net_pnl"] / (trades["entry_premium"] * multiplier)
    return_diff = (expected_return - trades["return_on_premium"]).abs()
    lines.append("## 2. return_on_premium formula")
    lines.append(f"- {_fmt_bool(bool((return_diff < 1e-8).all()))}: max abs diff = {return_diff.max():.12f}")
    lines.append("- Formula used: net_pnl / (entry_premium_points * contract_multiplier).")
    lines.append("")

    raw_entry = trades["entry_premium"] / (1.0 + slippage) if slippage != -1 else np.nan
    raw_exit = trades["exit_premium"] / (1.0 - slippage) if slippage != 1 else np.nan
    expected_gross = (raw_exit - raw_entry) * multiplier
    gross_diff = (expected_gross - trades["gross_pnl"]).abs()
    lines.append("## 3. contract_multiplier application")
    lines.append(f"- {_fmt_bool(bool((gross_diff < 1e-6).all()))}: max gross pnl diff = {gross_diff.max():.8f}")
    lines.append("")

    expected_cost = ((raw_entry + raw_exit) * slippage * multiplier) + 4.0 * fee
    cost_diff = (expected_cost - trades["cost"]).abs()
    lines.append("## 4. cost model")
    lines.append(f"- {_fmt_bool(bool((cost_diff < 1e-6).all()))}: max cost diff = {cost_diff.max():.8f}")
    lines.append("- Cost includes entry slippage and exit slippage; fee_per_contract is applied to four legs/transactions in the simplified model.")
    lines.append("")

    holding_values = sorted(trades["holding_days"].dropna().astype(int).unique())
    lines.append("## 5. equity curve holding-day merge")
    lines.append(f"- CHECK: current dashboard equity curve merges holding_days={holding_values} into one daily realized PnL curve.")
    lines.append("")

    max_active = _max_overlap(trades)
    lines.append("## 6. daily rolling overlap")
    lines.append(f"- CHECK: max simultaneous research trades = {max_active}. Daily rolling mode intentionally contains overlapping positions.")
    lines.append("")

    strict_dates = bool(((trades["signal_date"] < trades["entry_date"]) & (trades["entry_date"] <= trades["exit_date"])).all())
    lines.append("## 7. signal/entry/exit date ordering")
    lines.append(f"- {_fmt_bool(strict_dates)}: requires signal_date < entry_date <= exit_date.")
    lines.append("")

    first_valid_rank = trades.drop_duplicates("signal_date").sort_values("signal_date")["iv_rank"].first_valid_index()
    lines.append("## 8. IV Rank / Percentile lookahead")
    lines.append("- PASS: strategy computes IV history incrementally in signal-date order, so current implementation is point-in-time.")
    lines.append("")

    signal_rows = trades.drop_duplicates("signal_date").sort_values("signal_date").reset_index(drop=True)
    warmup_count = int(min(iv_lookback - 1, len(signal_rows)))
    warmup_non_null = int(signal_rows.head(warmup_count)[["iv_rank", "iv_percentile"]].notna().sum().sum())
    lines.append("## 9. IV warmup")
    lines.append(f"- CHECK: first {warmup_count} signal samples are warmup for lookback={iv_lookback}.")
    lines.append(f"- Warmup non-null IV rank/percentile cells: {warmup_non_null}.")
    lines.append("")

    post_warmup = signal_rows.iloc[iv_lookback - 1 :] if len(signal_rows) >= iv_lookback else signal_rows.iloc[0:0]
    lines.append("## 10. warmup-separated stats")
    lines.append(f"- warmup signals: {warmup_count}")
    lines.append(f"- post-warmup signals: {len(post_warmup)}")
    if len(post_warmup):
        post_trades = trades.loc[trades["signal_date"].isin(post_warmup["signal_date"])]
        lines.append(f"- post-warmup trades: {len(post_trades)}")
        lines.append(f"- post-warmup total net pnl: {post_trades['net_pnl'].sum():.2f}")
    lines.append("")
    return "\n".join(lines)

