from src.mock_data_provider import MockDataProvider
from src.strategy_straddle import TRADE_COLUMNS, run_straddle_strategy


def test_mock_straddle_backtest_generates_trade_details():
    config = {
        "underlying_code": "000852.SH",
        "option_prefix": "MO",
        "contract_multiplier": 100,
        "risk_free_rate": 0.02,
        "min_dte": 10,
        "max_dte": 35,
        "roll_dte_threshold": 7,
        "holding_days": [1, 2],
        "entry_mode": "next_open",
        "fallback_entry_mode": "next_close",
        "slippage_rate": 0.005,
        "fee_per_contract": 0,
        "iv_lookback": 20,
        "mock_start_date": "2023-01-03",
        "mock_end_date": "2023-06-30",
        "mock_seed": 7,
        "mock_start_price": 5000,
    }
    provider = MockDataProvider(config)
    trades = run_straddle_strategy(provider, config)
    assert not trades.empty
    assert set(TRADE_COLUMNS).issubset(trades.columns)
    assert set(trades["holding_days"]) == {1, 2}
    assert trades["entry_premium"].gt(0).all()

