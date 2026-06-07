from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.dte_research import bucket_dte
from src.strategy_straddle import _entry_prices, _finite_positive, _get_option_row


logger = logging.getLogger(__name__)

STRANGLE_COLUMNS = [
    "signal_date",
    "entry_date",
    "exit_date",
    "holding_days",
    "strategy",
    "moneyness",
    "call_code",
    "put_code",
    "spot_at_signal",
    "call_strike",
    "put_strike",
    "dte",
    "entry_call_price",
    "entry_put_price",
    "exit_call_price",
    "exit_put_price",
    "entry_premium",
    "exit_premium",
    "net_pnl",
    "return_on_premium",
    "entry_mode_used",
]

STRANGLE_SUMMARY_COLUMNS = [
    "strategy",
    "holding_days",
    "event_type",
    "dte_bucket",
    "data_source",
    "trade_count",
    "premium_cost",
    "win_rate",
    "avg_return",
    "median_return",
    "max_loss",
    "max_win",
    "top_5_wins_contribution",
    "event_type_capture",
]


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _date(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


def _valid_option_frame(option_chain: pd.DataFrame, spot: float, current_date, config: dict) -> pd.DataFrame:
    if option_chain is None or option_chain.empty or spot <= 0:
        return pd.DataFrame()
    current = pd.Timestamp(current_date).normalize()
    frame = option_chain.copy()
    required = ["option_code", "call_put", "strike", "expire_date", "close"]
    if any(column not in frame.columns for column in required):
        return pd.DataFrame()
    frame["expire_date"] = pd.to_datetime(frame["expire_date"], errors="coerce").dt.normalize()
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["dte"] = (frame["expire_date"] - current).dt.days
    frame["call_put_norm"] = frame["call_put"].astype(str).str.upper().str[0]
    if "volume" not in frame.columns:
        frame["volume"] = 0
    if "open_interest" not in frame.columns:
        frame["open_interest"] = 0
    liquid = _num(frame, "volume").fillna(0).gt(0) | _num(frame, "open_interest").fillna(0).gt(0)
    min_dte = int(config.get("min_dte", 7))
    max_dte = int(config.get("max_dte", 45))
    return frame.loc[
        frame["dte"].between(min_dte, max_dte)
        & frame["call_put_norm"].isin(["C", "P"])
        & frame["strike"].notna()
        & frame["close"].gt(0)
        & liquid
    ].copy()


def select_otm_strangle(option_chain: pd.DataFrame, spot: float, current_date, config: dict, moneyness: float) -> dict | None:
    valid = _valid_option_frame(option_chain, float(spot), current_date, config)
    if valid.empty:
        select_otm_strangle.last_reason = "no valid option chain"
        return None

    expiries = valid[["expire_date", "dte"]].drop_duplicates().sort_values(["dte", "expire_date"])
    for _, expiry_row in expiries.iterrows():
        month = valid.loc[valid["expire_date"].eq(expiry_row["expire_date"])].copy()
        puts = month.loc[month["call_put_norm"].eq("P")]
        calls = month.loc[month["call_put_norm"].eq("C")]
        target_put = float(spot) * (1.0 - float(moneyness))
        target_call = float(spot) * (1.0 + float(moneyness))
        put_candidates = puts.loc[puts["strike"] <= target_put].copy()
        call_candidates = calls.loc[calls["strike"] >= target_call].copy()
        if put_candidates.empty or call_candidates.empty:
            continue
        put = put_candidates.assign(distance=(put_candidates["strike"] - target_put).abs()).sort_values(
            ["distance", "close"], ascending=[True, True]
        ).iloc[0]
        call = call_candidates.assign(distance=(call_candidates["strike"] - target_call).abs()).sort_values(
            ["distance", "close"], ascending=[True, True]
        ).iloc[0]
        select_otm_strangle.last_reason = "ok"
        return {
            "put": put.to_dict(),
            "call": call.to_dict(),
            "put_code": put["option_code"],
            "call_code": call["option_code"],
            "put_strike": float(put["strike"]),
            "call_strike": float(call["strike"]),
            "expire_date": pd.Timestamp(expiry_row["expire_date"]),
            "dte": int(expiry_row["dte"]),
        }
    select_otm_strangle.last_reason = "no OTM put/call pair at requested moneyness"
    return None


select_otm_strangle.last_reason = ""


def run_strangle_strategy(
    provider,
    config: dict,
    start_date=None,
    end_date=None,
    moneyness_levels: tuple[float, ...] = (0.03, 0.05),
    holding_days: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    start = start_date or config.get("backtest_start_date") or config.get("mock_start_date")
    end = end_date or config.get("backtest_end_date") or config.get("mock_end_date")
    if start is None or end is None:
        raise ValueError("start_date/end_date or config mock_start_date/mock_end_date is required")

    calendar = provider.get_trading_calendar(start, end).sort_values("date").reset_index(drop=True)
    underlying = provider.get_underlying_daily(start, end).sort_values("date").reset_index(drop=True)
    if calendar.empty or underlying.empty:
        return pd.DataFrame(columns=STRANGLE_COLUMNS)

    dates = list(pd.to_datetime(calendar["date"]).dt.normalize())
    underlying = underlying.copy()
    underlying["date"] = pd.to_datetime(underlying["date"]).dt.normalize()
    underlying_by_date = underlying.set_index("date")
    max_holding = max(int(value) for value in holding_days)
    multiplier = float(config.get("contract_multiplier", 100))
    slippage = float(config.get("slippage_rate", 0.0))
    fee_per_contract = float(config.get("fee_per_contract", 0.0))
    rows = []

    for i, signal_date in enumerate(dates):
        if i + max_holding >= len(dates) or signal_date not in underlying_by_date.index:
            continue
        spot = float(underlying_by_date.loc[signal_date, "close"])
        chain = provider.get_option_chain(signal_date)
        for moneyness in moneyness_levels:
            selection = select_otm_strangle(chain, spot, signal_date, config, moneyness)
            if selection is None:
                continue
            entry_date = dates[i + 1]
            max_exit_date = dates[i + max_holding]
            option_daily = provider.get_option_daily([selection["call_code"], selection["put_code"]], entry_date, max_exit_date)
            if option_daily.empty:
                continue
            option_daily = option_daily.copy()
            option_daily["date_norm"] = pd.to_datetime(option_daily["date"]).dt.normalize()

            for holding in holding_days:
                exit_idx = i + int(holding)
                if exit_idx >= len(dates):
                    continue
                exit_date = dates[exit_idx]
                call_entry = _get_option_row(option_daily, selection["call_code"], entry_date)
                put_entry = _get_option_row(option_daily, selection["put_code"], entry_date)
                call_exit = _get_option_row(option_daily, selection["call_code"], exit_date)
                put_exit = _get_option_row(option_daily, selection["put_code"], exit_date)
                if call_entry is None or put_entry is None or call_exit is None or put_exit is None:
                    continue
                entry_call, entry_put, entry_mode_used = _entry_prices(call_entry, put_entry, config)
                exit_call = call_exit.get("close")
                exit_put = put_exit.get("close")
                if entry_call is None or entry_put is None or not _finite_positive(exit_call) or not _finite_positive(exit_put):
                    continue

                raw_entry = float(entry_call) + float(entry_put)
                raw_exit = float(exit_call) + float(exit_put)
                entry_premium = raw_entry * (1.0 + slippage)
                exit_premium = raw_exit * (1.0 - slippage)
                net_pnl = (exit_premium - entry_premium) * multiplier - 4.0 * fee_per_contract
                rows.append(
                    {
                        "signal_date": signal_date,
                        "entry_date": entry_date,
                        "exit_date": exit_date,
                        "holding_days": int(holding),
                        "strategy": f"{int(round(moneyness * 100))}% OTM strangle",
                        "moneyness": float(moneyness),
                        "call_code": selection["call_code"],
                        "put_code": selection["put_code"],
                        "spot_at_signal": spot,
                        "call_strike": selection["call_strike"],
                        "put_strike": selection["put_strike"],
                        "dte": selection["dte"],
                        "entry_call_price": float(entry_call),
                        "entry_put_price": float(entry_put),
                        "exit_call_price": float(exit_call),
                        "exit_put_price": float(exit_put),
                        "entry_premium": entry_premium,
                        "exit_premium": exit_premium,
                        "net_pnl": net_pnl,
                        "return_on_premium": net_pnl / (entry_premium * multiplier) if entry_premium > 0 else np.nan,
                        "entry_mode_used": entry_mode_used,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=STRANGLE_COLUMNS)
    return pd.DataFrame(rows, columns=STRANGLE_COLUMNS).sort_values(["strategy", "signal_date", "holding_days"]).reset_index(drop=True)


def _top_wins_share(pnl: pd.Series) -> float:
    total = pnl.sum()
    if total == 0:
        return np.nan
    return float(pnl.sort_values(ascending=False).head(5).sum() / total)


def _prepare_strategy_frame(
    atm_trades: pd.DataFrame,
    strangle_trades: pd.DataFrame | None = None,
    event_classification: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frames = []
    if atm_trades is not None and not atm_trades.empty:
        atm = atm_trades.copy()
        atm["strategy"] = "ATM straddle"
        atm["moneyness"] = 0.0
        atm["data_source"] = "processed_trade_details"
        frames.append(atm)
    if strangle_trades is not None and not strangle_trades.empty:
        strangles = strangle_trades.copy()
        strangles["data_source"] = "provider_chain"
        frames.append(strangles)
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True, sort=False)
    frame["signal_date"] = _date(frame, "signal_date")
    frame["holding_days"] = _num(frame, "holding_days").astype("Int64")
    frame["dte_bucket"] = frame["dte"].apply(bucket_dte)
    frame["event_type"] = "unclassified"
    if event_classification is not None and not event_classification.empty:
        events = event_classification.copy()
        events["signal_date"] = _date(events, "signal_date")
        events["holding_days"] = _num(events, "holding_days").astype("Int64")
        frame = frame.merge(
            events[["signal_date", "holding_days", "event_type"]],
            on=["signal_date", "holding_days"],
            how="left",
            suffixes=("", "_event"),
        )
        frame["event_type"] = frame["event_type_event"].combine_first(frame["event_type"])
        frame = frame.drop(columns=["event_type_event"])
    return frame


def _summary_row(selected: pd.DataFrame, strategy_frame: pd.DataFrame, keys: dict) -> dict:
    pnl = _num(selected, "net_pnl").dropna()
    ret = _num(selected, "return_on_premium").dropna()
    event_type = keys.get("event_type", "all")
    if event_type != "all" and "event_type" in strategy_frame.columns:
        event_total = len(strategy_frame.loc[strategy_frame["event_type"].eq(event_type)])
    else:
        event_total = 0
    return {
        **keys,
        "data_source": selected["data_source"].iloc[0] if not selected.empty and "data_source" in selected else keys.get("data_source", ""),
        "trade_count": int(len(selected)),
        "premium_cost": float(_num(selected, "entry_premium").mean()) if len(selected) else np.nan,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
        "avg_return": float(ret.mean()) if len(ret) else np.nan,
        "median_return": float(ret.median()) if len(ret) else np.nan,
        "max_loss": float(pnl.min()) if len(pnl) else np.nan,
        "max_win": float(pnl.max()) if len(pnl) else np.nan,
        "top_5_wins_contribution": _top_wins_share(pnl) if len(pnl) else np.nan,
        "event_type_capture": float(len(selected) / event_total) if event_total else np.nan,
    }


def summarize_straddle_vs_strangle(
    atm_trades: pd.DataFrame,
    strangle_trades: pd.DataFrame | None = None,
    event_classification: pd.DataFrame | None = None,
    include_unavailable_otm: bool = True,
) -> pd.DataFrame:
    frame = _prepare_strategy_frame(atm_trades, strangle_trades, event_classification)
    rows = []
    if not frame.empty:
        for (strategy, holding), selected in frame.groupby(["strategy", "holding_days"], dropna=False, observed=False):
            strategy_frame = frame.loc[frame["strategy"].eq(strategy)]
            rows.append(
                _summary_row(
                    selected,
                    strategy_frame,
                    {
                        "strategy": strategy,
                        "holding_days": int(holding),
                        "event_type": "all",
                        "dte_bucket": "all",
                    },
                )
            )
        for (strategy, holding, event_type, dte_bucket), selected in frame.groupby(
            ["strategy", "holding_days", "event_type", "dte_bucket"], dropna=False, observed=False
        ):
            strategy_frame = frame.loc[frame["strategy"].eq(strategy)]
            rows.append(
                _summary_row(
                    selected,
                    strategy_frame,
                    {
                        "strategy": strategy,
                        "holding_days": int(holding),
                        "event_type": event_type,
                        "dte_bucket": dte_bucket,
                    },
                )
            )
    if include_unavailable_otm:
        existing = set(frame["strategy"].dropna().astype(str).unique()) if not frame.empty else set()
        for strategy in ["3% OTM strangle", "5% OTM strangle"]:
            if strategy in existing:
                continue
            for holding in [1, 3, 5]:
                rows.append(
                    {
                        "strategy": strategy,
                        "holding_days": holding,
                        "event_type": "all",
                        "dte_bucket": "all",
                        "data_source": "unavailable_no_chain",
                        "trade_count": 0,
                        "premium_cost": np.nan,
                        "win_rate": np.nan,
                        "avg_return": np.nan,
                        "median_return": np.nan,
                        "max_loss": np.nan,
                        "max_win": np.nan,
                        "top_5_wins_contribution": np.nan,
                        "event_type_capture": np.nan,
                    }
                )
    return pd.DataFrame(rows, columns=STRANGLE_SUMMARY_COLUMNS)
