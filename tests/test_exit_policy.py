import math

import pandas as pd

from src.exit_policy import evaluate_exit_policy, run_exit_policy_experiments


def test_exit_policy_stop_loss_wins_when_take_profit_same_day():
    path = pd.DataFrame(
        [
            {
                "signal_date": pd.Timestamp("2024-01-02"),
                "date": pd.Timestamp("2024-01-03"),
                "day": 1,
                "straddle_return": 0.1,
                "high_return": 0.6,
                "low_return": -0.4,
                "entry_notional": 1000.0,
                "dte": 12,
                "event_type": "gap_event",
            }
        ]
    )

    result = evaluate_exit_policy(path, "take_profit_50pct_or_stop_loss_30pct", {})

    assert result["exit_reason"] == "stop_loss_30pct"
    assert math.isclose(result["return_on_premium"], -0.3)


def test_exit_policy_missing_event_fields_do_not_crash():
    trades = pd.DataFrame(
        [
            {
                "signal_date": "2024-01-02",
                "exit_date": "2024-01-03",
                "holding_days": 1,
                "dte": 12,
                "entry_premium": 20.0,
                "return_on_premium": 0.1,
                "net_pnl": 200.0,
            }
        ]
    )

    results, summary, by_event, by_dte = run_exit_policy_experiments(trades, pd.DataFrame(), {"contract_multiplier": 100}, ["fixed_hold_1d"])

    assert len(results) == 1
    assert summary.loc[0, "trade_count"] == 1
    assert not by_event.empty
    assert not by_dte.empty

