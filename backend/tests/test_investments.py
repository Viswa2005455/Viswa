"""Investment analytics: known answers from standard references."""

import math

import pytest

from app.finance import FinanceInputError
from app.finance.investments import (
    binomial, black_scholes, bond_analytics, fcfe_value, gordon, performance, portfolio_stats, put_call_parity,
    residual_income, strategy_payoff, two_stage_ddm,
)


def test_bond_price_duration_convexity():
    r = bond_analytics(100, 0.10, 3, 1, ytm=0.10)
    assert r["price"] == pytest.approx(100)
    assert r["macaulay_duration"] == pytest.approx(2.7355, abs=1e-4)
    assert r["modified_duration"] == pytest.approx(2.4869, abs=1e-4)
    pv = [10 / 1.1, 10 / 1.21, 110 / 1.331]
    conv = sum(v * k * (k + 1) for v, k in zip(pv, (1, 2, 3))) / (100 * 1.1 ** 2)
    assert r["convexity"] == pytest.approx(conv)
    # duration + convexity beats duration alone
    s = r["shock"]
    assert abs(s["estimate_up"] - s["actual_up"]) < abs(s["duration_only_up"] - s["actual_up"])


def test_bond_ytm_from_price():
    r = bond_analytics(100, 0.05, 10, 1, price=92.6399)
    assert r["ytm"] == pytest.approx(0.06, abs=1e-5)
    with pytest.raises(FinanceInputError):
        bond_analytics(100, 0.05, 10, 1)


def test_equity_models():
    assert gordon(2, None, 0.05, 0.10)["value"] == pytest.approx(42)
    t = two_stage_ddm(1, 0.20, 3, 0.05, 0.12)
    assert t["value"] == pytest.approx(1.2 / 1.12 + 1.44 / 1.12 ** 2 + 1.728 / 1.12 ** 3 + (1.728 * 1.05 / 0.07) / 1.12 ** 3)
    assert fcfe_value(100, 0.04, 0.10, shares=50)["per_share"] == pytest.approx(104 / 0.06 / 50)
    with pytest.raises(FinanceInputError):
        gordon(1, None, 0.1, 0.1)


def test_residual_income_matches_ddm_when_consistent():
    # constant ROE, payout and growth: RI value equals the Gordon value of the same dividends
    b, roe, payout, r = 100.0, 0.15, 0.6, 0.10
    g = roe * (1 - payout)
    ri = residual_income(b, roe, payout, r, 5, terminal_growth=g)
    ddm = gordon(None, b * roe * payout, g, r)["value"]
    assert ri["value"] == pytest.approx(ddm, rel=1e-9)
    assert ri["justified_multiples"]["pb"] == pytest.approx((roe - g) / (r - g))


def test_portfolio_two_assets():
    r = portfolio_stats([0.6, 0.4], [0.10, 0.06], [0.20, 0.10], [[1, 0.3], [0.3, 1]], risk_free=0.03)
    assert r["expected_return"] == pytest.approx(0.084)
    assert r["std_dev"] == pytest.approx(math.sqrt(0.01888))
    assert r["sharpe"] == pytest.approx((0.084 - 0.03) / math.sqrt(0.01888))
    assert sum(r["risk_contribution"]) == pytest.approx(1)
    assert len(r["frontier"]) == 41 and 0 <= r["min_variance"]["w1"] <= 1
    with pytest.raises(FinanceInputError):
        portfolio_stats([0.5, 0.4], [0.1, 0.1], [0.1, 0.1], [[1, 0], [0, 1]])
    with pytest.raises(FinanceInputError):  # not positive semi-definite
        portfolio_stats([1 / 3] * 3, [0.1] * 3, [0.1] * 3, [[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]])


def test_performance_measures():
    b = [0.01, -0.02, 0.03, 0.015, -0.005, 0.02, 0.01, -0.01, 0.025, 0.005, 0.0, 0.012]
    p = [x * 1.2 + 0.001 for x in b]  # beta 1.2, small alpha
    r = performance(p, b, 0.04, 12)
    assert r["beta"] == pytest.approx(1.2)
    assert r["treynor"] == pytest.approx((r["annual_return"] - 0.04) / 1.2)
    assert r["jensens_alpha"] == pytest.approx(r["annual_return"] - (0.04 + 1.2 * (r["benchmark_return"] - 0.04)))
    assert r["max_drawdown"] <= 0


def test_black_scholes_reference_values():
    r = black_scholes(100, 100, 1, 0.05, 0.20)
    assert r["call"] == pytest.approx(10.4506, abs=1e-4) and r["put"] == pytest.approx(5.5735, abs=1e-4)
    assert r["greeks"]["call"]["delta"] == pytest.approx(0.6368, abs=1e-4)
    assert abs(r["parity_check"]) < 1e-9


def test_binomial_converges_and_american_premium():
    eu = binomial(100, 100, 1, 0.05, 0.20, steps=500, kind="put", american=False)["value"]
    am = binomial(100, 100, 1, 0.05, 0.20, steps=500, kind="put", american=True)["value"]
    assert eu == pytest.approx(5.5735, abs=0.01)
    assert am > eu and am == pytest.approx(6.09, abs=0.02)
    call_am = binomial(100, 100, 1, 0.05, 0.20, steps=500, kind="call", american=True)["value"]
    assert call_am == pytest.approx(10.4506, abs=0.01)  # no early exercise without dividends


def test_parity_and_strategies():
    bs = black_scholes(100, 100, 1, 0.05, 0.2)
    assert "no arbitrage" in put_call_parity(bs["call"], bs["put"], 100, 100, 0.05, 1)["action"]
    assert "overpriced" in put_call_parity(bs["call"] + 1, bs["put"], 100, 100, 0.05, 1)["action"]
    straddle = strategy_payoff([{"type": "call", "position": "long", "strike": 100, "premium": 10},
                                {"type": "put", "position": "long", "strike": 100, "premium": 5}], (50, 150))
    assert straddle["net_premium"] == 15
    assert sorted(round(b, 1) for b in straddle["breakevens"]) == [85.0, 115.0]


def test_investment_endpoints(client):
    r = client.post("/api/investments/bond", json={"face": 100, "coupon_rate": 0.1, "years": 3, "freq": 1, "ytm": 0.1})
    assert r.status_code == 200 and round(r.json()["macaulay_duration"], 4) == 2.7355
    r = client.post("/api/investments/options", json={"s": 100, "k": 100, "t": 1, "r": 0.05, "sigma": 0.2})
    assert r.status_code == 200 and round(r.json()["black_scholes"]["call"], 4) == 10.4506
    assert client.post("/api/investments/equity", json={"model": "gordon", "d0": 2, "g": 0.05, "r": 0.04}).status_code == 422
