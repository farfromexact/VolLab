# VolLab

VolLab is a Python research project for daily ATM straddle studies on China equity index options. Version 0.2 extends the original backtest into a Timing Research Lab with feature tables, labels, event studies, rule experiments, and score component analysis.

It does not place orders, consume real-time market data, or model full volatility surfaces.

## Current Research Findings

The latest v0.2 review is in `reports/research_findings.md`. The main conclusion is deliberately conservative: current data does not show a stable, monotonic, directly tradable timing signal for buying MO ATM straddles.

Key findings:

- Past top 10% straddle-return events do not share one robust pre-signal.
- `IV - RV20` is not usually lower before top events; lower implied volatility versus realized volatility did not work as a monotonic signal.
- `range_percentile_252` is not usually lower before top events after warmup.
- `RV20_change_5d` is not reliably rising before top events.
- `straddle_premium_to_spot` is not yet fully testable because older trade records did not save signal-date option closes; `entry_premium / spot_at_signal` is only a proxy and does not show a clear cheapness edge.
- DTE has the most useful weak tendency: post-warmup top events appear more often in shorter DTE buckets, especially around 10-16 days, but the relationship is not strictly monotonic.
- 2024-09/10 and 2025-04 spikes are different event types. Both depend materially on a small number of large wins.
- `daily_rolling`, `non_overlapping`, and `one_position_at_a_time` execution modes lead to the same broad conclusion: the default rules are not robust.
- Removing warmup makes score and feature bucket conclusions weaker, not stronger.
- No core feature currently passes a strict monotonicity check.

Research discipline for the next iteration:

- Do not optimize PnL first.
- First improve signal-date option snapshot quality: call/put close, volume, open interest, and true `straddle_premium_to_spot`.
- Separate spike event types before fitting or tuning rules.
- Always report trade count, win rate, average return, median return, max loss, and top-five-wins contribution.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Mock Mode

Generate deterministic mock data:

```powershell
python scripts/generate_mock_data.py
```

Run the ATM straddle backtest and write reports to `data/processed/`:

```powershell
python scripts/run_backtest.py
```

Open the dashboard:

```powershell
streamlit run app.py
```

Run tests:

```powershell
pytest
```

## Timing Research Lab

After `scripts/run_backtest.py` has produced `data/processed/trade_details.csv`, build the v0.2 research artifacts:

```powershell
python scripts/build_feature_table.py
python scripts/run_event_study.py
python scripts/run_timing_experiments.py
python scripts/audit_metrics.py
```

Outputs:

- `data/processed/feature_table.csv`
- `data/processed/label_table.csv`
- `reports/event_study_top_daily_pnl.csv`
- `reports/event_study_top_trades.csv`
- `reports/event_study_windows.csv`
- `reports/timing_experiment_summary.csv`
- `reports/metric_audit_report.md`
- `reports/research_findings.md`

Dashboard sections:

- Overview
- Feature Lab
- Event Study
- Rule Lab
- Score Components

## Configuration

Main parameters live in `config.yaml`. The default instrument is:

- `underlying_code: "000852.SH"`
- `option_prefix: "MO"`
- `data_mode: "wind"`

Set `data_mode` to `mock`, `csv`, or `wind`.

For Wind mode, keep the Wind terminal logged in, then run Python from a normal local shell:

```powershell
python scripts/run_backtest.py
streamlit run app.py
```

If `w.start()` reports login failure inside Codex sandbox but works in a normal terminal, run the Wind-backed commands outside the sandbox. The provider reads query templates and field names from `config.yaml`.

## Wind Integration Notes

`src/wind_data_provider.py` uses:

- `w.tdays` for the trading calendar
- `w.wsd` for underlying daily bars and selected option daily bars
- `w.wset("optionchain", ...)` for option metadata
- `w.wss(..., tradeDate=...)` to merge same-day option OHLC, volume, and open interest into the option chain

Before changing instruments or vendors, confirm the exact Wind field names with the Wind code generator and place them in `config.yaml`.

Expected unified option fields are:

`date, option_code, call_put, strike, expire_date, open, high, low, close, volume, open_interest`

Expected unified underlying fields are:

`date, open, high, low, close, volume`


v1 张这样哈哈 好差的pnl
<img width="1616" height="1251" alt="image" src="https://github.com/user-attachments/assets/4ededdb3-fa10-4461-b9e2-092eb22e2c9f" />

