# VolLab

VolLab is a small Python research project for daily ATM straddle studies on China equity index options. Version 0.1 focuses on one instrument, mock data, and historical daily backtests only.

It does not place orders, consume real-time market data, or model full volatility surfaces.

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

## Configuration

Main parameters live in `config.yaml`. The default instrument is:

- `underlying_code: "000852.SH"`
- `option_prefix: "MO"`
- `data_mode: "mock"`

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
