# VolLab

VolLab is a Python research project for daily long-gamma studies on China equity index options, focused on MO options on `000852.SH`.

Version 0.3 extends the original ATM straddle backtest into an event-driven research lab with:

- Wind-backed signal-date option quality fields
- horizon labels
- event classification
- DTE research
- exit-policy experiments
- ATM straddle vs OTM strangle comparison
- Streamlit dashboard pages for the v0.3 research outputs

VolLab does not place orders, consume real-time market data, or model full volatility surfaces.

## Final Research Conclusion / 最终研究结论

Detailed research reports:

- v0.2 timing research: `reports/research_findings.md`
- v0.3 Wind-backed event research: `reports/v03_research_findings.md`

### 中文结论

VolLab 到 v0.3 可以作为一个完整的阶段性研究项目收尾。它完成了两件事：

1. v0.2 回答了“是否存在稳定、单调、可直接交易的 ATM straddle 买入前置信号”。
2. v0.3 补齐了 Wind 真实期权数据质量，并把研究拆成 data quality、event type、DTE、exit policy、straddle vs strangle 几个可审计模块。

最终结论很明确：当前证据不支持把 MO ATM straddle 或 OTM strangle 做成一个稳定的机械化 long-gamma 买入策略。long gamma 的赢家是真实存在的，但收益分布主要由少数冲击事件贡献；多数普通交易日仍然承受 theta decay 和负中位收益。

v0.2 的核心发现：

- 过去 top 10% straddle return 事件没有稳定共同前置信号。
- `IV - RV20` 并没有在大行情前稳定偏低，因此“IV 相对 RV 越便宜越好”不是可靠单调规则。
- `range_percentile_252` 不稳定偏低，`RV20_change_5d` 也没有稳定提前抬升。
- 旧数据缺少 signal-date call/put close，所以当时无法严肃判断真实 `straddle_premium_to_spot`。
- DTE 是最值得继续研究的变量之一，但也只是弱倾向，不是独立交易规则。
- 2024-09/10 与 2025-04 的大行情不是同一种事件，不能混成一个统一的稳定信号。
- 默认 timing rules 在 daily rolling、non-overlapping、one-position-at-a-time 三种执行模式下都不稳健。
- 没有核心 feature 通过严格单调性检查。

v0.3 的核心发现：

- Wind-backed v0.3 回测已补齐 signal-date option quality：`signal_call_close`、`signal_put_close`、signal volume、signal open interest 完整率均为 100%。
- ATM straddle baseline：1,880 horizon trades，胜率 31.8%，平均收益 0.4%，中位收益 -5.6%，总净 PnL -805,129.8。
- `up_shock` 和 `down_shock` 能解释赢家来自哪里，但它们是事后标签，不是入场信号。
- post-warmup 的 `7-10` DTE / 5d 是唯一明显为正的 DTE 切片，但只有 11 笔，不能视作稳定规律。
- `stop_loss_30pct` 改善了尾部亏损和总 PnL，但中位收益仍为负，且 total PnL 依赖少数大赢家。
- 3%/5% OTM strangle 已经是真实 provider-chain 结果。它们更便宜，平均收益弹性更高，但所有 OTM strangle 的中位收益仍为负，说明尾部依赖更强，而不是策略质量更稳。

项目收尾判断：

- 可以接受的结论：MO long gamma 在冲击行情里有显著 convex payoff；短 DTE、真实 signal premium、volume/open interest、近期 realized-vol regime 值得作为下一阶段研究变量。
- 不可以接受的结论：目前不能声称已经找到稳定买入规则，也不能只根据平均收益、top-event 表现或少数 spike 来上线交易。
- 本仓库现在更适合作为研究归档和 dashboard 展示，不应被理解为交易信号系统。

如果未来继续研究，重点不应是直接优化 PnL，而应是验证：能否在事前用 signal premium、DTE、option activity、realized-vol regime 和事件日历识别 shock-prone windows。任何新规则都必须同时报告 trade count、win rate、average return、median return、max loss、max win 和 top-winners concentration。

### English Conclusion

VolLab v0.3 is a complete research checkpoint. It answered two separate questions:

1. v0.2 tested whether MO ATM straddle winners shared stable, monotonic, directly tradable pre-signal features.
2. v0.3 repaired the real-data foundation with Wind-backed signal-date option snapshots, then decomposed the problem into data quality, event type, DTE, exit policy, and straddle-versus-strangle panels.

The final conclusion is conservative and clear: the current evidence does not support a stable mechanical long-gamma buying strategy in MO ATM straddles or OTM strangles. Long-gamma winners are real, but the payoff distribution is dominated by a small number of shock events. Most ordinary trading days still suffer from theta decay and negative median returns.

Core v0.2 findings:

- Top-decile straddle-return events did not share one stable pre-signal.
- `IV - RV20` was not reliably lower before the biggest winners, so “cheaper IV versus RV is better” did not hold as a monotonic rule.
- `range_percentile_252` was not reliably low, and `RV20_change_5d` was not reliably rising before the events.
- The old backtest did not store signal-date call/put closes, so true `straddle_premium_to_spot` could not be tested properly at that stage.
- DTE was one of the more useful weak tendencies, but it was not an independent rule.
- The 2024-09/10 and 2025-04 spikes were different event types, not one stable repeatable pattern.
- Default timing rules were not robust under daily rolling, non-overlapping, or one-position-at-a-time execution modes.
- No core feature passed a strict monotonicity check.

Core v0.3 findings:

- Wind-backed v0.3 trade rows now have 100% completeness for signal-date call/put closes, signal volume, and signal open interest.
- ATM straddle baseline: 1,880 horizon trades, 31.8% win rate, 0.4% average return, -5.6% median return, and -805,129.8 total net PnL.
- `up_shock` and `down_shock` explain where winners came from, but they are ex-post labels, not entry signals.
- Post-warmup `7-10` DTE / 5d is the only clearly positive DTE slice, but it has only 11 trades.
- `stop_loss_30pct` improves tail loss and total PnL, but median return remains negative and total PnL depends on a small number of large winners.
- 3% and 5% OTM strangles are now real provider-chain results. They are cheaper and more convex in average-return terms, but all OTM median returns remain negative, which points to stronger tail dependence rather than a more stable strategy.

Final project assessment:

- Acceptable conclusion: MO long gamma has meaningful convex payoff in shock regimes; short DTE, true signal premium, volume/open interest, and recent realized-volatility regime are useful variables for future research.
- Unacceptable conclusion: this project has not found a robust production trading rule, and results should not be judged only by average return, top-event behavior, or a handful of spikes.
- The repository should now be treated as a research archive and dashboard, not as a live trading signal engine.

If the project continues, the next question should not be “how do we optimize PnL?” It should be: can pre-signal premium, DTE, option activity, realized-volatility regime, and event calendars identify shock-prone windows before the event? Any new rule must report trade count, win rate, average return, median return, max loss, max win, and top-winners concentration.

## Dashboard

Run the dashboard locally:

```powershell
streamlit run app.py
```

Dashboard sections:

- Overview
- Feature Lab
- Event Study
- Rule Lab
- Score Components
- Data Quality
- Event Type Lab
- DTE Lab
- Exit Policy Lab
- Straddle vs Strangle

When `data_mode=wind` and the committed `data/processed/*.csv` files exist, the dashboard reads the precomputed CSV outputs instead of initializing WindPy. This is intentional so Streamlit Cloud can deploy without Wind Terminal access.

## Streamlit Cloud Deployment

The repository includes the current Wind-backed processed CSV outputs:

- `data/processed/trade_details.csv`
- `data/processed/feature_table.csv`
- `data/processed/label_table.csv`
- `data/processed/label_table_by_horizon.csv`
- `data/processed/event_classification.csv`
- `reports/*.csv`

On Streamlit Cloud, the app should display these committed numbers directly. It should not need WindPy or a Wind Terminal session unless the processed CSV files are removed.

If you rerun Wind locally and want the deployed dashboard to update, commit and push the regenerated `data/processed/*.csv` and `reports/*.csv` files.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run tests:

```powershell
pytest
```

## Wind-Backed v0.3 Pipeline

For Wind mode, keep the Wind terminal logged in, then run Python from a normal local shell. In restricted Codex sandboxes, `w.start()` may return login failure even when Wind works in a normal shell.

Full v0.3 rebuild:

```powershell
python scripts/run_backtest.py
python scripts/audit_data_quality.py
python scripts/build_feature_table.py
python scripts/build_label_table_by_horizon.py
python scripts/run_event_classification.py
python scripts/run_dte_research.py
python scripts/run_exit_policy_experiments.py
python scripts/run_straddle_vs_strangle.py
pytest
```

Main outputs:

- `data/processed/trade_details.csv`
- `data/processed/trade_details_v03_quality_fields.csv`
- `data/processed/feature_table.csv`
- `data/processed/label_table.csv`
- `data/processed/label_table_by_horizon.csv`
- `data/processed/event_classification.csv`
- `reports/data_quality_report.md`
- `reports/event_type_summary.csv`
- `reports/dte_research_summary.csv`
- `reports/exit_policy_summary.csv`
- `reports/straddle_vs_strangle_summary.csv`
- `reports/strangle_trade_details.csv`
- `reports/v03_research_findings.md`

## Mock Mode

Generate deterministic mock data:

```powershell
python scripts/generate_mock_data.py
```

Run the ATM straddle backtest and write reports to `data/processed/`:

```powershell
python scripts/run_backtest.py
```

## Configuration

Main parameters live in `config.yaml`. The default instrument is:

- `underlying_code: "000852.SH"`
- `option_prefix: "MO"`
- `data_mode: "wind"`

Set `data_mode` to `mock`, `csv`, or `wind`.

## Wind Integration Notes

`src/wind_data_provider.py` uses:

- `w.tdays` for the trading calendar
- `w.wsd` for underlying daily bars and selected option daily bars
- `w.wset("optionchain", ...)` for option metadata when configured
- `w.wss(..., tradeDate=...)` to merge same-day option OHLC, volume, and open interest into the option chain

Current config uses synthetic MO contract-code generation with Wind quote snapshots, which avoids depending entirely on `w.wset("optionchain", ...)` availability.

Before changing instruments or vendors, confirm the exact Wind field names with the Wind code generator and place them in `config.yaml`.

Expected unified option fields:

`date, option_code, call_put, strike, expire_date, open, high, low, close, volume, open_interest`

Expected unified underlying fields:

`date, open, high, low, close, volume`
