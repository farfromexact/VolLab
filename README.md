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

## Current Research Findings

The latest v0.3 review is in `reports/v03_research_findings.md`.

The current conclusion remains deliberately conservative: Wind-backed data quality is now good enough for signal-premium and strangle research, but the evidence still does not support a stable, directly tradable long-gamma rule.

Key findings from the Wind-backed v0.3 run:

- `signal_call_close`, `signal_put_close`, signal volume, and signal open interest are now 100% complete in the v0.3 trade rows.
- ATM straddle baseline: 1,880 horizon trades, 31.8% win rate, 0.4% average return, -5.6% median return, and -805,129.8 total net PnL.
- Winners are still concentrated in ex-post `up_shock` and `down_shock` buckets. These labels explain where profits came from, but they are not entry signals.
- Post-warmup `7-10` DTE / 5d is the only clearly positive DTE slice, but it has only 11 trades.
- `stop_loss_30pct` improves tail loss and total PnL, but median return remains negative and total PnL depends on a small number of large winners.
- 3% and 5% OTM strangles are now provider-chain results, not placeholders. They are cheaper and more convex in average-return terms, but all OTM median returns remain negative.

Research discipline for the next iteration:

- Do not optimize PnL first.
- Use the newly available signal premium, volume, open interest, DTE, and realized-vol regime fields to test whether shock-prone windows can be identified before the event.
- Always report trade count, win rate, average return, median return, max loss, max win, and top-winners concentration.

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
