from __future__ import annotations

import pandas as pd

from src.instruments import to_timestamp


def _fail(reason: str):
    select_atm_straddle.last_reason = reason
    return None


def _is_positive(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0) > 0


def select_atm_straddle(option_chain, spot, current_date, config):
    """Select the nearest valid ATM call and put pair for one signal date."""

    select_atm_straddle.last_reason = ""
    if option_chain is None or len(option_chain) == 0:
        return _fail("empty option chain")
    if spot is None or pd.isna(spot) or float(spot) <= 0:
        return _fail("invalid spot")

    current = to_timestamp(current_date)
    df = option_chain.copy()
    required = ["option_code", "call_put", "strike", "expire_date", "close"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        return _fail(f"missing columns: {missing}")

    df["expire_date"] = pd.to_datetime(df["expire_date"]).dt.normalize()
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["dte"] = (df["expire_date"] - current).dt.days
    df["call_put_norm"] = df["call_put"].astype(str).str.upper().str[0]
    if "volume" not in df.columns:
        df["volume"] = 0
    if "open_interest" not in df.columns:
        df["open_interest"] = 0

    liquid = _is_positive(df["volume"]) | _is_positive(df["open_interest"])
    valid = df.loc[
        (df["dte"] > 0)
        & df["strike"].notna()
        & df["close"].notna()
        & (df["close"] > 0)
        & df["call_put_norm"].isin(["C", "P"])
        & liquid
    ].copy()
    if valid.empty:
        return _fail("no valid liquid options")

    min_dte = int(config.get("min_dte", 10))
    max_dte = int(config.get("max_dte", 35))
    roll_threshold = int(config.get("roll_dte_threshold", 7))
    eligible = valid.loc[(valid["dte"] >= min_dte) & (valid["dte"] <= max_dte)].copy()
    if eligible.empty:
        return _fail(f"no contracts with DTE in [{min_dte}, {max_dte}]")

    nearest = valid.sort_values("dte").iloc[0]
    expiries = eligible[["expire_date", "dte"]].drop_duplicates().sort_values(["dte", "expire_date"]).reset_index(drop=True)
    if (
        pd.Timestamp(nearest["expire_date"]) in set(expiries["expire_date"])
        and int(nearest["dte"]) < roll_threshold
        and len(expiries) > 1
    ):
        chosen_expiry = expiries.iloc[1]["expire_date"]
    else:
        chosen_expiry = expiries.iloc[0]["expire_date"]

    month = eligible.loc[eligible["expire_date"] == chosen_expiry].copy()
    calls = month.loc[month["call_put_norm"] == "C"]
    puts = month.loc[month["call_put_norm"] == "P"]
    common_strikes = sorted(set(calls["strike"]).intersection(set(puts["strike"])))
    if not common_strikes:
        return _fail("no strike with both call and put")

    strike = min(common_strikes, key=lambda value: abs(float(value) - float(spot)))
    call = calls.loc[calls["strike"] == strike].sort_values("close").iloc[0].to_dict()
    put = puts.loc[puts["strike"] == strike].sort_values("close").iloc[0].to_dict()
    select_atm_straddle.last_reason = "ok"
    return {
        "call": call,
        "put": put,
        "call_code": call["option_code"],
        "put_code": put["option_code"],
        "strike": float(strike),
        "expire_date": pd.Timestamp(chosen_expiry),
        "dte": int(call["dte"]),
    }


select_atm_straddle.last_reason = ""

