import pandas as pd

from src.option_selector import select_atm_straddle


def _chain():
    return pd.DataFrame(
        [
            {
                "date": "2024-01-02",
                "option_code": "MO_240131_05000_C",
                "call_put": "C",
                "strike": 5000,
                "expire_date": "2024-01-31",
                "close": 80,
                "volume": 100,
                "open_interest": 1000,
            },
            {
                "date": "2024-01-02",
                "option_code": "MO_240131_05000_P",
                "call_put": "P",
                "strike": 5000,
                "expire_date": "2024-01-31",
                "close": 75,
                "volume": 100,
                "open_interest": 1000,
            },
            {
                "date": "2024-01-02",
                "option_code": "MO_240131_05200_C",
                "call_put": "C",
                "strike": 5200,
                "expire_date": "2024-01-31",
                "close": 20,
                "volume": 100,
                "open_interest": 1000,
            },
            {
                "date": "2024-01-02",
                "option_code": "MO_240131_05200_P",
                "call_put": "P",
                "strike": 5200,
                "expire_date": "2024-01-31",
                "close": 190,
                "volume": 100,
                "open_interest": 1000,
            },
        ]
    )


def test_selects_nearest_atm_pair():
    result = select_atm_straddle(_chain(), 5010, "2024-01-02", {"min_dte": 10, "max_dte": 35})
    assert result is not None
    assert result["strike"] == 5000
    assert result["call_code"].endswith("_C")
    assert result["put_code"].endswith("_P")


def test_returns_none_when_no_liquid_contracts():
    chain = _chain()
    chain["volume"] = 0
    chain["open_interest"] = 0
    result = select_atm_straddle(chain, 5010, "2024-01-02", {"min_dte": 10, "max_dte": 35})
    assert result is None
    assert "valid liquid" in select_atm_straddle.last_reason

