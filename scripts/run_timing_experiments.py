from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.experiment_runner import run_timing_experiments
from src.instruments import resolve_project_path
from src.rule_filters import DEFAULT_RULES


def _read_csv(name: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = resolve_project_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path, parse_dates=parse_dates)


def main() -> None:
    feature_table = _read_csv("data/processed/feature_table.csv", ["signal_date"])
    label_table = _read_csv("data/processed/label_table.csv", ["signal_date"])
    trade_details = _read_csv("data/processed/trade_details.csv", ["signal_date", "entry_date", "exit_date"])

    summary = run_timing_experiments(feature_table, label_table, trade_details, DEFAULT_RULES)
    reports_dir = resolve_project_path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    output = reports_dir / "timing_experiment_summary.csv"
    summary.to_csv(output, index=False)
    print(f"Wrote {output} rows={len(summary):,}")


if __name__ == "__main__":
    main()

