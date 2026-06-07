# Data Quality Report

## Conclusion

- Audited trade rows: 1,880.
- Required v0.3 field average completeness: 100.00%.
- Signal-date call/put close completeness: 100.00%.
- Bid/ask fields are reserved and may be fully missing when the provider does not supply bid/ask.
- Legacy v0.2 rows can backfill entry/exit open/close proxies, but they cannot recover true signal-date call/put closes.

## Field Source Map

| field | source_type | present_in_input | completeness |
| --- | --- | ---: | ---: |
| signal_call_close | real_provider_quote | True | 100.00% |
| signal_put_close | real_provider_quote | True | 100.00% |
| signal_call_volume | real_provider_quote | True | 100.00% |
| signal_put_volume | real_provider_quote | True | 100.00% |
| signal_call_open_interest | real_provider_quote | True | 100.00% |
| signal_put_open_interest | real_provider_quote | True | 100.00% |
| signal_straddle_close | derived_from_signal_call_put_close | True | 100.00% |
| signal_straddle_premium_to_spot | derived_from_signal_straddle_close_and_spot | True | 100.00% |
| entry_call_open | real_provider_quote_or_legacy_entry_proxy | True | 100.00% |
| entry_put_open | real_provider_quote_or_legacy_entry_proxy | True | 100.00% |
| entry_straddle_open | derived_from_entry_call_put_open | True | 100.00% |
| exit_call_close | real_provider_quote_or_legacy_exit_price | True | 100.00% |
| exit_put_close | real_provider_quote_or_legacy_exit_price | True | 100.00% |
| exit_straddle_close | derived_from_exit_call_put_close | True | 100.00% |
| signal_call_bid | reserved_bid_ask_provider_quote | True | 0.00% |
| signal_call_ask | reserved_bid_ask_provider_quote | True | 0.00% |
| signal_put_bid | reserved_bid_ask_provider_quote | True | 0.00% |
| signal_put_ask | reserved_bid_ask_provider_quote | True | 0.00% |
| call_bid_ask_spread | derived_from_bid_ask | True | 0.00% |
| put_bid_ask_spread | derived_from_bid_ask | True | 0.00% |

## Interpretation

- `real_provider_quote` fields are true Wind/provider quote fields when produced by the v0.3 backtest.
- `real_provider_quote_or_legacy_entry_proxy` and `real_provider_quote_or_legacy_exit_price` are true fields in v0.3, but old rows may use the legacy `entry_*_price` or `exit_*_price` columns.
- `derived_*` fields are arithmetic fields built from real/proxy inputs.
- Fully missing signal-date close fields mean `signal_straddle_premium_to_spot` is not reliable for old v0.2 rows.
