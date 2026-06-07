import pandas as pd

from src.experiment_runner import apply_execution_mode, run_timing_experiments


def _trades():
    return pd.DataFrame(
        [
            {
                "signal_date": "2024-01-01",
                "entry_date": "2024-01-02",
                "exit_date": "2024-01-05",
                "holding_days": 3,
                "net_pnl": 10,
                "return_on_premium": 0.1,
            },
            {
                "signal_date": "2024-01-02",
                "entry_date": "2024-01-03",
                "exit_date": "2024-01-06",
                "holding_days": 3,
                "net_pnl": -5,
                "return_on_premium": -0.05,
            },
            {
                "signal_date": "2024-01-08",
                "entry_date": "2024-01-09",
                "exit_date": "2024-01-12",
                "holding_days": 3,
                "net_pnl": 20,
                "return_on_premium": 0.2,
            },
            {
                "signal_date": "2024-01-03",
                "entry_date": "2024-01-04",
                "exit_date": "2024-01-05",
                "holding_days": 1,
                "net_pnl": 1,
                "return_on_premium": 0.01,
            },
        ]
    )


def test_non_overlapping_mode_skips_same_holding_overlap():
    selected = apply_execution_mode(_trades(), "non_overlapping")
    holding3 = selected[selected["holding_days"] == 3]
    assert holding3["signal_date"].tolist() == ["2024-01-01", "2024-01-08"]


def test_one_position_at_a_time_has_no_overlap():
    selected = apply_execution_mode(_trades(), "one_position_at_a_time")
    selected = selected.sort_values("entry_date").reset_index(drop=True)
    exits = pd.to_datetime(selected["exit_date"])
    entries = pd.to_datetime(selected["entry_date"])
    assert all(entries.iloc[i] > exits.iloc[i - 1] for i in range(1, len(selected)))


def test_timing_experiment_outputs_summary():
    features = pd.DataFrame({"signal_date": ["2024-01-01", "2024-01-02", "2024-01-03"], "x": [1, 0, 1]})
    labels = pd.DataFrame(
        {
            "signal_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "is_top_10pct_straddle_return_1d": [True, False, False],
            "is_top_10pct_straddle_return_3d": [True, False, False],
        }
    )
    rule = {"name": "x_positive", "conditions": [{"field": "x", "op": ">", "value": 0}]}
    summary = run_timing_experiments(features, labels, _trades(), [rule], modes=["daily_rolling"])
    assert not summary.empty
    assert set(summary["rule_name"]) == {"x_positive"}

