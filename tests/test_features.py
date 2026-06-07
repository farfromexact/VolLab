import numpy as np
import pandas as pd

from src.features import build_feature_table


def _trade_details(n=12):
    dates = pd.bdate_range("2024-01-02", periods=n)
    rows = []
    for i, date in enumerate(dates):
        for holding in [1, 2]:
            rows.append(
                {
                    "signal_date": date,
                    "entry_date": dates[min(i + 1, n - 1)],
                    "exit_date": dates[min(i + holding, n - 1)],
                    "holding_days": holding,
                    "spot_at_signal": 100 + i,
                    "atm_iv": 0.15 + i * 0.005,
                    "rv20": np.nan,
                    "iv_rank": np.nan,
                    "iv_percentile": np.nan,
                    "iv_minus_rv20": np.nan,
                    "dte": 20,
                    "strike": 100 + i,
                    "net_pnl": i,
                    "return_on_premium": i / 100,
                }
            )
    return pd.DataFrame(rows)


def _underlying(n=12):
    dates = pd.bdate_range("2024-01-02", periods=n)
    close = pd.Series(100 + np.arange(n), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000 + np.arange(n),
        }
    )


def test_features_do_not_use_future_data():
    trades = _trade_details()
    underlying = _underlying()
    base = build_feature_table(trades, underlying, iv_lookback=5)

    changed = underlying.copy()
    changed.loc[changed.index >= 8, "close"] *= 10
    changed.loc[changed.index >= 8, "high"] *= 10
    changed.loc[changed.index >= 8, "low"] *= 10
    rebuilt = build_feature_table(trades, changed, iv_lookback=5)

    cols = ["ret_1d", "ret_3d", "rv5", "iv_rank", "winsorized_iv_rank_252"]
    pd.testing.assert_frame_equal(base.loc[:6, cols], rebuilt.loc[:6, cols])


def test_winsorized_iv_rank_and_warmup_flags():
    trades = _trade_details(8)
    trades.loc[trades["signal_date"] == pd.bdate_range("2024-01-02", periods=8)[5], "atm_iv"] = 2.0
    features = build_feature_table(trades, _underlying(8), iv_lookback=5)

    assert features["is_iv_warmup"].iloc[:4].all()
    assert not features["is_iv_warmup"].iloc[4]
    valid = features["winsorized_iv_rank_252"].dropna()
    assert valid.between(0, 1).all()

