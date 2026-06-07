from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from functools import lru_cache

import numpy as np
import pandas as pd

from src.data_provider import DataProvider, filter_date_range
from src.instruments import to_timestamp
from src.option_pricer import bs_price


class MockDataProvider(DataProvider):
    """Deterministic mock daily data provider for end-to-end local runs."""

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
        "implied_vol",
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.start_date = to_timestamp(config.get("mock_start_date", "2022-01-03"))
        self.end_date = to_timestamp(config.get("mock_end_date", "2024-12-31"))
        self.seed = int(config.get("mock_seed", 42))
        self.risk_free_rate = float(config.get("risk_free_rate", 0.02))
        self.option_prefix = str(config.get("option_prefix", "MO"))
        self.strike_step = int(config.get("mock_strike_step", 50))
        self._calendar = self._build_calendar()
        self._underlying = self._build_underlying()
        self._underlying_by_date = self._underlying.set_index("date")
        self._expiries = self._build_expiries()

    def _build_calendar(self) -> pd.DataFrame:
        dates = pd.bdate_range(self.start_date, self.end_date)
        return pd.DataFrame({"date": dates.normalize()})

    def _build_underlying(self) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed)
        dates = self._calendar["date"]
        n = len(dates)
        t = np.arange(n)
        daily_vol = 0.012 + 0.004 * (np.sin(t / 45.0) + 1.0) / 2.0
        returns = rng.normal(loc=0.0001, scale=daily_vol, size=n)
        close = float(self.config.get("mock_start_price", 5000)) * np.exp(np.cumsum(returns))
        open_ = np.empty(n)
        open_[0] = close[0] * (1.0 + rng.normal(0, 0.003))
        open_[1:] = close[:-1] * (1.0 + rng.normal(0, 0.004, size=n - 1))
        intraday_range = np.abs(rng.normal(0.008, 0.003, size=n))
        high = np.maximum(open_, close) * (1.0 + intraday_range)
        low = np.minimum(open_, close) * (1.0 - intraday_range)
        volume = rng.integers(2_000_000, 8_000_000, size=n)
        return pd.DataFrame(
            {
                "date": dates,
                "open": open_.round(2),
                "high": high.round(2),
                "low": low.round(2),
                "close": close.round(2),
                "volume": volume,
            }
        )

    def _build_expiries(self) -> list[pd.Timestamp]:
        end = self.end_date + pd.DateOffset(months=3)
        expiries: list[pd.Timestamp] = []
        for period in pd.period_range(self.start_date, end, freq="M"):
            business_days = pd.bdate_range(period.start_time, period.end_time)
            wednesdays = [d for d in business_days if d.weekday() == 2]
            expiry = pd.Timestamp(wednesdays[-1] if wednesdays else business_days[-1]).normalize()
            if expiry >= self.start_date:
                expiries.append(expiry)
        return expiries

    def _stable_unit(self, key: str) -> float:
        payload = f"{self.seed}|{key}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        return int.from_bytes(digest[:8], "big") / float(2**64 - 1)

    def _stable_noise(self, key: str, scale: float) -> float:
        return (self._stable_unit(key) - 0.5) * 2.0 * scale

    def _option_code(self, expiry: pd.Timestamp, strike: float, call_put: str) -> str:
        return f"{self.option_prefix}_{expiry:%y%m%d}_{int(round(strike)):05d}_{call_put}"

    def _parse_option_code(self, option_code: str) -> tuple[pd.Timestamp, float, str]:
        parts = str(option_code).split("_")
        if len(parts) != 4:
            raise ValueError(f"Unsupported mock option code: {option_code!r}")
        expiry = pd.to_datetime(parts[1], format="%y%m%d").normalize()
        strike = float(parts[2])
        call_put = parts[3].upper()
        if call_put not in {"C", "P"}:
            raise ValueError(f"Unsupported option type in code: {option_code!r}")
        return expiry, strike, call_put

    def _active_expiries(self, current: pd.Timestamp) -> list[pd.Timestamp]:
        max_dte = max(int(self.config.get("max_dte", 35)) + 10, int(self.config.get("roll_dte_threshold", 7)) + 30, 45)
        return [expiry for expiry in self._expiries if 0 < (expiry - current).days <= max_dte]

    def _strike_grid(self, spot: float) -> list[float]:
        width = float(self.config.get("mock_strike_width", 0.12))
        low = math.floor(spot * (1.0 - width) / self.strike_step) * self.strike_step
        high = math.ceil(spot * (1.0 + width) / self.strike_step) * self.strike_step
        return [float(k) for k in range(max(self.strike_step, low), high + self.strike_step, self.strike_step)]

    def _mock_iv(self, current: pd.Timestamp, expiry: pd.Timestamp, strike: float, spot: float) -> float:
        dte = max((expiry - current).days, 1)
        day_angle = 2.0 * math.pi * current.dayofyear / 365.25
        seasonal = 0.035 * math.sin(day_angle)
        term = 0.015 * math.sqrt(min(dte, 90) / 90.0)
        moneyness = math.log(max(strike, 1.0) / max(spot, 1.0))
        skew = 0.09 * max(-moneyness, 0.0) + 0.04 * abs(moneyness)
        noise = self._stable_noise(f"iv|{current:%Y%m%d}|{expiry:%Y%m%d}|{strike:.0f}", 0.012)
        return float(np.clip(0.21 + seasonal + term + skew + noise, 0.08, 0.65))

    @lru_cache(maxsize=250_000)
    def _quote(self, current: pd.Timestamp, expiry: pd.Timestamp, strike: float, call_put: str) -> dict:
        if current not in self._underlying_by_date.index:
            raise KeyError(f"No underlying price for {current.date()}")
        spot = float(self._underlying_by_date.loc[current, "close"])
        dte = max((expiry - current).days, 0)
        iv = self._mock_iv(current, expiry, strike, spot)
        T = max(dte / 252.0, 1.0 / 252.0)
        fair = bs_price(spot, strike, T, self.risk_free_rate, iv, call_put)
        close = max(fair * (1.0 + self._stable_noise(f"close|{current}|{strike}|{call_put}", 0.012)), 0.01)
        open_ = max(fair * (1.0 + self._stable_noise(f"open|{current}|{strike}|{call_put}", 0.018)), 0.01)
        high = max(open_, close) * (1.0 + abs(self._stable_noise(f"high|{current}|{strike}|{call_put}", 0.018)))
        low = max(min(open_, close) * (1.0 - abs(self._stable_noise(f"low|{current}|{strike}|{call_put}", 0.018))), 0.01)
        distance = abs(strike / spot - 1.0)
        liquidity = max(0.05, 1.0 - distance / 0.18) * max(0.2, 1.0 - dte / 140.0)
        volume = int(max(0, 60 + 1500 * liquidity + self._stable_noise(f"vol|{current}|{strike}|{call_put}", 80)))
        open_interest = int(max(0, 500 + 6000 * liquidity + self._stable_noise(f"oi|{current}|{strike}|{call_put}", 250)))
        return {
            "date": current,
            "option_code": self._option_code(expiry, strike, call_put),
            "call_put": call_put,
            "strike": float(strike),
            "expire_date": expiry,
            "open": round(open_, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": volume,
            "open_interest": open_interest,
            "implied_vol": round(iv, 6),
        }

    def get_trading_calendar(self, start_date, end_date) -> pd.DataFrame:
        return filter_date_range(self._calendar, start_date, end_date).sort_values("date").reset_index(drop=True)

    def get_underlying_daily(self, start_date, end_date) -> pd.DataFrame:
        return filter_date_range(self._underlying, start_date, end_date).sort_values("date").reset_index(drop=True)

    def get_option_chain(self, date) -> pd.DataFrame:
        current = to_timestamp(date)
        if current not in self._underlying_by_date.index:
            return pd.DataFrame(columns=self.OPTION_COLUMNS)
        spot = float(self._underlying_by_date.loc[current, "close"])
        rows = []
        for expiry in self._active_expiries(current):
            for strike in self._strike_grid(spot):
                rows.append(self._quote(current, expiry, strike, "C"))
                rows.append(self._quote(current, expiry, strike, "P"))
        return pd.DataFrame(rows, columns=self.OPTION_COLUMNS)

    def get_option_daily(self, option_codes: Iterable[str], start_date, end_date) -> pd.DataFrame:
        codes = list(dict.fromkeys(option_codes))
        if not codes:
            return pd.DataFrame(columns=self.OPTION_COLUMNS)
        calendar = self.get_trading_calendar(start_date, end_date)["date"]
        rows = []
        for option_code in codes:
            expiry, strike, call_put = self._parse_option_code(option_code)
            for current in calendar:
                current = pd.Timestamp(current).normalize()
                if current <= expiry:
                    rows.append(self._quote(current, expiry, strike, call_put))
        return pd.DataFrame(rows, columns=self.OPTION_COLUMNS).sort_values(["option_code", "date"]).reset_index(drop=True)

    def generate_option_daily_export(self, start_date=None, end_date=None) -> pd.DataFrame:
        start = to_timestamp(start_date or self.start_date)
        end = to_timestamp(end_date or self.end_date)
        rows = []
        for current in self.get_trading_calendar(start, end)["date"]:
            chain = self.get_option_chain(current)
            if not chain.empty:
                rows.append(chain)
        if not rows:
            return pd.DataFrame(columns=self.OPTION_COLUMNS)
        return pd.concat(rows, ignore_index=True)
