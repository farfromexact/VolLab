from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

import numpy as np
import pandas as pd

from src.data_provider import DataProvider, filter_date_range
from src.instruments import coerce_date_columns, to_timestamp


class WindDataProvider(DataProvider):
    """
    WindPy-backed provider.

    Wind field names and query templates are read from `config.yaml`. If your Wind
    terminal returns different field names, confirm them with the Wind code
    generator and update `wind.fields` / `wind_field_mapping` rather than changing
    strategy code.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        try:
            from WindPy import w  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "WindPy is not available. Install/configure WindPy, or use data_mode='mock' "
                "or data_mode='csv'."
            ) from exc
        self.w = w
        self.wind_config = config.get("wind", {})
        self.field_mapping = config.get("wind_field_mapping", {})
        self.option_prefix = str(config.get("option_prefix", "")).upper()
        self._chain_cache: dict[pd.Timestamp, pd.DataFrame] = {}
        self._option_meta: dict[str, dict[str, Any]] = {}
        self._underlying_cache: dict[pd.Timestamp, dict[str, Any]] = {}
        self._expiry_cache: dict[str, pd.Timestamp] = {}

        result = self.w.start()
        if getattr(result, "ErrorCode", 0) != 0:
            message = self._wind_message(result)
            raise ConnectionError(
                "WindPy start failed. Confirm Wind terminal is logged in and run this process outside "
                f"the restricted sandbox if needed. Wind message: {message}"
            )

    def _wind_message(self, result) -> str:
        data = getattr(result, "Data", None)
        if data:
            return str(data[0])
        return str(result)

    def _check(self, result, context: str) -> None:
        error_code = getattr(result, "ErrorCode", 0)
        if error_code != 0:
            raise RuntimeError(f"Wind {context} failed: ErrorCode={error_code}, message={self._wind_message(result)}")

    def _fields(self, group: str) -> dict[str, str]:
        wind_fields = self.wind_config.get("fields", {})
        return dict(wind_fields.get(group, {}))

    def _mapping(self, group: str) -> dict[str, str]:
        nested = dict(self.field_mapping.get(group, {}))
        wind_nested = self.wind_config.get("fields", {}).get(group, {})
        if group == "option_chain":
            merged = dict(wind_nested)
            merged.update(nested)
            return merged
        return nested

    def _options(self, key: str) -> str:
        return str(self.wind_config.get(key, ""))

    def _frame_from_wsd_single_code(self, result, output_to_wind_field: dict[str, str]) -> pd.DataFrame:
        self._check(result, "wsd")
        frame = pd.DataFrame({"date": pd.to_datetime(result.Times).normalize()})
        wind_fields = [str(field).upper() for field in result.Fields]
        for output_col, wind_field in output_to_wind_field.items():
            field_upper = str(wind_field).upper()
            frame[output_col] = result.Data[wind_fields.index(field_upper)] if field_upper in wind_fields else np.nan
        return frame

    def _frame_from_wset(self, result) -> pd.DataFrame:
        self._check(result, "wset")
        if not getattr(result, "Fields", None) or not getattr(result, "Data", None):
            return pd.DataFrame()
        return pd.DataFrame({str(field): values for field, values in zip(result.Fields, result.Data)})

    def _column(self, frame: pd.DataFrame, configured_name: str) -> pd.Series:
        columns = {str(column).lower(): column for column in frame.columns}
        key = str(configured_name).lower()
        if key not in columns:
            return pd.Series([np.nan] * len(frame), index=frame.index)
        return frame[columns[key]]

    def _format_date(self, value) -> str:
        return to_timestamp(value).strftime("%Y-%m-%d")

    def _normalize_call_put(self, option_code: Any, raw_value: Any = None) -> str | None:
        raw = str(raw_value).upper() if raw_value is not None and pd.notna(raw_value) else ""
        if raw in {"C", "CALL"} or "CALL" in raw:
            return "C"
        if raw in {"P", "PUT"} or "PUT" in raw:
            return "P"
        match = re.search(r"-([CP])-", str(option_code).upper())
        if match:
            return match.group(1)
        return None

    def _parse_strike_from_code(self, option_code: str) -> float:
        match = re.search(r"-[CP]-([0-9]+(?:\.[0-9]+)?)", str(option_code).upper())
        return float(match.group(1)) if match else np.nan

    def _filter_prefix(self, codes: pd.Series) -> pd.Series:
        if not self.option_prefix:
            return pd.Series([True] * len(codes), index=codes.index)
        return codes.astype(str).str.upper().str.startswith(self.option_prefix)

    def _spot_on_date(self, date: pd.Timestamp) -> float:
        current = to_timestamp(date)
        if current not in self._underlying_cache:
            daily = self.get_underlying_daily(current, current)
            if daily.empty:
                return np.nan
        cached = self._underlying_cache.get(current, {})
        return float(cached.get("close", np.nan))

    def _month_expiry(self, period: pd.Period) -> pd.Timestamp:
        key = str(period)
        if key in self._expiry_cache:
            return self._expiry_cache[key]
        month_days = pd.date_range(period.start_time, period.end_time, freq="D")
        fridays = [day for day in month_days if day.weekday() == 4]
        target = pd.Timestamp(fridays[2] if len(fridays) >= 3 else fridays[-1]).normalize()
        trading_days = self.get_trading_calendar(period.start_time, target)
        if trading_days.empty:
            expiry = target
        else:
            expiry = pd.Timestamp(trading_days["date"].iloc[-1]).normalize()
        self._expiry_cache[key] = expiry
        return expiry

    def _synthetic_expiries(self, current: pd.Timestamp) -> list[pd.Timestamp]:
        chain_config = self.wind_config.get("option_chain", {})
        months_ahead = int(chain_config.get("months_ahead", 4))
        max_dte = int(self.config.get("max_dte", 35))
        expiries: list[pd.Timestamp] = []
        start_period = pd.Period(current, freq="M")
        for offset in range(months_ahead):
            expiry = self._month_expiry(start_period + offset)
            dte = (expiry - current).days
            if 0 < dte <= max_dte:
                expiries.append(expiry)
        return expiries

    def _synthetic_strikes(self, spot: float) -> list[int]:
        chain_config = self.wind_config.get("option_chain", {})
        step = int(chain_config.get("strike_step", 100))
        pct_range = float(chain_config.get("strike_pct_range", 0.18))
        low = int(np.floor(float(spot) * (1.0 - pct_range) / step) * step)
        high = int(np.ceil(float(spot) * (1.0 + pct_range) / step) * step)
        return list(range(max(step, low), high + step, step))

    def _synthetic_option_code(self, expiry: pd.Timestamp, call_put: str, strike: int) -> str:
        chain_config = self.wind_config.get("option_chain", {})
        template = str(chain_config.get("code_template", "{option_prefix}{yymm}-{call_put}-{strike}.{exchange_suffix}"))
        return template.format(
            option_prefix=self.option_prefix,
            yymm=expiry.strftime("%y%m"),
            call_put=call_put,
            strike=int(strike),
            exchange_suffix=str(chain_config.get("exchange_suffix", "CFE")),
        )

    def _synthetic_option_chain(self, date: pd.Timestamp) -> pd.DataFrame:
        current = to_timestamp(date)
        spot = self._spot_on_date(current)
        if not np.isfinite(spot) or spot <= 0:
            return pd.DataFrame()

        rows = []
        for expiry in self._synthetic_expiries(current):
            for strike in self._synthetic_strikes(spot):
                for call_put in ["C", "P"]:
                    option_code = self._synthetic_option_code(expiry, call_put, strike)
                    rows.append(
                        {
                            "date": current,
                            "option_code": option_code,
                            "call_put": call_put,
                            "strike": float(strike),
                            "expire_date": expiry,
                        }
                    )
        meta = pd.DataFrame(rows)
        if meta.empty:
            return meta
        quotes = self._option_quote_snapshot(meta["option_code"].tolist(), current)
        output = meta.merge(quotes, on=["date", "option_code"], how="left")
        for column in ["open", "high", "low", "close", "volume", "open_interest"]:
            if column not in output.columns:
                output[column] = np.nan
        output = output.loc[pd.to_numeric(output["close"], errors="coerce").notna()].copy()
        for _, row in output.iterrows():
            self._option_meta[str(row["option_code"])] = {
                "call_put": row["call_put"],
                "strike": float(row["strike"]),
                "expire_date": row["expire_date"],
            }
        return output[
            [
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
        ].sort_values(["expire_date", "strike", "call_put"]).reset_index(drop=True)

    def _option_quote_snapshot(self, option_codes: list[str], date: pd.Timestamp) -> pd.DataFrame:
        fields = self._fields("option_quote")
        if not option_codes:
            return pd.DataFrame(columns=["date", "option_code", *fields.keys()])

        field_names = list(fields.values())
        field_request = ",".join(field_names)
        option_bits = [f"tradeDate={self._format_date(date)}"]
        extra_options = self._options("wss_options")
        if extra_options:
            option_bits.append(extra_options)
        options = ";".join(option_bits)

        chunks = [option_codes[i : i + 80] for i in range(0, len(option_codes), 80)]
        frames = []
        for chunk in chunks:
            result = self.w.wss(",".join(chunk), field_request, options)
            self._check(result, "wss option quote")
            quote = pd.DataFrame({"date": date, "option_code": list(result.Codes)})
            result_fields = [str(field).upper() for field in result.Fields]
            for output_col, wind_field in fields.items():
                field_upper = str(wind_field).upper()
                quote[output_col] = result.Data[result_fields.index(field_upper)] if field_upper in result_fields else np.nan
            frames.append(quote)
        if not frames:
            return pd.DataFrame(columns=["date", "option_code", *fields.keys()])
        return pd.concat(frames, ignore_index=True)

    def get_trading_calendar(self, start_date, end_date) -> pd.DataFrame:
        result = self.w.tdays(self._format_date(start_date), self._format_date(end_date), self._options("tdays_options"))
        self._check(result, "tdays")
        return pd.DataFrame({"date": pd.to_datetime(result.Data[0]).normalize()})

    def get_underlying_daily(self, start_date, end_date) -> pd.DataFrame:
        fields = self._fields("underlying_daily")
        if not fields:
            raise ValueError("wind.fields.underlying_daily is not configured")
        result = self.w.wsd(
            self.config.get("underlying_code"),
            ",".join(fields.values()),
            self._format_date(start_date),
            self._format_date(end_date),
            self._options("wsd_options"),
        )
        frame = self._frame_from_wsd_single_code(result, fields)
        for _, row in frame.iterrows():
            self._underlying_cache[pd.Timestamp(row["date"]).normalize()] = row.to_dict()
        return coerce_date_columns(frame, ["date"]).sort_values("date").reset_index(drop=True)

    def get_option_chain(self, date) -> pd.DataFrame:
        current = to_timestamp(date)
        if current in self._chain_cache:
            return self._chain_cache[current].copy()

        chain_config = self.wind_config.get("option_chain", {})
        if bool(chain_config.get("prefer_synthetic", False)):
            output = self._synthetic_option_chain(current)
            self._chain_cache[current] = output
            return output.copy()

        dataset = str(chain_config.get("dataset", "optionchain"))
        template = str(chain_config.get("params_template", "date={date};us_code={underlying_code}"))
        params = template.format(date=self._format_date(current), underlying_code=self.config.get("underlying_code", ""))
        try:
            raw = self._frame_from_wset(self.w.wset(dataset, params))
        except RuntimeError as exc:
            if "quota exceeded" not in str(exc).lower():
                raise
            output = self._synthetic_option_chain(current)
            self._chain_cache[current] = output
            return output.copy()
        if raw.empty:
            output = pd.DataFrame(
                columns=[
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
            )
            self._chain_cache[current] = output
            return output.copy()

        mapping = self._mapping("option_chain")
        option_code = self._column(raw, mapping.get("option_code", "option_code")).astype(str)
        meta = pd.DataFrame(
            {
                "date": current,
                "option_code": option_code,
                "call_put": [
                    self._normalize_call_put(code, raw_value)
                    for code, raw_value in zip(option_code, self._column(raw, mapping.get("call_put", "call_put")))
                ],
                "strike": pd.to_numeric(self._column(raw, mapping.get("strike", "strike_price")), errors="coerce"),
                "expire_date": pd.to_datetime(self._column(raw, mapping.get("expire_date", "expiredate")), errors="coerce").dt.normalize(),
            }
        )
        meta = meta.loc[self._filter_prefix(meta["option_code"])].dropna(subset=["option_code", "call_put", "strike", "expire_date"])
        if meta.empty:
            self._chain_cache[current] = meta
            return meta.copy()

        for _, row in meta.iterrows():
            self._option_meta[str(row["option_code"])] = {
                "call_put": row["call_put"],
                "strike": float(row["strike"]),
                "expire_date": row["expire_date"],
            }

        quotes = self._option_quote_snapshot(meta["option_code"].tolist(), current)
        output = meta.merge(quotes, on=["date", "option_code"], how="left")
        for column in ["open", "high", "low", "close", "volume", "open_interest"]:
            if column not in output.columns:
                output[column] = np.nan
        output = output[
            [
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
        ].sort_values(["expire_date", "strike", "call_put"])
        self._chain_cache[current] = output.reset_index(drop=True)
        return self._chain_cache[current].copy()

    def get_option_daily(self, option_codes: Iterable[str], start_date, end_date) -> pd.DataFrame:
        codes = [str(code) for code in dict.fromkeys(option_codes) if code]
        fields = self._fields("option_quote")
        if not codes:
            return pd.DataFrame()
        if not fields:
            raise ValueError("wind.fields.option_quote is not configured")

        frames = []
        for code in codes:
            result = self.w.wsd(
                code,
                ",".join(fields.values()),
                self._format_date(start_date),
                self._format_date(end_date),
                self._options("wsd_options"),
            )
            frame = self._frame_from_wsd_single_code(result, fields)
            frame["option_code"] = code
            meta = self._option_meta.get(code, {})
            frame["call_put"] = meta.get("call_put") or self._normalize_call_put(code)
            frame["strike"] = meta.get("strike", self._parse_strike_from_code(code))
            frame["expire_date"] = meta.get("expire_date", pd.NaT)
            frames.append(frame)

        if not frames:
            return pd.DataFrame()
        output = pd.concat(frames, ignore_index=True)
        output = filter_date_range(output, start_date, end_date)
        return output[
            [
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
        ].sort_values(["option_code", "date"]).reset_index(drop=True)
