from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.instruments import build_data_provider, load_config, resolve_project_path
from src.labels_by_horizon import build_label_table_by_horizon


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _load_trade_details() -> pd.DataFrame:
    path = resolve_project_path("data/processed/trade_details.csv")
    if not path.exists():
        raise FileNotFoundError(f"Missing trade details: {path}. Run scripts/run_backtest.py first.")
    return pd.read_csv(path)


def _load_underlying(config: dict, trade_details: pd.DataFrame) -> pd.DataFrame | None:
    start = config.get("backtest_start_date") or trade_details["signal_date"].min()
    end = config.get("backtest_end_date") or trade_details["exit_date"].max()
    try:
        provider = build_data_provider(config)
        return provider.get_underlying_daily(start, end)
    except Exception as exc:
        logger.warning("Could not load underlying daily data; falling back to spot_at_signal only: %s", exc)
        return None


def main() -> None:
    config = load_config()
    trade_details = _load_trade_details()
    underlying = _load_underlying(config, trade_details)
    labels = build_label_table_by_horizon(trade_details, underlying_daily=underlying)

    output_dir = resolve_project_path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "label_table_by_horizon.csv"
    labels.to_csv(output, index=False)
    print(f"Wrote {output} rows={len(labels):,}")


if __name__ == "__main__":
    main()
