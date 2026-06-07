from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError
import streamlit as st

from src.backtest_engine import BacktestEngine
from src.instruments import build_data_provider, load_config, resolve_project_path
from src.option_pricer import implied_vol
from src.option_selector import select_atm_straddle
from src.vol_metrics import realized_vol


st.set_page_config(page_title="VolLab", layout="wide")


REPORT_FILES = {
    "trade_details": "trade_details.csv",
    "summary": "summary.csv",
    "summary_by_holding_days": "summary_by_holding_days.csv",
    "summary_by_iv_rank_bucket": "summary_by_iv_rank_bucket.csv",
    "summary_by_iv_minus_rv_bucket": "summary_by_iv_minus_rv_bucket.csv",
}


def load_processed_reports(processed_dir: Path) -> dict[str, pd.DataFrame] | None:
    paths = {name: processed_dir / filename for name, filename in REPORT_FILES.items()}
    if not all(path.exists() for path in paths.values()):
        return None

    reports = {}
    for name, path in paths.items():
        try:
            frame = pd.read_csv(path)
        except EmptyDataError:
            frame = pd.DataFrame()
        for column in ["signal_date", "entry_date", "exit_date", "date"]:
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        reports[name] = frame
    return reports


def underlying_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    frame = (
        trades[["signal_date", "spot_at_signal"]]
        .dropna()
        .drop_duplicates(subset=["signal_date"])
        .sort_values("signal_date")
        .rename(columns={"signal_date": "date", "spot_at_signal": "close"})
    )
    frame["open"] = frame["close"]
    frame["high"] = frame["close"]
    frame["low"] = frame["close"]
    frame["volume"] = np.nan
    return frame[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_dashboard_data():
    config = load_config()
    processed_reports = load_processed_reports(resolve_project_path("data/processed"))
    if processed_reports is not None and str(config.get("data_mode", "")).lower() == "wind":
        return config, underlying_from_trades(processed_reports["trade_details"]), processed_reports, "processed"

    provider = build_data_provider(config)
    start = config.get("backtest_start_date") or config.get("mock_start_date")
    end = config.get("backtest_end_date") or config.get("mock_end_date")
    underlying = provider.get_underlying_daily(start, end).sort_values("date").reset_index(drop=True)
    reports = BacktestEngine(provider, config).run(start, end)
    return config, underlying, reports, "live"


def latest_signal_from_trades(trades: pd.DataFrame):
    if trades.empty:
        return None, np.nan, None
    latest = trades.sort_values(["signal_date", "holding_days"]).iloc[-1]
    latest_date = pd.Timestamp(latest["signal_date"]).normalize()
    selected = {
        "call_code": latest.get("call_code"),
        "put_code": latest.get("put_code"),
        "strike": latest.get("strike"),
        "dte": latest.get("dte"),
        "atm_iv": latest.get("atm_iv"),
        "rv20": latest.get("rv20"),
        "call": {
            "close": latest.get("entry_call_price"),
            "volume": np.nan,
            "open_interest": np.nan,
        },
        "put": {
            "close": latest.get("entry_put_price"),
            "volume": np.nan,
            "open_interest": np.nan,
        },
    }
    return latest_date, float(latest.get("spot_at_signal", np.nan)), selected


def latest_signal_snapshot(config: dict, underlying: pd.DataFrame, trades: pd.DataFrame, source_mode: str):
    if source_mode == "processed":
        return latest_signal_from_trades(trades)

    latest_date = pd.to_datetime(underlying["date"]).dt.normalize().iloc[-1]
    spot = float(underlying["close"].iloc[-1])
    try:
        provider = build_data_provider(config)
        chain = provider.get_option_chain(latest_date)
        selected = select_atm_straddle(chain, spot, latest_date, config)
        if selected is None:
            return latest_signal_from_trades(trades)
    except Exception:
        return latest_signal_from_trades(trades)

    r = float(config.get("risk_free_rate", 0.02))
    T = max(int(selected["dte"]) / 252.0, 1.0 / 252.0)
    call_iv = implied_vol(float(selected["call"]["close"]), spot, float(selected["strike"]), T, r, "C")
    put_iv = implied_vol(float(selected["put"]["close"]), spot, float(selected["strike"]), T, r, "P")
    finite_ivs = [value for value in [call_iv, put_iv] if np.isfinite(value) and value > 0]
    atm_iv = float(np.mean(finite_ivs)) if finite_ivs else np.nan
    rv20 = realized_vol(underlying.set_index(pd.to_datetime(underlying["date"]).dt.normalize())["close"], 20).iloc[-1]
    return latest_date, spot, {**selected, "atm_iv": atm_iv, "rv20": rv20}


def vol_long_score(iv_percentile_value, iv_minus_rv20_value, rv20_series: pd.Series, selected) -> float:
    score = 50.0
    if pd.notna(iv_percentile_value):
        score += (0.5 - float(iv_percentile_value)) * 45.0
    if pd.notna(iv_minus_rv20_value):
        score += np.clip(-float(iv_minus_rv20_value) * 180.0, -20.0, 20.0)
    if len(rv20_series.dropna()) >= 5 and rv20_series.dropna().iloc[-1] > rv20_series.dropna().iloc[-5]:
        score += 10.0
    if selected:
        call_ok = float(selected["call"].get("volume", 0)) > 0 or float(selected["call"].get("open_interest", 0)) > 0
        put_ok = float(selected["put"].get("volume", 0)) > 0 or float(selected["put"].get("open_interest", 0)) > 0
        if call_ok and put_ok:
            score += 5.0
    return float(np.clip(score, 0.0, 100.0))


def fmt_pct(value):
    return "NA" if pd.isna(value) else f"{float(value) * 100:.1f}%"


config, underlying, reports, source_mode = load_dashboard_data()
trades = reports["trade_details"]
latest_date, spot, selected = latest_signal_snapshot(config, underlying, trades, source_mode)

st.title("VolLab")
st.caption(
    f"{config.get('underlying_code')} ATM straddle daily research | "
    f"data_mode={config.get('data_mode')} | "
    f"display_source={source_mode} | "
    f"{config.get('backtest_start_date') or config.get('mock_start_date')} to "
    f"{config.get('backtest_end_date') or config.get('mock_end_date')}"
)

metric_cols = st.columns(4)
metric_cols[0].metric("Latest Date", latest_date.date().isoformat())
metric_cols[1].metric("Spot Close", f"{spot:,.2f}")

latest_trade = trades.sort_values("signal_date").iloc[-1] if not trades.empty else None
atm_iv = selected["atm_iv"] if selected else np.nan
rv20 = selected["rv20"] if selected else np.nan
iv_rank_value = latest_trade["iv_rank"] if latest_trade is not None else np.nan
iv_percentile_value = latest_trade["iv_percentile"] if latest_trade is not None else np.nan
iv_minus_rv20_value = atm_iv - rv20 if pd.notna(atm_iv) and pd.notna(rv20) else np.nan
rv20_series = realized_vol(underlying.set_index(pd.to_datetime(underlying["date"]).dt.normalize())["close"], 20)
score = vol_long_score(iv_percentile_value, iv_minus_rv20_value, rv20_series, selected)

metric_cols[2].metric("ATM IV", fmt_pct(atm_iv))
metric_cols[3].metric("Vol Long Score", f"{score:.0f}")

detail_cols = st.columns(4)
detail_cols[0].metric("RV20", fmt_pct(rv20))
detail_cols[1].metric("IV Rank", fmt_pct(iv_rank_value))
detail_cols[2].metric("IV Percentile", fmt_pct(iv_percentile_value))
detail_cols[3].metric("IV - RV20", fmt_pct(iv_minus_rv20_value))

if selected:
    st.subheader("Latest ATM Straddle")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "call_code": selected["call_code"],
                    "put_code": selected["put_code"],
                    "strike": selected["strike"],
                    "dte": selected["dte"],
                    "call_close": selected["call"]["close"],
                    "put_close": selected["put"]["close"],
                }
            ]
        ),
        width="stretch",
    )
else:
    st.warning(f"No valid latest ATM straddle: {select_atm_straddle.last_reason}")

st.subheader("Backtest Equity Curve")
if trades.empty:
    st.info("No trades generated.")
else:
    curve = trades[["exit_date", "net_pnl"]].copy()
    curve["exit_date"] = pd.to_datetime(curve["exit_date"])
    curve = curve.groupby("exit_date", as_index=False)["net_pnl"].sum()
    curve["cum_net_pnl"] = curve["net_pnl"].cumsum()
    st.line_chart(curve.set_index("exit_date")["cum_net_pnl"])

    table_cols = st.columns(2)
    with table_cols[0]:
        st.subheader("Holding Day Summary")
        st.dataframe(reports["summary_by_holding_days"], width="stretch")
    with table_cols[1]:
        st.subheader("IV Rank Buckets")
        st.dataframe(reports["summary_by_iv_rank_bucket"], width="stretch")

    st.subheader("IV - RV20 Buckets")
    st.dataframe(reports["summary_by_iv_minus_rv_bucket"], width="stretch")

    st.subheader("Trade Details")
    st.dataframe(trades, width="stretch")
