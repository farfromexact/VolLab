import pandas as pd

from src.event_classifier import classify_events
from src.features import build_feature_table


def test_event_classification_uses_research_labels_not_signal_features():
    dates = pd.bdate_range("2024-01-02", periods=6)
    trades = pd.DataFrame(
        [
            {
                "signal_date": dates[0],
                "entry_date": dates[1],
                "exit_date": dates[1],
                "holding_days": 1,
                "spot_at_signal": 100.0,
                "atm_iv": 0.2,
                "rv20": 0.1,
                "iv_rank": 0.5,
                "iv_percentile": 0.5,
                "iv_minus_rv20": 0.1,
                "dte": 12,
                "strike": 100,
                "entry_call_price": 10,
                "entry_put_price": 10,
                "exit_call_price": 1,
                "exit_put_price": 25,
                "return_on_premium": 0.4,
                "net_pnl": 1400,
            }
        ]
    )
    labels = pd.DataFrame(
        {
            "signal_date": [dates[0]],
            "future_abs_return_1d": [0.04],
            "future_direction_1d": [-1],
            "future_gap_return_next_open": [0.0],
            "future_rv_5d": [0.12],
        }
    )
    features = build_feature_table(trades, pd.DataFrame({"date": dates, "close": range(100, 106)}), iv_lookback=2)
    events = classify_events(trades, labels, features, {"event_thresholds": {"shock_return_threshold": 0.025}})

    assert events.loc[0, "event_type"] == "down_shock"
    assert "event_type" not in features.columns


def test_gap_event_has_priority_over_shock_direction():
    date = pd.Timestamp("2024-01-02")
    trades = pd.DataFrame(
        [
            {
                "signal_date": date,
                "holding_days": 1,
                "entry_call_price": 10,
                "entry_put_price": 10,
                "exit_call_price": 30,
                "exit_put_price": 1,
                "return_on_premium": 0.5,
                "net_pnl": 1000,
                "rv20": 0.1,
            }
        ]
    )
    labels = pd.DataFrame(
        {
            "signal_date": [date],
            "future_abs_return_1d": [0.04],
            "future_direction_1d": [1],
            "future_gap_return_next_open": [0.02],
            "future_rv_5d": [0.12],
        }
    )

    events = classify_events(trades, labels, pd.DataFrame(), {"event_thresholds": {"gap_threshold": 0.012}})

    assert events.loc[0, "event_type"] == "gap_event"
