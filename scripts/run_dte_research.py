from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dte_research import run_dte_research
from src.event_classifier import classify_events, summarize_event_types
from src.instruments import load_config, resolve_project_path


def _read_csv(path: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    full_path = resolve_project_path(path)
    if not full_path.exists():
        return pd.DataFrame()
    return pd.read_csv(full_path, parse_dates=parse_dates)


def _load_or_build_events(
    trades: pd.DataFrame,
    labels: pd.DataFrame,
    features: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    event_path = resolve_project_path("data/processed/event_classification.csv")
    if event_path.exists():
        return pd.read_csv(event_path, parse_dates=["signal_date"])
    events = classify_events(trades, labels, features, config)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(event_path, index=False)
    summary = summarize_event_types(events, trades)
    reports_dir = resolve_project_path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(reports_dir / "event_type_summary.csv", index=False)
    return events


def main() -> None:
    config = load_config()
    trades = _read_csv("data/processed/trade_details.csv", ["signal_date", "entry_date", "exit_date"])
    if trades.empty:
        raise FileNotFoundError("Missing or empty data/processed/trade_details.csv. Run scripts/run_backtest.py first.")
    labels = _read_csv("data/processed/label_table_by_horizon.csv", ["signal_date"])
    if labels.empty:
        labels = _read_csv("data/processed/label_table.csv", ["signal_date"])
    features = _read_csv("data/processed/feature_table.csv", ["signal_date"])
    events = _load_or_build_events(trades, labels, features, config)

    summary = run_dte_research(trades, labels, events, features)
    output_dir = resolve_project_path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "dte_research_summary.csv"
    summary.to_csv(output, index=False)
    print(f"Wrote {output} rows={len(summary):,}")


if __name__ == "__main__":
    main()
