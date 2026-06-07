from __future__ import annotations

import numpy as np
import pandas as pd

from src.option_pricer import implied_vol
from src.option_selector import select_atm_straddle
from src.vol_metrics import iv_percentile, iv_rank, realized_vol


TRADE_COLUMNS = [
    "signal_date",
    "entry_date",
    "exit_date",
    "holding_days",
    "underlying_code",
    "call_code",
    "put_code",
    "spot_at_signal",
    "strike",
    "dte",
    "entry_call_price",
    "entry_put_price",
    "exit_call_price",
    "exit_put_price",
    "entry_premium",
    "exit_premium",
    "gross_pnl",
    "cost",
    "net_pnl",
    "return_on_premium",
    "atm_iv",
    "rv20",
    "iv_rank",
    "iv_percentile",
    "iv_minus_rv20",
    "entry_mode_used",
]


def _finite_positive(value) -> bool:
    return value is not None and np.isfinite(value) and float(value) > 0


def _get_option_row(option_daily: pd.DataFrame, option_code: str, date: pd.Timestamp) -> pd.Series | None:
    date_column = "date_norm" if "date_norm" in option_daily.columns else "date"
    dates = option_daily[date_column]
    if date_column == "date":
        dates = pd.to_datetime(dates).dt.normalize()
    rows = option_daily.loc[
        (option_daily["option_code"] == option_code)
        & (dates == pd.Timestamp(date).normalize())
    ]
    if rows.empty:
        return None
    return rows.iloc[0]


def _entry_prices(call_row: pd.Series, put_row: pd.Series, config: dict) -> tuple[float | None, float | None, str]:
    entry_mode = str(config.get("entry_mode", "next_open")).lower()
    fallback_mode = str(config.get("fallback_entry_mode", "next_close")).lower()
    if entry_mode == "next_open":
        call_open = call_row.get("open")
        put_open = put_row.get("open")
        if _finite_positive(call_open) and _finite_positive(put_open):
            return float(call_open), float(put_open), "next_open"
        if fallback_mode == "next_close":
            call_close = call_row.get("close")
            put_close = put_row.get("close")
            if _finite_positive(call_close) and _finite_positive(put_close):
                return float(call_close), float(put_close), "next_close"
        return None, None, "missing_entry"

    call_close = call_row.get("close")
    put_close = put_row.get("close")
    if _finite_positive(call_close) and _finite_positive(put_close):
        return float(call_close), float(put_close), "next_close"
    return None, None, "missing_entry"


def _last_metric(series: pd.Series, lookback: int, metric_func) -> float:
    if len(series) < lookback:
        return np.nan
    value = metric_func(series, lookback=lookback).iloc[-1]
    return float(value) if pd.notna(value) else np.nan


def run_straddle_strategy(provider, config: dict, start_date=None, end_date=None) -> pd.DataFrame:
    start = start_date or config.get("backtest_start_date") or config.get("mock_start_date")
    end = end_date or config.get("backtest_end_date") or config.get("mock_end_date")
    if start is None or end is None:
        raise ValueError("start_date/end_date or config mock_start_date/mock_end_date is required")

    calendar = provider.get_trading_calendar(start, end).sort_values("date").reset_index(drop=True)
    underlying = provider.get_underlying_daily(start, end).sort_values("date").reset_index(drop=True)
    if calendar.empty or underlying.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)

    dates = list(pd.to_datetime(calendar["date"]).dt.normalize())
    underlying = underlying.copy()
    underlying["date"] = pd.to_datetime(underlying["date"]).dt.normalize()
    underlying_by_date = underlying.set_index("date")
    close = underlying_by_date["close"].astype(float)
    rv20_series = realized_vol(close, 20)

    multiplier = float(config.get("contract_multiplier", 100))
    r = float(config.get("risk_free_rate", 0.02))
    slippage = float(config.get("slippage_rate", 0.0))
    fee_per_contract = float(config.get("fee_per_contract", 0.0))
    holding_days_list = [int(value) for value in config.get("holding_days", [1, 2, 3, 5])]
    max_holding = max(holding_days_list)
    iv_lookback = int(config.get("iv_lookback", 252))

    rows = []
    iv_history_index: list[pd.Timestamp] = []
    iv_history_values: list[float] = []

    for i, signal_date in enumerate(dates):
        if i + max_holding >= len(dates) or signal_date not in underlying_by_date.index:
            continue
        spot = float(underlying_by_date.loc[signal_date, "close"])
        chain = provider.get_option_chain(signal_date)
        selection = select_atm_straddle(chain, spot, signal_date, config)
        if selection is None:
            continue

        call_signal_price = float(selection["call"]["close"])
        put_signal_price = float(selection["put"]["close"])
        strike = float(selection["strike"])
        dte = int(selection["dte"])
        T = max(dte / 252.0, 1.0 / 252.0)
        call_iv = implied_vol(call_signal_price, spot, strike, T, r, "C")
        put_iv = implied_vol(put_signal_price, spot, strike, T, r, "P")
        finite_ivs = [value for value in [call_iv, put_iv] if np.isfinite(value) and value > 0]
        if finite_ivs:
            atm_iv = float(np.mean(finite_ivs))
        else:
            atm_iv = float(np.nanmean([selection["call"].get("implied_vol"), selection["put"].get("implied_vol")]))

        iv_history_index.append(signal_date)
        iv_history_values.append(atm_iv)
        iv_series = pd.Series(iv_history_values, index=iv_history_index, dtype="float64")
        current_iv_rank = _last_metric(iv_series, iv_lookback, iv_rank)
        current_iv_percentile = _last_metric(iv_series, iv_lookback, iv_percentile)
        rv20 = float(rv20_series.loc[signal_date]) if signal_date in rv20_series.index and pd.notna(rv20_series.loc[signal_date]) else np.nan
        iv_minus_rv20 = atm_iv - rv20 if np.isfinite(atm_iv) and np.isfinite(rv20) else np.nan

        entry_date = dates[i + 1]
        max_exit_date = dates[i + max_holding]
        option_daily = provider.get_option_daily([selection["call_code"], selection["put_code"]], entry_date, max_exit_date)
        if option_daily.empty:
            continue
        option_daily = option_daily.copy()
        option_daily["date_norm"] = pd.to_datetime(option_daily["date"]).dt.normalize()

        for holding_days in holding_days_list:
            entry_idx = i + 1
            exit_idx = i + holding_days
            if exit_idx >= len(dates):
                continue
            exit_date = dates[exit_idx]
            call_entry = _get_option_row(option_daily, selection["call_code"], entry_date)
            put_entry = _get_option_row(option_daily, selection["put_code"], entry_date)
            call_exit = _get_option_row(option_daily, selection["call_code"], exit_date)
            put_exit = _get_option_row(option_daily, selection["put_code"], exit_date)
            if call_entry is None or put_entry is None or call_exit is None or put_exit is None:
                continue

            entry_call_price, entry_put_price, entry_mode_used = _entry_prices(call_entry, put_entry, config)
            if entry_call_price is None or entry_put_price is None:
                continue
            exit_call_price = call_exit.get("close")
            exit_put_price = put_exit.get("close")
            if not _finite_positive(exit_call_price) or not _finite_positive(exit_put_price):
                continue

            raw_entry_premium = float(entry_call_price) + float(entry_put_price)
            raw_exit_premium = float(exit_call_price) + float(exit_put_price)
            entry_premium = raw_entry_premium * (1.0 + slippage)
            exit_premium = raw_exit_premium * (1.0 - slippage)
            gross_pnl = (raw_exit_premium - raw_entry_premium) * multiplier
            fees = 4.0 * fee_per_contract
            net_pnl = (exit_premium - entry_premium) * multiplier - fees
            cost = gross_pnl - net_pnl
            return_on_premium = net_pnl / (entry_premium * multiplier) if entry_premium > 0 else np.nan

            rows.append(
                {
                    "signal_date": signal_date,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "holding_days": holding_days,
                    "underlying_code": config.get("underlying_code", ""),
                    "call_code": selection["call_code"],
                    "put_code": selection["put_code"],
                    "spot_at_signal": spot,
                    "strike": strike,
                    "dte": dte,
                    "entry_call_price": float(entry_call_price),
                    "entry_put_price": float(entry_put_price),
                    "exit_call_price": float(exit_call_price),
                    "exit_put_price": float(exit_put_price),
                    "entry_premium": entry_premium,
                    "exit_premium": exit_premium,
                    "gross_pnl": gross_pnl,
                    "cost": cost,
                    "net_pnl": net_pnl,
                    "return_on_premium": return_on_premium,
                    "atm_iv": atm_iv,
                    "rv20": rv20,
                    "iv_rank": current_iv_rank,
                    "iv_percentile": current_iv_percentile,
                    "iv_minus_rv20": iv_minus_rv20,
                    "entry_mode_used": entry_mode_used,
                }
            )

    if not rows:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    return pd.DataFrame(rows, columns=TRADE_COLUMNS).sort_values(["signal_date", "holding_days"]).reset_index(drop=True)
