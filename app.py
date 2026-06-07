from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError
import streamlit as st

from src.backtest_engine import BacktestEngine
from src.experiment_runner import run_timing_experiments
from src.instruments import build_data_provider, load_config, resolve_project_path
from src.option_pricer import implied_vol
from src.option_selector import select_atm_straddle
from src.rule_filters import DEFAULT_RULES
from src.vol_metrics import realized_vol


st.set_page_config(page_title="VolLab", layout="wide")


REPORT_FILES = {
    "trade_details": "trade_details.csv",
    "summary": "summary.csv",
    "summary_by_holding_days": "summary_by_holding_days.csv",
    "summary_by_iv_rank_bucket": "summary_by_iv_rank_bucket.csv",
    "summary_by_iv_minus_rv_bucket": "summary_by_iv_minus_rv_bucket.csv",
}

ARTIFACT_FILES = {
    "feature_table": "data/processed/feature_table.csv",
    "label_table": "data/processed/label_table.csv",
    "event_daily": "reports/event_study_top_daily_pnl.csv",
    "event_trades": "reports/event_study_top_trades.csv",
    "event_windows": "reports/event_study_windows.csv",
    "timing_summary": "reports/timing_experiment_summary.csv",
}


def read_csv_safe(path: Path, parse_date_columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()
    for column in parse_date_columns or []:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def load_processed_reports(processed_dir: Path) -> dict[str, pd.DataFrame] | None:
    paths = {name: processed_dir / filename for name, filename in REPORT_FILES.items()}
    if not all(path.exists() for path in paths.values()):
        return None
    reports = {}
    for name, path in paths.items():
        reports[name] = read_csv_safe(path, ["signal_date", "entry_date", "exit_date", "date"])
    return reports


def load_artifacts() -> dict[str, pd.DataFrame]:
    artifacts = {}
    for name, rel_path in ARTIFACT_FILES.items():
        artifacts[name] = read_csv_safe(resolve_project_path(rel_path), ["signal_date", "event_date", "entry_date", "exit_date"])
    return artifacts


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
    artifacts = load_artifacts()
    if processed_reports is not None and str(config.get("data_mode", "")).lower() == "wind":
        return config, underlying_from_trades(processed_reports["trade_details"]), processed_reports, artifacts, "processed"

    provider = build_data_provider(config)
    start = config.get("backtest_start_date") or config.get("mock_start_date")
    end = config.get("backtest_end_date") or config.get("mock_end_date")
    underlying = provider.get_underlying_daily(start, end).sort_values("date").reset_index(drop=True)
    reports = BacktestEngine(provider, config).run(start, end)
    return config, underlying, reports, artifacts, "live"


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
        "entry_call_price": latest.get("entry_call_price"),
        "entry_put_price": latest.get("entry_put_price"),
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


def fmt_pct(value):
    return "NA" if pd.isna(value) else f"{float(value) * 100:.1f}%"


def fmt_score(value):
    return "NA" if pd.isna(value) else f"{float(value):.0f}"


def latest_feature_row(feature_table: pd.DataFrame, latest_date) -> pd.Series:
    if feature_table.empty:
        return pd.Series(dtype="float64")
    feature_table = feature_table.copy()
    feature_table["signal_date"] = pd.to_datetime(feature_table["signal_date"]).dt.normalize()
    if latest_date is not None:
        rows = feature_table.loc[feature_table["signal_date"] <= pd.Timestamp(latest_date).normalize()]
        if not rows.empty:
            return rows.sort_values("signal_date").iloc[-1]
    return feature_table.sort_values("signal_date").iloc[-1]


def render_overview(config, underlying, reports, artifacts, source_mode):
    trades = reports["trade_details"]
    feature_table = artifacts.get("feature_table", pd.DataFrame())
    latest_date, spot, selected = latest_signal_snapshot(config, underlying, trades, source_mode)
    latest_feature = latest_feature_row(feature_table, latest_date)

    st.title("VolLab")
    st.caption(
        f"{config.get('underlying_code')} ATM straddle daily research | "
        f"data_mode={config.get('data_mode')} | "
        f"display_source={source_mode} | "
        f"{config.get('backtest_start_date') or config.get('mock_start_date')} to "
        f"{config.get('backtest_end_date') or config.get('mock_end_date')}"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Latest Date", latest_date.date().isoformat() if latest_date is not None else "NA")
    metric_cols[1].metric("Spot Close", "NA" if pd.isna(spot) else f"{spot:,.2f}")
    metric_cols[2].metric("ATM IV", fmt_pct(selected.get("atm_iv") if selected else np.nan))
    metric_cols[3].metric("Valuation Score", fmt_score(latest_feature.get("valuation_score", np.nan)))

    detail_cols = st.columns(4)
    detail_cols[0].metric("RV20", fmt_pct(selected.get("rv20") if selected else np.nan))
    detail_cols[1].metric("IV Rank", fmt_pct(latest_feature.get("iv_rank", np.nan)))
    detail_cols[2].metric("IV Percentile", fmt_pct(latest_feature.get("iv_percentile", np.nan)))
    detail_cols[3].metric("IV - RV20", fmt_pct(latest_feature.get("iv_minus_rv20", np.nan)))

    score_cols = st.columns(4)
    score_cols[0].metric("Compression", fmt_score(latest_feature.get("compression_score", np.nan)))
    score_cols[1].metric("Trigger", fmt_score(latest_feature.get("trigger_score", np.nan)))
    score_cols[2].metric("Liquidity", fmt_score(latest_feature.get("liquidity_score", np.nan)))
    score_cols[3].metric("Legacy Vol Score", fmt_score(latest_feature.get("old_vol_long_score", np.nan)))

    if selected:
        st.subheader("Latest ATM Straddle")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "call_code": selected.get("call_code"),
                        "put_code": selected.get("put_code"),
                        "strike": selected.get("strike"),
                        "dte": selected.get("dte"),
                        "entry_call_price": selected.get("entry_call_price"),
                        "entry_put_price": selected.get("entry_put_price"),
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
        return

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


def render_feature_lab(feature_table: pd.DataFrame):
    st.header("Feature Lab")
    if feature_table.empty:
        st.info("Run `python scripts/build_feature_table.py` first.")
        return

    features = feature_table.copy()
    features["signal_date"] = pd.to_datetime(features["signal_date"])
    latest = features.sort_values("signal_date").iloc[-1]
    key_cols = [
        "signal_date",
        "atm_iv",
        "rv5",
        "rv20",
        "iv_minus_rv20",
        "iv_rank",
        "iv_percentile",
        "rv20_change_5d",
        "range_percentile_252",
        "dte",
        "strike",
        "valuation_score",
        "compression_score",
        "trigger_score",
        "liquidity_score",
    ]
    st.subheader("Latest Feature Row")
    latest_display = latest[[c for c in key_cols if c in latest.index]].to_frame("value")
    latest_display["value"] = latest_display["value"].astype(str)
    st.dataframe(latest_display, width="stretch")

    numeric_cols = [c for c in features.columns if c != "signal_date" and pd.api.types.is_numeric_dtype(features[c])]
    defaults = [c for c in ["atm_iv", "rv20", "iv_minus_rv20", "iv_rank", "rv20_change_5d"] if c in numeric_cols]
    selected_cols = st.multiselect("Feature series", numeric_cols, default=defaults)
    if selected_cols:
        st.line_chart(features.set_index("signal_date")[selected_cols])


def render_event_study(artifacts: dict[str, pd.DataFrame]):
    st.header("Event Study")
    events = artifacts.get("event_daily", pd.DataFrame())
    windows = artifacts.get("event_windows", pd.DataFrame())
    if events.empty:
        st.info("Run `python scripts/run_event_study.py` first.")
        return

    events = events.copy()
    events["event_date"] = pd.to_datetime(events["event_date"])
    labels = [
        f"{row.event_date.date()} | pnl={row.daily_pnl:,.0f} | trades={row.contributing_trades}"
        for row in events.itertuples()
    ]
    choice = st.selectbox("Top daily PnL event", labels)
    event = events.iloc[labels.index(choice)]
    event_display = event.to_frame("value")
    event_display["value"] = event_display["value"].astype(str)
    st.dataframe(event_display, width="stretch")

    if not windows.empty:
        windows = windows.copy()
        windows["event_date"] = pd.to_datetime(windows["event_date"])
        window = windows.loc[
            (windows["event_date"] == event["event_date"]) & (windows["event_type"] == event["event_type"])
        ].copy()
        if not window.empty:
            chart_cols = [
                col
                for col in ["atm_iv", "rv20", "iv_minus_rv20", "rv20_change_5d", "old_vol_long_score"]
                if col in window.columns
            ]
            st.subheader("T-10 to T+5 Feature Window")
            st.dataframe(window[["relative_day", "signal_date", *chart_cols]], width="stretch")
            if chart_cols:
                st.line_chart(window.set_index("relative_day")[chart_cols])


def render_rule_lab(feature_table: pd.DataFrame, label_table: pd.DataFrame, trade_details: pd.DataFrame):
    st.header("Rule Lab")
    if feature_table.empty or label_table.empty or trade_details.empty:
        st.info("Run feature/label scripts first.")
        return

    rule_by_name = {rule["name"]: rule for rule in DEFAULT_RULES}
    selected_names = st.multiselect("Rules", list(rule_by_name), default=list(rule_by_name)[:2])
    mode = st.selectbox("Execution mode", ["daily_rolling", "non_overlapping", "one_position_at_a_time"])
    selected_rules = [rule_by_name[name] for name in selected_names]
    if not selected_rules:
        st.info("Select at least one rule.")
        return

    summary = run_timing_experiments(feature_table, label_table, trade_details, selected_rules, modes=[mode])
    if "holding_days" in summary.columns:
        summary["holding_days"] = summary["holding_days"].astype(str)
    st.subheader("Experiment Summary")
    st.dataframe(summary, width="stretch")
    st.subheader("Selected Rule Definitions")
    st.json(selected_rules)


def render_score_components(feature_table: pd.DataFrame):
    st.header("Score Components")
    if feature_table.empty:
        st.info("Run `python scripts/build_feature_table.py` first.")
        return

    features = feature_table.copy()
    features["signal_date"] = pd.to_datetime(features["signal_date"])
    score_cols = [
        "valuation_score",
        "compression_score",
        "trigger_score",
        "liquidity_score",
        "old_vol_long_score",
    ]
    latest = features.sort_values("signal_date").iloc[-1]
    cols = st.columns(4)
    cols[0].metric("Valuation", fmt_score(latest.get("valuation_score")))
    cols[1].metric("Compression", fmt_score(latest.get("compression_score")))
    cols[2].metric("Trigger", fmt_score(latest.get("trigger_score")))
    cols[3].metric("Liquidity", fmt_score(latest.get("liquidity_score")))

    existing = [col for col in score_cols if col in features.columns]
    st.line_chart(features.set_index("signal_date")[existing])
    st.dataframe(features[["signal_date", *existing]].tail(60), width="stretch")


config, underlying, reports, artifacts, source_mode = load_dashboard_data()

tab_overview, tab_feature, tab_event, tab_rule, tab_score = st.tabs(
    ["Overview", "Feature Lab", "Event Study", "Rule Lab", "Score Components"]
)

with tab_overview:
    render_overview(config, underlying, reports, artifacts, source_mode)

with tab_feature:
    render_feature_lab(artifacts.get("feature_table", pd.DataFrame()))

with tab_event:
    render_event_study(artifacts)

with tab_rule:
    render_rule_lab(
        artifacts.get("feature_table", pd.DataFrame()),
        artifacts.get("label_table", pd.DataFrame()),
        reports.get("trade_details", pd.DataFrame()),
    )

with tab_score:
    render_score_components(artifacts.get("feature_table", pd.DataFrame()))
