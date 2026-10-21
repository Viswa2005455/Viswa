"""Reverse DCF and Monte Carlo valuation range."""

from dataclasses import replace

import pytest

from app.finance import FinanceInputError
from app.finance.dcf import DCFInputs, run_dcf
from app.finance.valuation_range import Distribution, monte_carlo, reverse_dcf

BASE = DCFInputs(base_revenue=1000, revenue_growth=[0.05] * 5, ebit_margin=[0.2], tax_rate=0.25, da_pct_revenue=0.03,
                 capex_pct_revenue=0.04, nwc_pct_revenue=0.1, wacc=0.10, terminal_growth=0.03, debt=200, cash=100,
                 shares_outstanding=100)


def test_reverse_dcf_recovers_growth():
    price = run_dcf(replace(BASE, revenue_growth=[0.08] * 5)).value_per_share
    r = reverse_dcf(BASE, price)
    assert r.implied == pytest.approx(0.08, abs=1e-6)
    assert "more optimistic than" in r.message and r.base_value == pytest.approx(0.05)
    assert len(r.curve) > 10


def test_reverse_dcf_wacc_and_margin():
    price = run_dcf(replace(BASE, wacc=0.11)).value_per_share
    assert reverse_dcf(BASE, price, "wacc").implied == pytest.approx(0.11, abs=1e-6)
    price = run_dcf(replace(BASE, ebit_margin=[0.15])).value_per_share
    r = reverse_dcf(BASE, price, "ebit_margin")
    assert r.implied == pytest.approx(0.15, abs=1e-6) and "less optimistic" in r.message


def test_reverse_dcf_no_solution_and_validation():
    r = reverse_dcf(BASE, 1e9)
    assert r.implied is None and "No revenue growth" in r.message
    with pytest.raises(FinanceInputError):
        reverse_dcf(replace(BASE, shares_outstanding=None), 100)
    with pytest.raises(FinanceInputError):
        reverse_dcf(BASE, 100, "exit_multiple")


def test_monte_carlo_is_reproducible_and_centred():
    d = [Distribution("revenue_growth", "normal", 0.05, 0.0001), Distribution("wacc", "triangular", 0.0999, 0.10, 0.1001)]
    a = monte_carlo(BASE, d, n=500, seed=7)
    b = monte_carlo(BASE, d, n=500, seed=7)
    assert a.percentiles == b.percentiles
    base = run_dcf(BASE).value_per_share
    assert a.percentiles["p50"] == pytest.approx(base, rel=0.01)
    p = a.percentiles
    assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]
    assert a.invalid == 0 and a.valid == 500 and len(a.histogram) == 30


def test_monte_carlo_counts_invalid_draws_and_probability():
    d = [Distribution("wacc", "uniform", 0.01, 0.12)]  # below terminal growth (3%) is invalid
    r = monte_carlo(BASE, d, n=1000, seed=1, target=run_dcf(BASE).value_per_share)
    assert 100 < r.invalid < 300  # about (0.03 - 0.01) / 0.11 = 18% of draws
    assert r.valid + r.invalid == 1000
    assert 0 < r.prob_above_target < 1
    assert any("excluded" in n for n in r.notes)


def test_monte_carlo_validation():
    with pytest.raises(FinanceInputError):
        monte_carlo(BASE, [])
    with pytest.raises(FinanceInputError):
        monte_carlo(BASE, [Distribution("wacc", "triangular", 0.12, 0.10, 0.08)])
    with pytest.raises(FinanceInputError):
        monte_carlo(BASE, [Distribution("nope", "uniform", 0, 1)])
    with pytest.raises(FinanceInputError):
        monte_carlo(BASE, [Distribution("wacc", "uniform", 0.08, 0.12)], n=50)


MODEL = {"base_revenue": 1000, "revenue_growth": [0.05] * 5, "ebit_margin": [0.2], "tax_rate": 0.25, "da_pct_revenue": 0.03,
         "capex_pct_revenue": 0.04, "nwc_pct_revenue": 0.1, "wacc": 0.1, "terminal_growth": 0.03, "debt": 200, "cash": 100,
         "shares_outstanding": 100}


def test_endpoints(client):
    r = client.post("/api/finance/dcf/reverse", json={"model": MODEL, "target": 50})
    assert r.status_code == 200, r.text
    assert "implied" in r.json()
    r = client.post("/api/finance/dcf/monte-carlo", json={"model": MODEL, "simulations": 300,
                                                          "distributions": [{"variable": "wacc", "kind": "uniform", "a": 0.08, "b": 0.12}]})
    assert r.status_code == 200, r.text
    assert r.json()["valid"] == 300
    bad = client.post("/api/finance/dcf/monte-carlo", json={"model": MODEL, "distributions": [{"variable": "wacc", "kind": "normal", "a": 0.1, "b": -1}]})
    assert bad.status_code == 422
