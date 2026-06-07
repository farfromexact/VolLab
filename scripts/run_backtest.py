from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest_engine import BacktestEngine
from src.instruments import build_data_provider, load_config, resolve_project_path


def main() -> None:
    config = load_config()
    provider = build_data_provider(config)
    reports = BacktestEngine(provider, config).run()

    output_dir = resolve_project_path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in reports.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)

    summary = reports["summary"]
    print("Backtest summary")
    print(summary.to_string(index=False))
    print(f"Wrote reports to {output_dir}")


if __name__ == "__main__":
    main()

