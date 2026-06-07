from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else project_root() / "config.yaml"
    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    return config


def resolve_project_path(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return project_root() / value


def to_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError(f"Invalid date value: {value!r}")
    return ts.normalize()


def coerce_date_columns(df: pd.DataFrame, columns: list[str] | tuple[str, ...]) -> pd.DataFrame:
    output = df.copy()
    for column in columns:
        if column in output.columns:
            output[column] = pd.to_datetime(output[column]).dt.normalize()
    return output


def build_data_provider(config: dict[str, Any] | None = None):
    cfg = dict(config or load_config())
    mode = str(cfg.get("data_mode", "mock")).lower()
    if mode == "mock":
        from src.mock_data_provider import MockDataProvider

        return MockDataProvider(cfg)
    if mode == "csv":
        from src.csv_data_provider import CsvDataProvider

        return CsvDataProvider(cfg)
    if mode == "wind":
        from src.wind_data_provider import WindDataProvider

        return WindDataProvider(cfg)
    raise ValueError(f"Unsupported data_mode: {mode!r}")

