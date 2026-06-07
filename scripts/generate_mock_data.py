from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.instruments import load_config, resolve_project_path
from src.mock_data_provider import MockDataProvider


def main() -> None:
    config = load_config()
    provider = MockDataProvider(config)
    start = config.get("mock_start_date")
    end = config.get("mock_end_date")

    paths = config.get("csv_paths", {})
    trading_calendar_path = resolve_project_path(paths.get("trading_calendar", "data/mock/trading_calendar.csv"))
    underlying_path = resolve_project_path(paths.get("underlying_daily", "data/mock/underlying_daily.csv"))
    chain_path = resolve_project_path(paths.get("option_chain", "data/mock/option_chain.csv"))
    option_daily_path = resolve_project_path(paths.get("option_daily", "data/mock/option_daily.csv"))
    for path in [trading_calendar_path, underlying_path, chain_path, option_daily_path]:
        path.parent.mkdir(parents=True, exist_ok=True)

    calendar = provider.get_trading_calendar(start, end)
    underlying = provider.get_underlying_daily(start, end)
    option_daily = provider.generate_option_daily_export(start, end)

    calendar.to_csv(trading_calendar_path, index=False)
    underlying.to_csv(underlying_path, index=False)
    option_daily.to_csv(chain_path, index=False)
    option_daily.to_csv(option_daily_path, index=False)

    print(f"Wrote {len(calendar):,} trading days to {trading_calendar_path}")
    print(f"Wrote {len(underlying):,} underlying bars to {underlying_path}")
    print(f"Wrote {len(option_daily):,} option bars to {option_daily_path}")


if __name__ == "__main__":
    main()

