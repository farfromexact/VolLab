import pandas as pd

from src.dte_research import bucket_dte, run_dte_research


def test_dte_bucket_boundaries_are_non_overlapping():
    assert bucket_dte(7) == "7-10"
    assert bucket_dte(10) == "7-10"
    assert bucket_dte(11) == "10-14"
    assert bucket_dte(14) == "10-14"
    assert bucket_dte(15) == "15-21"
    assert bucket_dte(22) == "22-30"
    assert bucket_dte(31) == "31-45"


def test_dte_research_splits_warmup_and_post_warmup():
    trades = pd.DataFrame(
        [
            {"signal_date": "2024-01-02", "holding_days": 1, "dte": 10, "return_on_premium": 0.1, "net_pnl": 100},
            {"signal_date": "2024-01-03", "holding_days": 1, "dte": 12, "return_on_premium": -0.1, "net_pnl": -100},
        ]
    )
    features = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "is_iv_warmup": [True, False],
        }
    )
    labels = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "is_top_10pct_straddle_return_1d": [True, False],
        }
    )
    events = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "holding_days": [1, 1],
            "event_type": ["up_shock", "noise_theta_decay"],
        }
    )

    summary = run_dte_research(trades, labels, events, features, horizons=(1,))
    all_rows = summary.loc[summary["post_warmup_only"].eq(False) & summary["event_type"].eq("all")]
    post_rows = summary.loc[summary["post_warmup_only"].eq(True) & summary["event_type"].eq("all")]

    assert all_rows["trade_count"].sum() == 2
    assert post_rows["trade_count"].sum() == 1

