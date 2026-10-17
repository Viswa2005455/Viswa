"""Accounting and audit schedules: textbook known answers."""

import pytest

from app.finance import FinanceInputError
from app.finance.accounting import (
    Dilutive, TempDiff, bond_schedule, deferred_tax, depreciation_schedule, eps, lease_schedule, materiality,
)


def balanced(je):
    d = sum(l["debit"] or 0 for l in je["lines"])
    c = sum(l["credit"] or 0 for l in je["lines"])
    return abs(d - c) < 0.02


def test_bond_discount_effective_interest():
    r = bond_schedule(100_000, 0.08, 0.10, 5, 2)
    assert r["issue_price"] == pytest.approx(92_278.26, abs=0.01)
    assert r["kind"] == "discount"
    p1 = r["schedule"][0]
    assert p1["interest"] == pytest.approx(4_613.91, abs=0.01) and p1["amortisation"] == pytest.approx(613.91, abs=0.01)
    assert r["schedule"][-1]["closing"] == 100_000
    assert all(balanced(j) for j in r["journal_entries"])


def test_bond_premium_and_investor():
    r = bond_schedule(100_000, 0.10, 0.08, 5, 2)
    assert r["issue_price"] == pytest.approx(108_110.90, abs=0.01) and r["kind"] == "premium"
    assert r["schedule"][0]["amortisation"] < 0
    inv = bond_schedule(100_000, 0.10, 0.08, 5, 2, "investor")
    assert all(balanced(j) for j in inv["journal_entries"])
    with pytest.raises(FinanceInputError):
        bond_schedule(100_000, 0.1, 0.08, 5.3, 2)


def test_lease_finance_arrears_and_advance():
    r = lease_schedule(10_000, 5, 0.06, timing="arrears")
    assert r["initial_liability"] == pytest.approx(42_123.64, abs=0.01)
    assert r["schedule"][0]["interest"] == pytest.approx(2_527.42, abs=0.01)
    assert r["schedule"][-1]["closing_liability"] == 0 and r["schedule"][-1]["closing_rou"] == 0
    assert r["schedule"][0]["expense"]["amortisation"] == pytest.approx(42_123.64 / 5, abs=0.01)
    assert all(balanced(j) for j in r["journal_entries"])
    adv = lease_schedule(10_000, 5, 0.06, timing="advance", initial_direct_costs=500, incentives=1_000)
    assert adv["initial_liability"] == pytest.approx(44_651.06, abs=0.01)
    assert adv["initial_rou_asset"] == pytest.approx(44_651.06 + 500 - 1_000, abs=0.01)
    assert all(balanced(j) for j in adv["journal_entries"])


def test_lease_operating_straight_line():
    r = lease_schedule(10_000, 5, 0.06, timing="arrears", classification="operating")
    assert r["straight_line_cost"] == 10_000
    first = r["schedule"][0]
    assert first["expense"]["total"] == 10_000
    assert first["rou_amortisation"] == pytest.approx(10_000 - 2_527.42, abs=0.01)
    assert sum(x["rou_amortisation"] for x in r["schedule"]) == pytest.approx(r["initial_rou_asset"], abs=0.01)
    assert all(balanced(j) for j in r["journal_entries"])


def test_depreciation_methods():
    sl = depreciation_schedule(10_000, 1_000, 5)
    assert [round(x["depreciation"]) for x in sl["schedule"]] == [1800] * 5
    syd = depreciation_schedule(10_000, 1_000, 5, "syd")
    assert syd["schedule"][0]["depreciation"] == pytest.approx(3_000)
    ddb = depreciation_schedule(10_000, 1_000, 5, "ddb")
    assert [round(x["depreciation"], 2) for x in ddb["schedule"]] == [4000, 2400, 1440, 864, 296]
    assert ddb["schedule"][-1]["closing_nbv"] == pytest.approx(1_000)
    units = depreciation_schedule(10_000, 1_000, 3, "units", units=[100, 200, 300])
    assert units["schedule"][2]["depreciation"] == pytest.approx(4_500)
    with pytest.raises(FinanceInputError):
        depreciation_schedule(10_000, 1_000, 3, "units", units=[1, 2])


def test_eps_basic_and_diluted_with_antidilution():
    r = eps(1_000_000, 100_000, 500_000, 25, [
        Dilutive("options", "Options", 50_000, exercise_price=20),
        Dilutive("convertible_debt", "Bonds", 100_000, interest_after_tax=120_000),
        Dilutive("convertible_preferred", "Preferred", 50_000, preferred_dividends=100_000),
    ])
    assert r["basic"] == pytest.approx(1.80)
    sec = {s["name"]: s for s in r["securities"]}
    assert sec["Options"]["incremental_shares"] == pytest.approx(10_000) and sec["Options"]["included"]
    assert sec["Bonds"]["included"] and not sec["Preferred"]["included"]
    assert r["diluted"] == pytest.approx(1_020_000 / 610_000)


def test_eps_loss_is_never_diluted():
    r = eps(-100_000, 0, 100_000, 10, [Dilutive("options", "Options", 10_000, exercise_price=5)])
    assert r["diluted"] == r["basic"] == -1.0


def test_deferred_tax():
    r = deferred_tax([TempDiff("PPE", "asset", 100_000, 70_000), TempDiff("Warranty provision", "liability", 20_000, 0)],
                     0.25, current_tax=50_000, opening_net_dtl=1_000)
    assert r["total_dtl"] == 7_500 and r["total_dta"] == 5_000 and r["net_dtl"] == 2_500
    assert r["deferred_tax_expense"] == 1_500 and r["income_tax_expense"] == 51_500
    assert balanced(r["journal_entries"][0])


def test_materiality():
    r = materiality({"profit_before_tax": 1_000_000, "revenue": 20_000_000}, "profit_before_tax", 0.05)
    assert r["overall"] == 50_000 and r["performance"] == 37_500 and r["clearly_trivial"] == 2_500
    assert len(r["ranges"]) == 2 and not r["notes"]
    r = materiality({"revenue": 20_000_000}, "revenue", 0.05)
    assert r["notes"]
    with pytest.raises(FinanceInputError):
        materiality({}, "revenue", 0.01)


def test_accounting_endpoints(client):
    r = client.post("/api/accounting/bond", json={"face": 100000, "coupon_rate": 0.08, "market_rate": 0.10, "years": 5, "payments_per_year": 2})
    assert r.status_code == 200 and r.json()["issue_price"] == pytest.approx(92_278.26, abs=0.01)
    r = client.post("/api/accounting/eps", json={"net_income": 1000, "preferred_dividends": 0, "weighted_shares": 100, "average_price": 10,
                                                "securities": [{"kind": "options", "name": "O", "shares": 10, "exercise_price": 5}]})
    assert r.status_code == 200 and r.json()["diluted"] < r.json()["basic"]
    assert client.post("/api/accounting/lease", json={"payment": 1, "periods": 2, "annual_rate": 0.1, "timing": "sometimes"}).status_code == 422
