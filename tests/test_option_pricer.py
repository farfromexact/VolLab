import math

from src.option_pricer import bs_delta, bs_gamma, bs_price, bs_vega, implied_vol


def test_implied_vol_recovers_input_sigma():
    S = 5000
    K = 5000
    T = 30 / 252
    r = 0.02
    sigma = 0.24
    price = bs_price(S, K, T, r, sigma, "C")
    recovered = implied_vol(price, S, K, T, r, "C")
    assert math.isclose(recovered, sigma, rel_tol=1e-5, abs_tol=1e-5)


def test_put_call_parity():
    S = 5000
    K = 5100
    T = 45 / 252
    r = 0.02
    sigma = 0.22
    call = bs_price(S, K, T, r, sigma, "C")
    put = bs_price(S, K, T, r, sigma, "P")
    assert math.isclose(call - put, S - K * math.exp(-r * T), rel_tol=1e-8, abs_tol=1e-8)


def test_greeks_are_finite_for_valid_input():
    S = 5000
    K = 5000
    T = 30 / 252
    r = 0.02
    sigma = 0.2
    assert math.isfinite(bs_delta(S, K, T, r, sigma, "C"))
    assert bs_gamma(S, K, T, r, sigma) > 0
    assert bs_vega(S, K, T, r, sigma) > 0


def test_invalid_price_returns_nan_iv():
    assert math.isnan(implied_vol(0, 5000, 5000, 30 / 252, 0.02, "C"))

