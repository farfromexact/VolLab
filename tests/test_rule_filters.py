import pandas as pd

from src.rule_filters import apply_rule, filter_by_rule


def test_rule_filter_supports_and_conditions():
    frame = pd.DataFrame(
        {
            "iv_minus_rv20": [-0.03, -0.01, -0.04],
            "iv_percentile": [0.5, 0.4, 0.8],
            "dte": [20, 40, 25],
            "x": [1, None, 3],
        }
    )
    rule = {
        "name": "test",
        "conditions": [
            {"field": "iv_minus_rv20", "op": "<", "value": -0.02},
            {"field": "iv_percentile", "op": "<", "value": 0.6},
            {"field": "dte", "op": "between", "value": [15, 30]},
            {"field": "x", "op": "not_null"},
        ],
    }

    mask = apply_rule(frame, rule)
    assert mask.tolist() == [True, False, False]
    assert len(filter_by_rule(frame, rule)) == 1

