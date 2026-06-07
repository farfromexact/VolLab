from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

import pandas as pd

from src.instruments import to_timestamp


class DataProvider(ABC):
    """Unified market data interface used by backtests and dashboards."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def get_trading_calendar(self, start_date, end_date) -> pd.DataFrame:
        """Return a DataFrame with one `date` column."""

    @abstractmethod
    def get_underlying_daily(self, start_date, end_date) -> pd.DataFrame:
        """Return date, open, high, low, close, volume."""

    @abstractmethod
    def get_option_chain(self, date) -> pd.DataFrame:
        """Return option rows available on `date`."""

    @abstractmethod
    def get_option_daily(self, option_codes: Iterable[str], start_date, end_date) -> pd.DataFrame:
        """Return daily bars for the requested option codes."""


def filter_date_range(df: pd.DataFrame, start_date, end_date, column: str = "date") -> pd.DataFrame:
    start = to_timestamp(start_date)
    end = to_timestamp(end_date)
    dates = pd.to_datetime(df[column]).dt.normalize()
    return df.loc[(dates >= start) & (dates <= end)].copy()


def require_columns(df: pd.DataFrame, columns: Iterable[str], frame_name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{frame_name} is missing required columns: {missing}")

