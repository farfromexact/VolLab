from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_classifier import classify_events, summarize_event_types
from src.instruments import load_config, resolve_project_path


def _read_csv(path: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    full_path = resolve_project_path(path)
    if not full_path.exists():
        return pd.DataFrame()
    return pd.read_csv(full_path, parse_dates=parse_dates)


def main() -> None:
    config = load_config()
    trades = _read_csv("data/processed/trade_details.csv", ["signal_date", "entry_date", "exit_date"])
    if trades.empty:
        raise FileNotFoundError("Missing or empty data/processed/trade_details.csv. Run scripts/run_backtest.py first.")
    labels = _read_csv("data/processed/label_table_by_horizon.csv", ["signal_date"])
    if labels.empty:
        labels = _read_csv("data/processed/label_table.csv", ["signal_date"])
    features = _read_csv("data/processed/feature_table.csv", ["signal_date"])

    events = classify_events(trades, labels, features, config)
    summary = summarize_event_types(events, trades)

    processed_dir = resolve_project_path("data/processed")
    reports_dir = resolve_project_path("reports")
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    event_path = processed_dir / "event_classification.csv"
    summary_path = reports_dir / "event_type_summary.csv"
    events.to_csv(event_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {event_path} rows={len(events):,}")
    print(f"Wrote {summary_path} rows={len(summary):,}")


if __name__ == "__main__":
    main()
