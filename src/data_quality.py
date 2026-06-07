from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_SIGNAL_FIELDS = [
    "signal_call_close",
    "signal_put_close",
    "signal_call_volume",
    "signal_put_volume",
    "signal_call_open_interest",
    "signal_put_open_interest",
    "signal_straddle_close",
    "signal_straddle_premium_to_spot",
    "entry_call_open",
    "entry_put_open",
    "entry_straddle_open",
    "exit_call_close",
    "exit_put_close",
    "exit_straddle_close",
]

BID_ASK_FIELDS = [
    "signal_call_bid",
    "signal_call_ask",
    "signal_put_bid",
    "signal_put_ask",
    "call_bid_ask_spread",
    "put_bid_ask_spread",
]

DATA_QUALITY_FIELDS = [*REQUIRED_SIGNAL_FIELDS, *BID_ASK_FIELDS]

FIELD_SOURCE = {
    "signal_call_close": "real_provider_quote",
    "signal_put_close": "real_provider_quote",
    "signal_call_volume": "real_provider_quote",
    "signal_put_volume": "real_provider_quote",
    "signal_call_open_interest": "real_provider_quote",
    "signal_put_open_interest": "real_provider_quote",
    "signal_straddle_close": "derived_from_signal_call_put_close",
    "signal_straddle_premium_to_spot": "derived_from_signal_straddle_close_and_spot",
    "entry_call_open": "real_provider_quote_or_legacy_entry_proxy",
    "entry_put_open": "real_provider_quote_or_legacy_entry_proxy",
    "entry_straddle_open": "derived_from_entry_call_put_open",
    "exit_call_close": "real_provider_quote_or_legacy_exit_price",
    "exit_put_close": "real_provider_quote_or_legacy_exit_price",
    "exit_straddle_close": "derived_from_exit_call_put_close",
    "signal_call_bid": "reserved_bid_ask_provider_quote",
    "signal_call_ask": "reserved_bid_ask_provider_quote",
    "signal_put_bid": "reserved_bid_ask_provider_quote",
    "signal_put_ask": "reserved_bid_ask_provider_quote",
    "call_bid_ask_spread": "derived_from_bid_ask",
    "put_bid_ask_spread": "derived_from_bid_ask",
}


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def ensure_data_quality_columns(trades: pd.DataFrame) -> pd.DataFrame:
    """Return trade rows with v0.3 data-quality fields present.

    Missing signal-date fields are left as NaN. Legacy entry/exit prices are
    only used where they are defensible proxies for open/close fields.
    """

    output = trades.copy()
    for column in DATA_QUALITY_FIELDS:
        if column not in output.columns:
            output[column] = np.nan

    if "entry_mode_used" in output.columns:
        next_open = output["entry_mode_used"].astype(str).str.lower().eq("next_open")
        output.loc[next_open, "entry_call_open"] = output.loc[next_open, "entry_call_open"].combine_first(
            _num(output, "entry_call_price").loc[next_open]
        )
        output.loc[next_open, "entry_put_open"] = output.loc[next_open, "entry_put_open"].combine_first(
            _num(output, "entry_put_price").loc[next_open]
        )

    output["entry_straddle_open"] = output["entry_straddle_open"].combine_first(
        _num(output, "entry_call_open") + _num(output, "entry_put_open")
    )
    output["exit_call_close"] = output["exit_call_close"].combine_first(_num(output, "exit_call_price"))
    output["exit_put_close"] = output["exit_put_close"].combine_first(_num(output, "exit_put_price"))
    output["exit_straddle_close"] = output["exit_straddle_close"].combine_first(
        _num(output, "exit_call_close") + _num(output, "exit_put_close")
    )
    output["signal_straddle_close"] = output["signal_straddle_close"].combine_first(
        _num(output, "signal_call_close") + _num(output, "signal_put_close")
    )
    output["signal_straddle_premium_to_spot"] = output["signal_straddle_premium_to_spot"].combine_first(
        _num(output, "signal_straddle_close") / _num(output, "spot_at_signal").replace(0, np.nan)
    )
    output["call_bid_ask_spread"] = output["call_bid_ask_spread"].combine_first(
        _num(output, "signal_call_ask") - _num(output, "signal_call_bid")
    )
    output["put_bid_ask_spread"] = output["put_bid_ask_spread"].combine_first(
        _num(output, "signal_put_ask") - _num(output, "signal_put_bid")
    )
    return output


def audit_data_quality(trades: pd.DataFrame, original_columns: set[str] | None = None) -> pd.DataFrame:
    original_columns = original_columns or set(trades.columns)
    normalized = ensure_data_quality_columns(trades)
    row_count = len(normalized)
    rows = []
    for column in DATA_QUALITY_FIELDS:
        non_null = int(normalized[column].notna().sum())
        rows.append(
            {
                "field": column,
                "source_type": FIELD_SOURCE[column],
                "present_in_input": column in original_columns,
                "non_null_count": non_null,
                "missing_count": int(row_count - non_null),
                "completeness": float(non_null / row_count) if row_count else np.nan,
            }
        )
    return pd.DataFrame(rows)


def render_data_quality_report(audit: pd.DataFrame, row_count: int) -> str:
    if audit.empty:
        return "# Data Quality Report\n\nNo trade rows were available.\n"

    required = audit.loc[audit["field"].isin(REQUIRED_SIGNAL_FIELDS)]
    bid_ask = audit.loc[audit["field"].isin(BID_ASK_FIELDS)]
    required_rate = required["completeness"].mean()
    signal_closes = audit.loc[audit["field"].isin(["signal_call_close", "signal_put_close"]), "completeness"].mean()

    lines = [
        "# Data Quality Report",
        "",
        "## Conclusion",
        "",
        f"- Audited trade rows: {row_count:,}.",
        f"- Required v0.3 field average completeness: {required_rate:.2%}.",
        f"- Signal-date call/put close completeness: {signal_closes:.2%}.",
        "- Bid/ask fields are reserved and may be fully missing when the provider does not supply bid/ask.",
        "- Legacy v0.2 rows can backfill entry/exit open/close proxies, but they cannot recover true signal-date call/put closes.",
        "",
        "## Field Source Map",
        "",
        "| field | source_type | present_in_input | completeness |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in audit.itertuples(index=False):
        lines.append(
            f"| {row.field} | {row.source_type} | {bool(row.present_in_input)} | {float(row.completeness):.2%} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `real_provider_quote` fields are true Wind/provider quote fields when produced by the v0.3 backtest.",
            "- `real_provider_quote_or_legacy_entry_proxy` and `real_provider_quote_or_legacy_exit_price` are true fields in v0.3, but old rows may use the legacy `entry_*_price` or `exit_*_price` columns.",
            "- `derived_*` fields are arithmetic fields built from real/proxy inputs.",
            "- Fully missing signal-date close fields mean `signal_straddle_premium_to_spot` is not reliable for old v0.2 rows.",
        ]
    )
    return "\n".join(lines) + "\n"
