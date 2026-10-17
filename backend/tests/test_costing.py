"""Cost & management accounting: textbook-style known answers."""

import pytest

from app.finance import FinanceInputError
from app.finance.costing import (
    LFProduct, MaterialIn, ProductCVP, absorption_vs_marginal, cvp, fixed_overhead_variances, labour_variances,
    limiting_factor, material_variances, sales_variances, variable_overhead_variances,
)


def vals(res):
    return {v.name: (round(v.value, 6), v.nature) for v in res["variances"]}


def test_material_single():
    r = material_variances([MaterialIn("Steel", 1000, 10, 1100, 9.5)])
    v = vals(r)
    assert v["Material cost variance"] == (-450, "A")
    assert v["Material price variance"] == (550, "F")
    assert v["Material usage variance"] == (-1000, "A")
    assert r["reconciles"]


def test_material_mix_and_yield():
    r = material_variances([MaterialIn("A", 60, 2, 70, 2.2), MaterialIn("B", 40, 5, 35, 4.8)])
    v = vals(r)
    assert v["Material mix variance"] == (21, "F")
    assert v["Material yield variance"] == (-16, "A")
    assert v["Material usage variance"][0] == pytest.approx(21 - 16)


def test_labour_with_idle_time():
    v = vals(labour_variances(1000, 10, 1100, 1050, 11))
    assert v["Labour cost variance"] == (-2100, "A")
    assert v["Labour rate variance"] == (-1100, "A")
    assert v["Idle time variance"] == (-500, "A")
    assert v["Labour efficiency variance"] == (-500, "A")


def test_overheads():
    v = vals(variable_overhead_variances(1100, 4, 1050, 4500))
    assert v["Variable overhead expenditure variance"] == (-300, "A")
    assert v["Variable overhead efficiency variance"] == (200, "F")
    f = fixed_overhead_variances(10000, 10500, 1000, 1100, 1050)
    v = vals(f)
    assert f["absorption_rate"] == 10
    assert v["Fixed overhead cost (total) variance"] == (500, "F")
    assert v["Fixed overhead expenditure variance"] == (-500, "A")
    assert v["Fixed overhead volume variance"] == (1000, "F")
    assert v["Capacity variance"] == (500, "F") and v["Efficiency variance"] == (500, "F")
    assert f["reconciles"]


def test_sales():
    v = vals(sales_variances(1000, 50, 1100, 48, 20))
    assert v["Sales price variance"] == (-2200, "A")
    assert v["Sales volume variance (contribution)"] == (2000, "F")


def test_cvp_single_product():
    r = cvp([ProductCVP("X", 50, 30, 1)], 40000, target_profit=30000, tax_rate=0.25, expected_units=3000)
    assert r["contribution_per_unit"] == 20 and r["pv_ratio"] == pytest.approx(0.4)
    assert r["breakeven_units"] == 2000 and r["breakeven_sales"] == 100000
    assert r["target"]["units"] == pytest.approx(4000)
    e = r["at_expected"]
    assert e["profit"] == 20000 and e["margin_of_safety_units"] == 1000
    assert e["margin_of_safety_pct"] == pytest.approx(1 / 3) and e["operating_leverage"] == pytest.approx(3)


def test_cvp_multi_product_and_errors():
    r = cvp([ProductCVP("A", 10, 6, 3), ProductCVP("B", 20, 10, 1)], 11000)
    assert r["contribution_per_unit"] == pytest.approx((3 * 4 + 1 * 10) / 4)
    assert r["products"][0]["breakeven_units"] == pytest.approx(r["breakeven_units"] * 0.75)
    with pytest.raises(FinanceInputError):
        cvp([ProductCVP("A", 10, 12, 1)], 100)


def test_absorption_vs_marginal_reconciles():
    r = absorption_vs_marginal(20, 8, 1, 30000, 10000, 12000, 10000, 0, 5000)
    assert r["oar"] == 3 and r["closing_units"] == 2000
    assert r["marginal"]["profit"] == 75000
    assert r["absorption"]["over_under_absorption"] == 6000
    assert r["absorption"]["profit"] == 81000
    assert r["reconciliation"]["explained"] == 6000 and r["reconciliation"]["reconciles"]
    with pytest.raises(FinanceInputError):
        absorption_vs_marginal(20, 8, 1, 30000, 10000, 1000, 5000, 0, 0)


def test_limiting_factor_ranks_by_contribution_per_resource():
    r = limiting_factor([LFProduct("A", 10, 2, 100), LFProduct("B", 12, 4, 100), LFProduct("C", 6, 1, 100)], 400, fixed_costs=1000)
    plan = {p["name"]: p for p in r["plan"]}
    assert [p["name"] for p in r["plan"]] == ["C", "A", "B"]
    assert plan["C"]["units"] == 100 and plan["A"]["units"] == 100 and plan["B"]["units"] == 25
    assert r["total_contribution"] == 1900 and r["profit"] == 900 and r["is_binding"]


def test_costing_endpoints(client):
    r = client.post("/api/costing/materials", json={"materials": [{"name": "Steel", "std_qty": 1000, "std_price": 10, "actual_qty": 1100, "actual_price": 9.5}]})
    assert r.status_code == 200, r.text
    assert r.json()["variances"][0]["nature"] == "A"
    assert client.post("/api/costing/cvp", json={"products": [{"name": "X", "price": 50, "variable_cost": 30, "mix": 1}], "fixed_costs": 40000}).json()["breakeven_units"] == 2000
    bad = client.post("/api/costing/labour", json={"std_hours": 1, "std_rate": 1, "hours_paid": 1, "hours_worked": 2, "actual_rate": 1})
    assert bad.status_code == 422
