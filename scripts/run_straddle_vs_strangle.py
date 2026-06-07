from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_classifier import classify_events, summarize_event_types
from src.instruments import build_data_provider, load_config, resolve_project_path
from src.strategy_strangle import run_strangle_strategy, summarize_straddle_vs_strangle


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _read_csv(path: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    full_path = resolve_project_path(path)
    if not full_path.exists():
        return pd.DataFrame()
    return pd.read_csv(full_path, parse_dates=parse_dates)


def _load_or_build_events(trades: pd.DataFrame, config: dict) -> pd.DataFrame:
    event_path = resolve_project_path("data/processed/event_classification.csv")
    if event_path.exists():
        return pd.read_csv(event_path, parse_dates=["signal_date"])
    labels = _read_csv("data/processed/label_table_by_horizon.csv", ["signal_date"])
    if labels.empty:
        labels = _read_csv("data/processed/label_table.csv", ["signal_date"])
    features = _read_csv("data/processed/feature_table.csv", ["signal_date"])
    events = classify_events(trades, labels, features, config)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(event_path, index=False)
    reports_dir = resolve_project_path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    summarize_event_types(events, trades).to_csv(reports_dir / "event_type_summary.csv", index=False)
    return events


def _try_run_provider_strangles(config: dict) -> pd.DataFrame:
    try:
        provider = build_data_provider(config)
        return run_strangle_strategy(provider, config)
    except Exception as exc:
        logger.warning("Could not build provider-backed OTM strangles; summary will mark OTM rows unavailable: %s", exc)
        return pd.DataFrame()


def main() -> None:
    config = load_config()
    trades = _read_csv("data/processed/trade_details.csv", ["signal_date", "entry_date", "exit_date"])
    if trades.empty:
        raise FileNotFoundError("Missing or empty data/processed/trade_details.csv. Run scripts/run_backtest.py first.")
    events = _load_or_build_events(trades, config)
    strangles = _try_run_provider_strangles(config)

    reports_dir = resolve_project_path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    if not strangles.empty:
        strangles.to_csv(reports_dir / "strangle_trade_details.csv", index=False)
    summary = summarize_straddle_vs_strangle(trades, strangles, events)
    output = reports_dir / "straddle_vs_strangle_summary.csv"
    summary.to_csv(output, index=False)
    print(f"Wrote {output} rows={len(summary):,}")


if __name__ == "__main__":
    main()
