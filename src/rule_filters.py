from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def condition_mask(frame: pd.DataFrame, condition: dict) -> pd.Series:
    field = condition.get("field")
    if field not in frame.columns:
        return pd.Series(False, index=frame.index)

    op = str(condition.get("op", condition.get("operator", ""))).lower()
    values = frame[field]

    if op in {"<", "lt", "less_than"}:
        return values < condition["value"]
    if op in {">", "gt", "greater_than"}:
        return values > condition["value"]
    if op in {"<=", "le"}:
        return values <= condition["value"]
    if op in {">=", "ge"}:
        return values >= condition["value"]
    if op == "between":
        low, high = condition.get("value", [condition.get("low"), condition.get("high")])
        return values.between(low, high, inclusive="both")
    if op in {"not_null", "is_not_null", "notnull"}:
        return values.notna()

    raise ValueError(f"Unsupported rule operator: {op!r}")


def apply_rule(frame: pd.DataFrame, rule: dict) -> pd.Series:
    conditions = rule.get("conditions", [])
    if not conditions:
        return pd.Series(True, index=frame.index)
    mask = pd.Series(True, index=frame.index)
    for condition in conditions:
        mask &= condition_mask(frame, condition)
    return mask.fillna(False)


def filter_by_rule(frame: pd.DataFrame, rule: dict) -> pd.DataFrame:
    return frame.loc[apply_rule(frame, rule)].copy()


def apply_rules(frame: pd.DataFrame, rules: Iterable[dict]) -> dict[str, pd.DataFrame]:
    output = {}
    for idx, rule in enumerate(rules):
        name = str(rule.get("name", f"rule_{idx + 1}"))
        output[name] = filter_by_rule(frame, rule)
    return output


DEFAULT_RULES = [
    {
        "name": "cheap_iv_vs_rv",
        "conditions": [
            {"field": "iv_minus_rv20", "op": "<", "value": -0.02},
            {"field": "iv_percentile", "op": "<", "value": 0.60},
        ],
    },
    {
        "name": "compressed_range",
        "conditions": [
            {"field": "range_percentile_252", "op": "<", "value": 0.30},
            {"field": "rv20_change_5d", "op": ">", "value": 0.0},
        ],
    },
    {
        "name": "mid_dte_reasonable_premium",
        "conditions": [
            {"field": "dte", "op": "between", "value": [15, 30]},
            {"field": "straddle_premium_to_spot", "op": "<", "value": 0.06},
        ],
    },
    {
        "name": "iv_discount_and_trigger",
        "conditions": [
            {"field": "iv_minus_rv20", "op": "<", "value": -0.02},
            {"field": "rv20_change_5d", "op": ">", "value": 0.0},
            {"field": "dte", "op": "between", "value": [10, 35]},
        ],
    },
]

