import math

import pandas as pd

from src.labels import build_label_table


def test_labels_use_future_windows_and_trade_outcomes():
    dates = pd.bdate_range("2024-01-02", periods=6)
    trades = pd.DataFrame(
        [
            {
                "signal_date": dates[0],
                "holding_days": 1,
                "return_on_premium": 0.10,
                "net_pnl": 100,
                "spot_at_signal": 100,
            },
            {
                "signal_date": dates[0],
                "holding_days": 3,
                "return_on_premium": 0.30,
                "net_pnl": 300,
                "spot_at_signal": 100,
            },
            {
                "signal_date": dates[1],
                "holding_days": 1,
                "return_on_premium": -0.10,
                "net_pnl": -100,
                "spot_at_signal": 110,
            },
            {
                "signal_date": dates[1],
                "holding_days": 3,
                "return_on_premium": 0.05,
                "net_pnl": 50,
                "spot_at_signal": 110,
            },
        ]
    )
    underlying = pd.DataFrame({"date": dates, "close": [100, 110, 121, 110, 100, 105]})

    labels = build_label_table(trades, underlying, holding_days=[1, 3])
    first = labels.iloc[0]

    assert math.isclose(first["forward_straddle_return_1d"], 0.10)
    assert math.isclose(first["forward_straddle_net_pnl_3d"], 300)
    assert math.isclose(first["future_abs_return_1d"], 0.10)
    assert math.isclose(first["future_abs_return_3d"], 0.10)

