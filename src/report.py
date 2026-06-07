from __future__ import annotations

import numpy as np
import pandas as pd


def _max_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return np.nan
    equity = pnl.fillna(0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max())


def _profit_loss_ratio(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if wins.empty or losses.empty:
        return np.nan
    return float(wins.mean() / abs(losses.mean()))


def summarize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            [
                {
                    "total_trades": 0,
                    "win_rate": np.nan,
                    "avg_return": np.nan,
                    "median_return": np.nan,
                    "max_trade_profit": np.nan,
                    "max_trade_loss": np.nan,
                    "profit_loss_ratio": np.nan,
                    "max_drawdown": np.nan,
                    "total_net_pnl": 0.0,
                }
            ]
        )
    pnl = trades["net_pnl"].astype(float)
    returns = trades["return_on_premium"].astype(float)
    return pd.DataFrame(
        [
            {
                "total_trades": int(len(trades)),
                "win_rate": float((pnl > 0).mean()),
                "avg_return": float(returns.mean()),
                "median_return": float(returns.median()),
                "max_trade_profit": float(pnl.max()),
                "max_trade_loss": float(pnl.min()),
                "profit_loss_ratio": _profit_loss_ratio(pnl),
                "max_drawdown": _max_drawdown(pnl),
                "total_net_pnl": float(pnl.sum()),
            }
        ]
    )


def _group_summary(trades: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if trades.empty or group_col not in trades.columns:
        return pd.DataFrame()
    grouped = trades.groupby(group_col, observed=False)
    summary = grouped.agg(
        trades=("net_pnl", "size"),
        win_rate=("net_pnl", lambda x: float((x > 0).mean())),
        avg_return=("return_on_premium", "mean"),
        median_return=("return_on_premium", "median"),
        avg_net_pnl=("net_pnl", "mean"),
        total_net_pnl=("net_pnl", "sum"),
    )
    return summary.reset_index()


def summary_by_holding_days(trades: pd.DataFrame) -> pd.DataFrame:
    return _group_summary(trades, "holding_days")


def summary_by_iv_rank_bucket(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.copy()
    rank = pd.to_numeric(df["iv_rank"], errors="coerce")
    rank_pct = rank * 100.0 if rank.max(skipna=True) <= 1.0 else rank
    df["iv_rank_bucket"] = pd.cut(
        rank_pct,
        bins=[0, 20, 40, 60, 80, 100],
        labels=["0-20", "20-40", "40-60", "60-80", "80-100"],
        include_lowest=True,
    )
    return _group_summary(df.dropna(subset=["iv_rank_bucket"]), "iv_rank_bucket")


def summary_by_iv_minus_rv_bucket(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.copy()
    value = pd.to_numeric(df["iv_minus_rv20"], errors="coerce")
    df["iv_minus_rv_bucket"] = pd.cut(
        value,
        bins=[-np.inf, -0.10, -0.05, 0.0, 0.05, 0.10, np.inf],
        labels=["<-10vol", "-10--5vol", "-5-0vol", "0-5vol", "5-10vol", ">10vol"],
    )
    return _group_summary(df.dropna(subset=["iv_minus_rv_bucket"]), "iv_minus_rv_bucket")


def build_reports(trade_details: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "trade_details": trade_details.copy(),
        "summary": summarize_trades(trade_details),
        "summary_by_holding_days": summary_by_holding_days(trade_details),
        "summary_by_iv_rank_bucket": summary_by_iv_rank_bucket(trade_details),
        "summary_by_iv_minus_rv_bucket": summary_by_iv_minus_rv_bucket(trade_details),
    }

