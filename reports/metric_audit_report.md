# VolLab Metric Audit

- rows: 1,880
- signal range: 2024-01-02 to 2026-05-29
- exit range: 2024-01-03 to 2026-06-05

## 1. avg_return vs avg_net_pnl sign
- CHECK: 2 holding bucket(s) have different signs.
- Explanation: signs can differ only if return weighting by premium diverges from raw PnL weighting; this deserves review when present.

## 2. return_on_premium formula
- PASS: max abs diff = 0.000000000000
- Formula used: net_pnl / (entry_premium_points * contract_multiplier).

## 3. contract_multiplier application
- PASS: max gross pnl diff = 0.00000000

## 4. cost model
- PASS: max cost diff = 0.00000000
- Cost includes entry slippage and exit slippage; fee_per_contract is applied to four legs/transactions in the simplified model.

## 5. equity curve holding-day merge
- CHECK: current dashboard equity curve merges holding_days=[1, 2, 3, 5] into one daily realized PnL curve.

## 6. daily rolling overlap
- CHECK: max simultaneous research trades = 11. Daily rolling mode intentionally contains overlapping positions.

## 7. signal/entry/exit date ordering
- PASS: requires signal_date < entry_date <= exit_date.

## 8. IV Rank / Percentile lookahead
- PASS: strategy computes IV history incrementally in signal-date order, so current implementation is point-in-time.

## 9. IV warmup
- CHECK: first 251 signal samples are warmup for lookback=252.
- Warmup non-null IV rank/percentile cells: 0.

## 10. warmup-separated stats
- warmup signals: 251
- post-warmup signals: 219
- post-warmup trades: 876
- post-warmup total net pnl: -1637870.20
