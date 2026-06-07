from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src.data_provider import DataProvider, filter_date_range, require_columns
from src.instruments import coerce_date_columns, resolve_project_path, to_timestamp


class CsvDataProvider(DataProvider):
    """Read unified daily option and underlying data from local CSV files."""

    UNDERLYING_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
    OPTION_COLUMNS = [
        "date",
        "option_code",
        "call_put",
        "strike",
        "expire_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_interest",
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.paths = config.get("csv_paths", {})
        self._cache: dict[str, pd.DataFrame] = {}

    def _path(self, key: str) -> Path:
        if key not in self.paths:
            raise ValueError(f"csv_paths.{key} is not configured")
        return resolve_project_path(self.paths[key])

    def _read_csv(self, key: str) -> pd.DataFrame:
        if key in self._cache:
            return self._cache[key].copy()
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found for {key}: {path}")
        df = pd.read_csv(path)
        if "date" in df.columns:
            df = coerce_date_columns(df, ["date", "expire_date"])
        self._cache[key] = df
        return df.copy()

    def get_trading_calendar(self, start_date, end_date) -> pd.DataFrame:
        try:
            calendar = self._read_csv("trading_calendar")
            require_columns(calendar, ["date"], "trading_calendar")
        except FileNotFoundError:
            underlying = self._read_csv("underlying_daily")
            require_columns(underlying, ["date"], "underlying_daily")
            calendar = underlying[["date"]].drop_duplicates()
        return filter_date_range(calendar, start_date, end_date).sort_values("date").reset_index(drop=True)

    def get_underlying_daily(self, start_date, end_date) -> pd.DataFrame:
        underlying = self._read_csv("underlying_daily")
        require_columns(underlying, self.UNDERLYING_COLUMNS, "underlying_daily")
        return filter_date_range(underlying, start_date, end_date).sort_values("date").reset_index(drop=True)

    def get_option_chain(self, date) -> pd.DataFrame:
        current = to_timestamp(date)
        try:
            chain = self._read_csv("option_chain")
        except FileNotFoundError:
            chain = self._read_csv("option_daily")
        require_columns(chain, self.OPTION_COLUMNS, "option_chain")
        dates = pd.to_datetime(chain["date"]).dt.normalize()
        return chain.loc[dates == current].copy().reset_index(drop=True)

    def get_option_daily(self, option_codes: Iterable[str], start_date, end_date) -> pd.DataFrame:
        codes = list(option_codes)
        if not codes:
            return pd.DataFrame(columns=self.OPTION_COLUMNS)
        option_daily = self._read_csv("option_daily")
        require_columns(option_daily, self.OPTION_COLUMNS, "option_daily")
        filtered = filter_date_range(option_daily, start_date, end_date)
        return filtered.loc[filtered["option_code"].isin(codes)].sort_values(["option_code", "date"]).reset_index(drop=True)

