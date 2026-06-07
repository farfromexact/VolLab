# VolLab v0.3 Research Findings

## 结论先行

本次已用 Wind API 重新跑完 v0.3 全流程。Wind provider 可以读取 `000852.SH` 日线、MO option chain、期权日线和 signal-date quote snapshot；旧报告中“Wind 登录失败、OTM strangle unavailable”的限制已经解除。

1. v0.3 的 signal-date option quality 已落地：`signal_call_close / signal_put_close / volume / open_interest` 完整率从旧数据的 0% 变成 100%。
2. ATM straddle 回测仍不支持直接交易结论：1,880 笔 horizon trades，总净 PnL `-805,129.8`，胜率 `31.8%`，平均收益 `0.4%`，中位收益 `-5.6%`。
3. 收益仍主要来自 ex-post shock：`up_shock` 和 `down_shock` 在 1d/3d/5d 都是 100% 胜率，但它们是事后标签，不能直接当作入场信号。
4. DTE 只有局部现象：post-warmup 的 `7-10` DTE、5d horizon 为正，11 笔、胜率 `54.5%`、平均收益 `5.9%`、中位收益 `8.0%`，样本太小。
5. `stop_loss_30pct` 表面最好：470 笔、胜率 `33.6%`、平均收益 `3.4%`、中位收益 `-10.7%`、总净 PnL `95,250.6`，但 top 5 wins 是总 PnL 的 `4.81x`，仍高度依赖少数 spike。
6. 3%/5% OTM strangle 已有真实 provider-chain 结果：低 premium 带来更高平均收益弹性，但 1d/3d/5d 中位收益全部为负，尾部依赖比 ATM 更明显。

## 数据质量

审计行数：1,880 trade rows。

| field group | completeness | interpretation |
| --- | ---: | --- |
| signal call/put close | 100.0% | true Wind/provider quote |
| signal call/put volume | 100.0% | true Wind/provider quote |
| signal call/put open interest | 100.0% | true Wind/provider quote |
| signal straddle premium to spot | 100.0% | derived from true signal quote and spot |
| entry call/put open | 100.0% | v0.3 provider quote |
| exit call/put close | 100.0% | v0.3 provider quote |
| signal bid/ask fields | 0.0% | reserved; current provider config does not supply bid/ask |

结论：v0.3 现在可以研究真实 `signal_straddle_premium_to_spot`，不再依赖旧 v0.2 的 `entry_premium / spot_at_signal` proxy。但 bid/ask spread 仍不可研究，需要 Wind 字段确认后再接入。

## ATM Straddle Baseline

| metric | value |
| --- | ---: |
| total trades | 1,880 |
| win rate | 31.8% |
| avg return | 0.4% |
| median return | -5.6% |
| max trade profit | 139,300.7 |
| max trade loss | -97,513.5 |
| total net PnL | -805,129.8 |

按持有期看：

| holding | trades | win rate | avg return | median return | max loss | max win |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1d | 470 | 30.6% | -1.3% | -3.6% | -87,463.2 | 41,141.3 |
| 2d | 470 | 29.6% | -0.2% | -5.9% | -84,040.4 | 70,853.7 |
| 3d | 470 | 33.0% | 0.9% | -7.4% | -90,149.7 | 102,295.7 |
| 5d | 470 | 33.8% | 2.2% | -10.6% | -97,513.5 | 139,300.7 |

平均收益随持有期拉长变好，但中位数更差，说明正收益主要来自少数大波动。

## Event Type

| event_type | 1d trades / win / avg / median | 3d trades / win / avg / median | 5d trades / win / avg / median |
| --- | ---: | ---: | ---: |
| down_shock | 21 / 100.0% / 25.5% / 19.9% | 57 / 100.0% / 41.3% / 27.1% | 69 / 100.0% / 47.5% / 20.9% |
| up_shock | 7 / 100.0% / 23.2% / 18.5% | 27 / 100.0% / 54.6% / 25.6% | 48 / 100.0% / 73.0% / 29.5% |
| gap_event | 23 / 34.8% / 7.7% / -7.9% | 23 / 34.8% / 13.9% / -14.8% | 23 / 30.4% / -4.1% / -15.4% |
| trend_vol_expansion | 71 / 31.0% / -2.5% / -3.0% | 85 / 27.1% / -6.5% / -5.2% | 124 / 16.1% / -11.7% / -10.7% |
| noise_theta_decay | 348 / 24.7% / -3.7% / -4.3% | 278 / 14.4% / -11.4% / -10.8% | 206 / 7.3% / -20.3% / -19.6% |

Shock labels explain where winners came from, but they are ex-post labels. `noise_theta_decay` remains the main bleed bucket.

## DTE

Post-warmup, event_type=all：

| holding | best-looking bucket | trades | win rate | avg return | median return | total net PnL |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1d | 7-10 | 11 | 18.2% | -0.5% | -8.5% | 3,352.7 |
| 3d | 7-10 | 11 | 45.5% | -2.0% | -4.2% | 3,890.0 |
| 5d | 7-10 | 11 | 54.5% | 5.9% | 8.0% | 24,188.0 |

The `7-10` DTE / 5d result is the only clearly positive post-warmup DTE slice, but it has only 11 trades. It should be treated as a hypothesis for further testing, not a rule.

## Exit Policy

| policy | trades | win rate | avg return | median return | avg net PnL | total net PnL | max loss | max win | top 5 wins / total PnL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_hold_1d | 470 | 30.6% | -1.3% | -3.6% | -649.7 | -305,349.5 | -87,463.2 | 41,141.3 | -0.49 |
| fixed_hold_3d | 470 | 33.0% | 0.9% | -7.4% | -350.2 | -164,616.7 | -90,149.7 | 102,295.7 | -2.23 |
| fixed_hold_5d | 470 | 33.8% | 2.2% | -10.6% | -229.4 | -107,802.2 | -97,513.5 | 139,300.7 | -4.25 |
| stop_loss_30pct | 470 | 33.6% | 3.4% | -10.7% | 202.7 | 95,250.6 | -40,280.4 | 139,300.7 | 4.81 |

`stop_loss_30pct` improves tail loss and total PnL, but it does not fix the distribution: median return remains negative, and positive total PnL depends on a handful of large winners.

## Straddle vs Strangle

Provider-backed OTM strangle trade details were generated: 2,805 rows.

| strategy | holding | trades | avg premium | win rate | avg return | median return | max loss | max win | data source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ATM straddle | 1d | 470 | 318.9 | 30.6% | -1.3% | -3.6% | -87,463.2 | 41,141.3 | processed_trade_details |
| ATM straddle | 3d | 470 | 318.9 | 33.0% | 0.9% | -7.4% | -90,149.7 | 102,295.7 | processed_trade_details |
| ATM straddle | 5d | 470 | 318.9 | 33.8% | 2.2% | -10.6% | -97,513.5 | 139,300.7 | processed_trade_details |
| 3% OTM strangle | 1d | 468 | 138.2 | 29.5% | -0.6% | -6.1% | -14,105.5 | 53,044.7 | provider_chain |
| 3% OTM strangle | 3d | 468 | 138.2 | 31.4% | 4.9% | -14.5% | -17,978.7 | 96,902.3 | provider_chain |
| 3% OTM strangle | 5d | 468 | 138.2 | 31.0% | 10.0% | -20.4% | -20,489.2 | 131,588.3 | provider_chain |
| 5% OTM strangle | 1d | 467 | 87.7 | 30.6% | -0.1% | -7.0% | -11,131.8 | 45,665.2 | provider_chain |
| 5% OTM strangle | 3d | 467 | 87.7 | 29.3% | 9.6% | -18.3% | -18,076.9 | 93,171.1 | provider_chain |
| 5% OTM strangle | 5d | 467 | 87.7 | 28.9% | 17.9% | -26.6% | -15,797.3 | 124,031.4 | provider_chain |

OTM strangles are cheaper and more convex in average-return terms, especially at 3d/5d. But every OTM median return is negative, and the 3d/5d gains are concentrated in shock events. This is not a robust superiority conclusion; it is a stronger tail-dependence finding.

## Final Assessment

v0.3 now has the data foundation it was missing:

- true signal-date call/put closes, volume, and open interest;
- true `signal_straddle_premium_to_spot`;
- provider-backed OTM strangle comparisons;
- DTE, event type, and exit-policy panels rebuilt from the new Wind run.

The research conclusion remains conservative. Long gamma winners are real, but the distribution is still dominated by rare shocks. The next useful step is not PnL optimization; it is testing whether pre-signal features using the newly available signal premium, volume, open interest, DTE, and recent realized-volatility regime can identify shock-prone windows without simply overfitting the known 2024-2026 spike dates.
