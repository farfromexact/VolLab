import math

import pandas as pd

from src.data_quality import audit_data_quality, ensure_data_quality_columns


def test_missing_quality_fields_do_not_crash_and_legacy_entry_exit_backfill():
    trades = pd.DataFrame(
        [
            {
                "signal_date": "2024-01-02",
                "entry_mode_used": "next_open",
                "entry_call_price": 10.0,
                "entry_put_price": 12.0,
                "exit_call_price": 8.0,
                "exit_put_price": 15.0,
                "spot_at_signal": 100.0,
            }
        ]
    )

    normalized = ensure_data_quality_columns(trades)
    audit = audit_data_quality(normalized, original_columns=set(trades.columns))

    assert math.isclose(normalized.loc[0, "entry_straddle_open"], 22.0)
    assert math.isclose(normalized.loc[0, "exit_straddle_close"], 23.0)
    assert pd.isna(normalized.loc[0, "signal_call_close"])
    assert audit.loc[audit["field"].eq("signal_call_close"), "completeness"].iloc[0] == 0.0

