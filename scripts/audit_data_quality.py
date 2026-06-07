from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_quality import audit_data_quality, ensure_data_quality_columns, render_data_quality_report
from src.instruments import resolve_project_path


def main() -> None:
    trade_path = resolve_project_path("data/processed/trade_details.csv")
    if not trade_path.exists():
        raise FileNotFoundError(f"Missing trade details: {trade_path}. Run scripts/run_backtest.py first.")

    trades = pd.read_csv(trade_path)
    original_columns = set(trades.columns)
    normalized = ensure_data_quality_columns(trades)
    audit = audit_data_quality(normalized, original_columns=original_columns)

    processed_dir = resolve_project_path("data/processed")
    reports_dir = resolve_project_path("reports")
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    normalized.to_csv(processed_dir / "trade_details_v03_quality_fields.csv", index=False)
    audit.to_csv(reports_dir / "data_quality_fields.csv", index=False)
    report_path = reports_dir / "data_quality_report.md"
    report_path.write_text(render_data_quality_report(audit, len(trades)), encoding="utf-8")
    print(f"Wrote {report_path} rows={len(trades):,}")


if __name__ == "__main__":
    main()
