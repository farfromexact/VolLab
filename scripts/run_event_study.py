from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_study import top_daily_pnl_events, top_trade_events
from src.instruments import resolve_project_path


def _read_csv(name: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = resolve_project_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path, parse_dates=parse_dates)


def main() -> None:
    trade_details = _read_csv("data/processed/trade_details.csv", ["signal_date", "entry_date", "exit_date"])
    feature_table = _read_csv("data/processed/feature_table.csv", ["signal_date"])

    daily_events, daily_windows = top_daily_pnl_events(trade_details, feature_table, top_n=10)
    trade_events, trade_windows = top_trade_events(trade_details, feature_table, top_n=10)

    reports_dir = resolve_project_path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    daily_events.to_csv(reports_dir / "event_study_top_daily_pnl.csv", index=False)
    trade_events.to_csv(reports_dir / "event_study_top_trades.csv", index=False)
    pd.concat([daily_windows, trade_windows], ignore_index=True).to_csv(reports_dir / "event_study_windows.csv", index=False)

    print(f"Wrote {reports_dir / 'event_study_top_daily_pnl.csv'} rows={len(daily_events):,}")
    print(f"Wrote {reports_dir / 'event_study_top_trades.csv'} rows={len(trade_events):,}")


if __name__ == "__main__":
    main()

