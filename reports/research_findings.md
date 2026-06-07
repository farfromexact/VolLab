# VolLab v0.2 Research Findings

## 结论先行

1. 过去所有 top 10% straddle return 事件没有稳定、单调、可直接交易的共同前置信号。较短 DTE 和中等偏高的 Compression Score 有一点倾向，但不足以单独构成入场条件。
2. `IV - RV20` 在事件前并不通常偏低。全样本 top10 中位数为 -3.1%，非 top10 为 -5.4%；剔除 warmup 后 top10 为 -3.2%，全体为 -3.6%。这不支持“IV 相对 RV 越便宜越好”的单调结论。
3. `range_percentile_252` 不通常偏低。该字段主要在 post-warmup 后可用，top10 中位数为 48.0%，全体中位数为 39.7%，反而略高。
4. `RV20_change_5d` 在事件前没有普遍抬升。post-warmup top10 中位数为 -0.2%，全体中位数为 0.1%。
5. 正式的 `straddle_premium_to_spot` 目前无法判断，因为旧版回测没有保存 signal date 的 call/put close。用 `entry_premium / spot_at_signal` 作代理时，top10 和全样本中位数几乎一样，不能证明“便宜”有效。
6. DTE 是当前最值得继续研究的变量之一。post-warmup top10 的 DTE 中位数为 17.5，低于全体 23.0；10-16 天 bucket 的 top10 占比最高。但它仍不是严格单调。
7. 2024-09/10 和 2025-04 的 spike 属于不同类型。2024-09/10 是高波动冲击阶段，2025-04 更像低胜率、少数大胜拉动的事件性 spike。
8. daily_rolling、non_overlapping、one_position_at_a_time 三种模式下，当前默认规则的方向一致：没有一组规则稳健。减少重叠会减少交易数和风险暴露，但不会把弱信号变成强信号。
9. 剔除 warmup 后，score 和 feature 分桶结论更保守。高 Vol Long Score、高 Valuation Score、高 IV Percentile 都没有稳定优势。
10. 严格单调的核心 feature 暂时没有。DTE 有弱倾向，其余核心变量大多是非单调或样本不足。

## 样本定义

- feature rows: 470，signal_date 从 2024-01-02 到 2026-05-29。
- trades: 1,880，holding_days = 1 / 2 / 3 / 5，每个 signal date 生成 4 个研究样本。
- top 10% straddle return 事件定义：`is_top_10pct_straddle_return_1d / 3d / 5d` 任一为 True。
- top10 union signals: 99 / 470。
- warmup: `iv_lookback=252`，前 251 个 signal 视为 warmup。

## Top10 事件前置信号

| feature | top10 median | all median | non-top median | usable top n |
|---|---:|---:|---:|---:|
| IV - RV20 | -3.1% | -5.0% | -5.4% | 84 |
| range_percentile_252 | 48.0% | 39.7% | 38.1% | 32 |
| RV20_change_5d | -1.2% | 0.0% | 0.1% | 84 |
| entry premium / spot proxy | 4.9% | 4.9% | 4.9% | 99 |
| DTE | 21.0 | 23.0 | 23.0 | 99 |
| IV Percentile | 45.8% | 34.9% | 32.1% | 32 |
| IV Rank | 12.7% | 8.9% | 7.7% | 32 |
| Valuation Score | 62.0 | 74.0 | 76.7 | 84 |
| Compression Score | 65.3 | 62.6 | 61.5 | 85 |
| Trigger Score | 32.0 | 38.1 | 39.3 | 98 |
| Legacy Vol Score | 55.4 | 65.9 | 68.7 | 99 |

解读：

- top10 前并没有出现“IV 明显便宜、range 明显压缩、RV20 已经抬升”的组合。
- Compression Score 略高，但幅度不大。
- Valuation Score 和 Legacy Vol Score 在 top10 前反而低于非 top10，说明旧的 cheap-vol 打分不稳定。

## Top10 signal trades 与非 Top10 signal trades

这张表不是用来证明规则可交易，因为 top10 是事后标签；它用于衡量 spike 对收益的贡献强度。

| sample | trades | win rate | avg return | median return | avg net pnl | total net pnl | max loss | max win | top 5 wins / total pnl |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| top10 signal trades, all sample | 396 | 74.0% | 33.8% | 13.0% | 9,042.8 | 3,580,961.8 | -10,875.3 | 139,300.7 | 0.15 |
| non-top signal trades, all sample | 1,484 | 20.5% | -8.5% | -7.7% | -2,955.6 | -4,386,091.6 | -97,513.5 | 15,671.9 | -0.02 |
| top10 signal trades, post-warmup | 128 | 68.0% | 18.2% | 10.7% | 5,696.0 | 729,083.9 | -10,875.3 | 43,996.2 | 0.24 |
| non-top signal trades, post-warmup | 748 | 17.9% | -8.9% | -8.5% | -3,164.4 | -2,366,954.1 | -90,149.7 | 15,671.9 | -0.03 |

解读：

- top10 signal trades 赚钱是标签定义带来的结果，不等于可以提前识别。
- post-warmup 后，top 5 wins / total pnl 为 0.24，说明 top10 子样本仍依赖少数大胜。
- 非 top signal trades 的 max loss 明显更大，说明“每天都买”的尾部亏损仍然严重。

## DTE 分布

全样本：

| DTE bucket | top10 events | all signals | top10 share in bucket |
|---|---:|---:|---:|
| 10-14 | 15 | 71 | 21.1% |
| 15-20 | 29 | 102 | 28.4% |
| 21-25 | 22 | 138 | 15.9% |
| 26-30 | 21 | 82 | 25.6% |
| 31-35 | 12 | 77 | 15.6% |

剔除 warmup 后：

| DTE bucket | top10 events | all signals | top10 share in bucket |
|---|---:|---:|---:|
| 10-16 | 8 | 29 | 27.6% |
| 17-21 | 10 | 48 | 20.8% |
| 22-24 | 4 | 68 | 5.9% |
| 25-30 | 5 | 37 | 13.5% |
| 31-35 | 5 | 37 | 13.5% |

解读：

- DTE 确实有信号：较短 DTE 的 top10 占比更高。
- 但 25-30 天在全样本中也有较高占比，因此不能简单写成 DTE 越短越好。

## 2024-09/10 vs 2025-04

| period | signals | top10 signals | IV-RV20 median | RV20 change 5d median | range pct median | DTE median | legacy score median | 5d return median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-09/10 spike | 33 | 12 | -8.6% | 0.1% | NA | 22.0 | 70.0 | 2.2% |
| 2025-04 spike | 30 | 5 | -3.6% | -0.1% | 5.0% | 23.5 | 61.4 | -10.9% |

| sample | trades | win rate | avg return | median return | avg net pnl | total net pnl | max loss | max win | top 5 wins / total pnl |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-09/10 spike | 132 | 47.0% | 28.9% | -2.0% | 4,667.9 | 616,160.1 | -97,513.5 | 139,300.7 | 0.86 |
| 2025-04 spike | 120 | 20.8% | 6.4% | -6.6% | 1,271.6 | 152,594.0 | -22,092.6 | 58,378.8 | 1.79 |

判断：

- 2024-09/10 是高波动冲击。`RV20` 和 `ATM IV` 同时快速抬升，收益来自大幅波动兑现。该阶段 top 5 wins / total pnl = 0.86，已经高度依赖少数交易。
- 2025-04 胜率更低，median return 为 -6.6%，但 total pnl 为正，top 5 wins / total pnl = 1.79。这说明除了前 5 笔最大盈利外，其余交易合计为负，更依赖少数 spike。
- 因此两者不是同一类稳定信号。2024-09/10 更像 volatility shock，2025-04 更像 event-driven payoff。

## 执行模式对比

以下为当前默认规则集合的结果，不是优化后的策略。

| rule | mode | trades | win rate | avg return | median return | total net pnl | max loss | max win | top 5 wins / total pnl | top10 capture | flat ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cheap_iv_vs_rv | daily_rolling | 356 | 22.8% | -5.9% | -7.2% | -601,267.0 | -18,783.4 | 35,875.5 | -0.20 | 9.2% | 81.1% |
| cheap_iv_vs_rv | non_overlapping | 199 | 23.6% | -4.8% | -5.6% | -280,003.5 | -14,512.7 | 35,875.5 | -0.31 | 2.8% | 81.1% |
| cheap_iv_vs_rv | one_position_at_a_time | 89 | 22.5% | -4.0% | -4.6% | -105,969.6 | -6,586.1 | 13,659.1 | -0.21 | 2.1% | 81.1% |
| compressed_range | daily_rolling | 92 | 19.6% | -6.9% | -8.3% | -170,907.3 | -10,233.8 | 37,202.7 | -0.36 | 1.4% | 95.1% |
| compressed_range | non_overlapping | 74 | 17.6% | -6.9% | -8.2% | -138,352.0 | -10,233.8 | 37,202.7 | -0.36 | 0.7% | 95.1% |
| compressed_range | one_position_at_a_time | 23 | 17.4% | -6.2% | -5.8% | -37,856.3 | -5,493.6 | 1,661.1 | -0.08 | 0.0% | 95.1% |
| iv_discount_and_trigger | daily_rolling | 648 | 27.3% | -1.4% | -6.6% | -806,955.5 | -90,149.7 | 139,300.7 | -0.61 | 17.7% | 65.5% |
| iv_discount_and_trigger | non_overlapping | 379 | 26.6% | -2.2% | -6.0% | -642,718.8 | -90,149.7 | 139,300.7 | -0.51 | 12.8% | 65.5% |
| iv_discount_and_trigger | one_position_at_a_time | 162 | 27.8% | -2.4% | -4.3% | -201,017.5 | -87,463.2 | 20,944.5 | -0.35 | 25.5% | 65.5% |

解读：

- 三种模式下方向一致：默认规则均不稳健。
- `one_position_at_a_time` 降低重叠和 max loss，但也显著降低交易数和捕捉机会。
- `iv_discount_and_trigger` 捕捉 top10 事件最多，但 total pnl 仍为负，且 max loss 很大。
- 不能只看 total pnl。这里 win rate、median return、max loss 和 top 5 wins contribution 都显示规则质量不足。

## Warmup 影响

- warmup signals: 251。
- post-warmup signals: 219。
- post-warmup top10 signals: 32。
- post-warmup 后，`IV Rank / IV Percentile / range_percentile_252` 才更可信。
- 剔除 warmup 后，`IV - RV20`、`range_percentile_252`、`RV20_change_5d` 都没有显示稳定优势。
- 早期 2024 spike 不能直接拿来训练 IV Rank / Percentile 规则，否则会混入不可比的 warmup 样本。

## 单调性审查

Post-warmup 按五分位分桶，表中数字是每个桶内 top10 signal 占比。

| feature | post-warmup quintile top10 shares | monotonic read |
|---|---|---|
| IV - RV20 | 9.1% / 20.5% / 9.3% / 13.6% / 20.5% | not monotonic |
| range_percentile_252 | 9.3% / 9.1% / 21.4% / 18.6% / 16.3% | not monotonic |
| RV20_change_5d | 15.9% / 18.2% / 11.6% / 18.2% / 9.1% | not monotonic |
| entry premium / spot proxy | 20.5% / 11.4% / 11.6% / 15.9% / 13.6% | not monotonic |
| DTE | 27.5% / 12.5% / 7.1% / 10.2% / 13.5% | not monotonic; short DTE first bucket strongest |
| Valuation Score | 15.9% / 27.3% / 16.3% / 4.5% / 9.1% | not monotonic |
| Compression Score | 4.5% / 13.6% / 23.3% / 18.2% / 13.6% | not monotonic |
| Trigger Score | 13.6% / 22.7% / 11.6% / 13.6% / 11.4% | not monotonic |
| Legacy Vol Score | 18.2% / 34.1% / 9.3% / 6.8% / 4.5% | not monotonic; middle bucket best, high score weak |
| IV Percentile | 2.3% / 9.1% / 21.7% / 19.5% / 20.5% | weakly higher after low buckets, but not strictly monotonic |
| IV Rank | 4.5% / 9.1% / 18.6% / 20.5% / 20.5% | weak upward tendency, not sufficient alone |
| RV20 Percentile | 7.1% / 15.8% / 20.5% / 17.1% / 20.5% | not monotonic |

结论：

- 严格单调 feature：没有。
- 弱倾向：短 DTE；IV Rank / IV Percentile 有弱上升倾向，但与“便宜 IV”逻辑方向相反，并且不能单独交易。
- 非单调：`IV - RV20`、`range_percentile_252`、`RV20_change_5d`、`Valuation Score`、`Trigger Score`、`Legacy Vol Score`。
- 明确反证：Legacy Vol Score 的最高分桶 top10 占比只有 4.5%，说明不能把单一 score 当作买入信号。

## 对 10 个问题的直接回答

1. 共同前置信号：没有稳定共同信号。较短 DTE 和中等 Compression Score 有弱倾向，但不足以交易。
2. IV - RV20 是否通常偏低：否。top10 并不比非 top10 更低。
3. range_percentile_252 是否通常偏低：否。post-warmup top10 中位数反而略高。
4. RV20_change_5d 是否已经抬升：否。中位数不支持。
5. straddle_premium_to_spot 是否便宜：正式 feature 缺失；代理指标看不出便宜优势。
6. DTE 集中在哪些区间：全样本 15-20 天较多；post-warmup 10-16 天最强。
7. 2024-09/10 和 2025-04 是否不同类型：是。前者是大波动冲击，后者是低胜率但少数大胜拉动。
8. 三种执行模式结论是否一致：方向一致，默认规则都不稳健；交易数和风险暴露不同。
9. 剔除 warmup 后结论是否变化：变得更弱、更保守；很多早期关系消失。
10. 哪些 feature 单调：没有严格单调；DTE 有弱倾向，其余核心 feature 均非单调。

## 下一步研究建议

不要先优化收益。建议先补数据质量和事件分类：

1. 在回测时保存 signal date 的 call/put close、volume、open_interest，补齐 `straddle_premium_to_spot` 和 liquidity features。
2. 把 spike 按事件类型分层：大跌波动、上涨波动、节后跳空、政策冲击、流动性冲击。
3. 分别研究 1d / 3d / 5d 标签，不要只看 union top10。
4. 所有规则必须同时报告 trade count、win rate、avg return、median return、max loss、top 5 wins contribution。
5. warmup 样本必须单独列示，不能和 post-warmup 混合下结论。
