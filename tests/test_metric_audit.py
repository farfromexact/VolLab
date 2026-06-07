import pandas as pd

from src.metric_audit import audit_trade_metrics


def test_metric_audit_report_contains_core_checks():
    trades = pd.DataFrame(
        [
            {
                "signal_date": "2024-01-01",
                "entry_date": "2024-01-02",
                "exit_date": "2024-01-03",
                "holding_days": 1,
                "entry_premium": 10.05,
                "exit_premium": 11.94,
                "gross_pnl": 200,
                "cost": 11,
                "net_pnl": 189,
                "return_on_premium": 189 / (10.05 * 100),
                "iv_rank": None,
                "iv_percentile": None,
            }
        ]
    )
    report = audit_trade_metrics(trades, {"contract_multiplier": 100, "slippage_rate": 0.005, "fee_per_contract": 0})
    assert "return_on_premium formula" in report
    assert "PASS" in report
    assert "warmup" in report

