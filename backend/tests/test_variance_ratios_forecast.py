from decimal import Decimal

import pytest

from app.finance import FinanceInputError
from app.finance import variance as v
from app.finance.ratios import compute_ratios
from app.finance import forecasting as fc


# ---------------- Variance ----------------

def test_revenue_favourable_and_expense_adverse():
    rev = v.analyse_line("Sales", "revenue", 100, 120)
    assert rev.variance == 20 and rev.variance_pct == 20 and rev.status == "favourable"
    exp = v.analyse_line("Rent", "expense", 50, 60)
    assert exp.variance == 10 and exp.status == "adverse" and exp.profit_impact == -10


def test_on_budget():
    assert v.analyse_line("x", "expense", 10, 10).status == "on_budget"


def test_zero_budget_has_no_percentage():
    line = v.analyse_line("New line", "expense", 0, 25)
    assert line.variance == 25 and line.variance_pct is None
    assert "zero" in line.notes[0]


def test_negative_budget_uses_absolute_denominator():
    line = v.analyse_line("Other income", "revenue", -100, -50)
    assert line.variance == 50
    assert line.variance_pct == 50
    assert line.status == "favourable"
    assert line.notes


def test_decimal_precision():
    line = v.analyse_line("x", "revenue", 0.1, 0.3)
    assert line.variance == Decimal("0.2")


def test_missing_values_rejected():
    with pytest.raises(FinanceInputError):
        v.analyse_line("x", "revenue", None, 10)


def test_report_totals_and_contributors():
    rep = v.analyse([
        {"name": "Sales", "kind": "revenue", "budget": 1000, "actual": 1100},
        {"name": "COGS", "kind": "expense", "budget": 600, "actual": 700},
        {"name": "Rent", "kind": "expense", "budget": 100, "actual": 90},
    ])
    assert rep.totals["revenue"].variance == 100
    assert rep.totals["expense"].variance == 90
    assert rep.totals["profit"].budget == 300 and rep.totals["profit"].actual == 310
    assert rep.totals["profit"].status == "favourable"
    assert [l.name for l in rep.largest_contributors][:2] in (["Sales", "COGS"], ["COGS", "Sales"])


def test_price_volume_sums_to_total():
    r = v.sales_price_volume(10, 100, 11, 90)
    assert r.price_variance == 90 and r.volume_variance == -100
    assert r.price_variance + r.volume_variance == r.total_variance


def test_flexible_budget():
    r = v.flexible_budget_cost(1000, 5, 100, 120, 1700)
    assert r.static_budget == 1500 and r.flexed_budget == 1600
    assert r.flexible_budget_variance == 100 and r.activity_variance == 100
    assert r.total_variance == 200


# ---------------- Ratios ----------------

def by_key(rs):
    return {r.key: r for r in rs}


def test_ratio_known_answers():
    rs = by_key(compute_ratios({"current_assets": 300, "current_liabilities": 150, "inventory": 60,
                                "revenue": 1000, "cogs": 600, "receivables": 100, "accounts_payable": 50}))
    assert rs["current_ratio"].value == pytest.approx(2.0)
    assert rs["quick_ratio"].value == pytest.approx(1.6)
    assert rs["gross_margin"].value == pytest.approx(40.0)
    assert rs["dso"].value == pytest.approx(36.5)
    assert rs["dio"].value == pytest.approx(36.5)
    assert rs["dpo"].value == pytest.approx(50 / 600 * 365)
    assert rs["ccc"].value == pytest.approx(36.5 + 36.5 - 50 / 600 * 365)


def test_ratio_missing_inputs_not_zero():
    r = by_key(compute_ratios({"current_assets": 300}))["current_ratio"]
    assert r.status == "missing" and r.value is None
    assert "Current liabilities" in r.missing


def test_zero_denominator_undefined():
    r = by_key(compute_ratios({"current_assets": 300, "current_liabilities": 0}))["current_ratio"]
    assert r.status == "undefined" and r.value is None


def test_negative_equity_roe_not_meaningful():
    r = by_key(compute_ratios({"net_income": 50, "total_equity": -10}))["roe"]
    assert r.status == "undefined"


def test_average_balances_used_when_prior_supplied():
    r = by_key(compute_ratios({"net_income": 100, "total_assets": 1200, "total_assets_prior": 800}))["roa"]
    assert r.value == pytest.approx(10.0)
    r2 = by_key(compute_ratios({"net_income": 100, "total_assets": 1200}))["roa"]
    assert r2.value == pytest.approx(100 / 1200 * 100)
    assert any("Closing" in n for n in r2.notes)


def test_valuation_ratios():
    rs = by_key(compute_ratios({"net_income": 100, "shares_outstanding": 50, "share_price": 30,
                                "total_equity": 500, "total_debt": 200, "cash": 50,
                                "operating_income": 150, "depreciation_amortization": 50}))
    assert rs["eps"].value == pytest.approx(2)
    assert rs["pe"].value == pytest.approx(15)
    assert rs["pb"].value == pytest.approx(3)
    assert rs["ev_ebitda"].value == pytest.approx((1500 + 200 - 50) / 200)
    assert rs["net_debt_ebitda"].value == pytest.approx(0.75)


# ---------------- Forecasting ----------------

def test_linear_on_perfect_line():
    r = fc.forecast([10, 12, 14, 16, 18, 20], "linear", 3)
    assert r.forecast == pytest.approx([22, 24, 26])
    assert r.backtest["mae"] == pytest.approx(0, abs=1e-9)


def test_linear_interval_contains_point():
    r = fc.forecast([10, 13, 13, 17, 18, 22, 21, 25], "linear", 2)
    for lo, p, hi in zip(r.lower, r.forecast, r.upper):
        assert lo < p < hi


def test_ses_alpha_one_is_naive():
    r = fc.forecast([5, 7, 6, 9], "ses", 2, alpha=1.0)
    assert r.forecast == pytest.approx([9, 9])


def test_cagr():
    r = fc.forecast([100, 110, 121], "cagr", 2)
    assert r.params["growth_rate"] == pytest.approx(0.10)
    assert r.forecast == pytest.approx([133.1, 146.41])


def test_moving_average():
    r = fc.forecast([1, 2, 3, 4, 5, 6], "moving_average", 2, window=3)
    assert r.forecast == pytest.approx([5, 5])


def test_backtest_does_not_use_holdout():
    series = [10, 10, 10, 10, 10, 10, 100, 100]
    r = fc.forecast(series, "moving_average", 1, window=3, holdout=2)
    # trained on the six 10s, predicts 10 for the two 100s
    assert r.backtest["mae"] == pytest.approx(90)


def test_missing_values_raise():
    with pytest.raises(FinanceInputError):
        fc.forecast([1, None, 3, 4], "linear", 2)


def test_mape_undefined_with_zero_actuals():
    assert fc.error_metrics([0, 1], [1, 1])["mape"] is None
