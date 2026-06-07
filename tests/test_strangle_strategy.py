import pandas as pd

from src.strategy_strangle import select_otm_strangle


def _chain():
    date = pd.Timestamp("2024-01-02")
    expiry = pd.Timestamp("2024-01-24")
    rows = []
    for strike in [90, 95, 97, 100, 103, 105, 110]:
        rows.append(
            {
                "date": date,
                "option_code": f"C{strike}",
                "call_put": "C",
                "strike": strike,
                "expire_date": expiry,
                "close": 1.0,
                "volume": 10,
                "open_interest": 100,
            }
        )
        rows.append(
            {
                "date": date,
                "option_code": f"P{strike}",
                "call_put": "P",
                "strike": strike,
                "expire_date": expiry,
                "close": 1.0,
                "volume": 10,
                "open_interest": 100,
            }
        )
    return pd.DataFrame(rows)


def test_select_otm_strangle_uses_existing_positive_priced_contracts():
    selected = select_otm_strangle(_chain(), 100.0, "2024-01-02", {"min_dte": 7, "max_dte": 45}, 0.03)

    assert selected is not None
    assert selected["put_strike"] <= 97
    assert selected["call_strike"] >= 103
    assert selected["put_code"].startswith("P")
    assert selected["call_code"].startswith("C")


def test_select_otm_strangle_rejects_missing_or_zero_price_pair():
    chain = _chain()
    chain.loc[chain["call_put"].eq("C") & chain["strike"].ge(103), "close"] = 0.0

    selected = select_otm_strangle(chain, 100.0, "2024-01-02", {"min_dte": 7, "max_dte": 45}, 0.03)

    assert selected is None

