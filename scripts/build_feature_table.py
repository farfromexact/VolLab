from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.features import build_feature_table
from src.instruments import build_data_provider, load_config, resolve_project_path
from src.labels import build_label_table
from src.score_components import add_score_components


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

    feature_table = build_feature_table(
        trade_details,
        underlying_daily=underlying,
        rv_windows=config.get("rv_windows", [5, 10, 20, 60]),
        iv_lookback=int(config.get("iv_lookback", 252)),
    )
    feature_table = add_score_components(feature_table)
    label_table = build_label_table(
        trade_details,
        underlying_daily=underlying,
        holding_days=config.get("holding_days", [1, 2, 3, 5]),
    )

    output_dir = resolve_project_path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_path = output_dir / "feature_table.csv"
    label_path = output_dir / "label_table.csv"
    feature_table.to_csv(feature_path, index=False)
    label_table.to_csv(label_path, index=False)

    print(f"Wrote feature_table: {feature_path} rows={len(feature_table):,}")
    print(f"Wrote label_table: {label_path} rows={len(label_table):,}")


if __name__ == "__main__":
    main()

