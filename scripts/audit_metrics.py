from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.instruments import load_config, resolve_project_path
from src.metric_audit import audit_trade_metrics


def main() -> None:
    config = load_config()
    trade_path = resolve_project_path("data/processed/trade_details.csv")
    if not trade_path.exists():
        raise FileNotFoundError(f"Missing trade details: {trade_path}")
    trade_details = pd.read_csv(trade_path)
    report = audit_trade_metrics(trade_details, config, iv_lookback=int(config.get("iv_lookback", 252)))

    reports_dir = resolve_project_path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    output = reports_dir / "metric_audit_report.md"
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

