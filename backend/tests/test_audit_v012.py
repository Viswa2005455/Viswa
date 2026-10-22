"""v0.12 audit fixes: edge cases checked against independently hand-calculated answers."""

from decimal import Decimal

import pytest

from app.finance import FinanceInputError
from app.finance.accounting import TempDiff, bond_schedule, deferred_tax, depreciation_schedule, lease_schedule
from app.finance.budgeting import phase
from app.finance.costing import LFProduct, ProductCVP, cvp, limiting_factor
from app.finance.forensic import analyse
from app.finance.investments import binomial, performance


def balanced(je):
    return sum(l["debit"] or 0 for l in je["lines"]) == pytest.approx(sum(l["credit"] or 0 for l in je["lines"]), abs=1e-9)


def test_deferred_tax_net_benefit_entry_balances():
    # Current tax 1,000; a deductible difference of 18,000 at 30% creates a DTA of 5,400 (opening nil).
    # Tax expense = 1,000 - 5,400 = -4,400 (a benefit): Dr DTA 5,400 / Cr benefit 4,400 / Cr payable 1,000.
    r = deferred_tax([TempDiff("Provision", "liability", 18_000, 0)], 0.30, current_tax=1000)
    assert r["income_tax_expense"] == pytest.approx(-4400)
    je = r["journal_entries"][0]
    lines = {l["account"]: (l["debit"], l["credit"]) for l in je["lines"]}
    assert lines["Income tax benefit"] == (None, 4400)
    assert lines["Deferred tax liability (net)"] == (5400, None)
    assert lines["Income taxes payable"] == (None, 1000)
    assert balanced(je)


def test_deferred_tax_negative_current_tax_is_receivable():
    je = deferred_tax([TempDiff("PPE", "asset", 1000, 800)], 0.25, current_tax=-300)["journal_entries"][0]
    assert balanced(je) and any(l["account"] == "Income tax receivable" for l in je["lines"])


def test_every_bond_journal_entry_balances_to_the_cent():
    r = bond_schedule(1000, 0.0743, 0.068, 10, 12)
    for je in r["journal_entries"]:
        assert balanced(je), je


def test_lease_rejects_fractional_periods_and_negative_rou():
    with pytest.raises(FinanceInputError):
        lease_schedule(100, 2.5, 0.08)
    with pytest.raises(FinanceInputError):
        lease_schedule(100, 3, 0.08, incentives=1000)


def test_depreciation_rejects_fractional_life_and_bad_factor():
    with pytest.raises(FinanceInputError):
        depreciation_schedule(1000, 0, 2.5)
    with pytest.raises(FinanceInputError):
        depreciation_schedule(1000, 0, 5, "ddb", ddb_factor=0)


def test_phasing_remainder_never_lands_in_zero_weight_month():
    # 100 / 11 = 9.09 x 11 = 99.99; the 0.01 goes to month 11 (last month with the largest weight), month 12 stays 0.
    m = phase(Decimal("100"), [1] * 11 + [0])
    assert m[11] == 0 and m[10] == Decimal("9.10") and sum(m) == Decimal("100.00")


@pytest.mark.parametrize("returns, expected", [([-0.10, 0.05, 0.05], -0.10), ([-0.05, -0.10, 0.20], -0.145)])
def test_max_drawdown_counts_first_period_loss(returns, expected):
    # Wealth 1.00 -> 0.95 -> 0.855 is a 14.5% fall from the starting value.
    assert performance(returns, [0.01, 0.01, 0.02], 0.0)["max_drawdown"] == pytest.approx(expected)


def test_m_squared_is_return_at_benchmark_risk():
    r = performance([0.02, -0.01, 0.03, 0.01], [0.01, 0.0, 0.02, 0.01], 0.02, 12)
    assert r["m_squared"] == pytest.approx(0.02 + r["sharpe"] * r["benchmark_volatility"])
    assert r["m_squared_excess"] == pytest.approx(r["m_squared"] - r["benchmark_return"])


def test_binomial_rejects_unknown_kind():
    with pytest.raises(FinanceInputError):
        binomial(100, 100, 1, 0.05, 0.2, kind="cal")


def test_limiting_factor_ignores_loss_makers_when_judging_binding():
    plan = limiting_factor([LFProduct("A", 10, 2, 100), LFProduct("Loss", -5, 1, 10_000)], 250)
    assert plan["resource_needed_for_full_demand"] == 200 and plan["is_binding"] is False


def test_cvp_rejects_negative_mix_and_units():
    with pytest.raises(FinanceInputError):
        cvp([ProductCVP("A", 10, 6, 2), ProductCVP("B", 10, 6, -1)], 100)
    with pytest.raises(FinanceInputError):
        cvp([ProductCVP("A", 10, 6, 1)], 100, expected_units=-5)


def test_forensic_flags_equity_turning_negative_and_skips_gmi_on_negative_margin():
    items = {"revenue": [1000, 1000], "cogs": [1100, 1200], "total_equity": [100, -50], "total_debt": [200, 300],
             "total_assets": [1000, 1000]}
    r = analyse(["FY24", "FY25"], items)
    assert any(f.title == "Equity turned zero or negative" for f in r.flags)
    gmi = next(c for c in r.beneish.components if c.key == "GMI")
    assert gmi.value is None  # -10% / -20% = 0.5 would wrongly read as "margins improving"


def test_sensitivity_grid_refuses_assumption_the_terminal_method_ignores():
    from app.finance.dcf import DCFInputs
    from app.finance.sensitivity import two_way
    base = DCFInputs(base_revenue=1000, revenue_growth=[0.05] * 5, ebit_margin=[0.2], tax_rate=0.25, da_pct_revenue=0.03,
                     capex_pct_revenue=0.04, nwc_pct_revenue=0.1, wacc=0.10, terminal_growth=0.03, shares_outstanding=100)
    with pytest.raises(FinanceInputError):
        two_way(base, "wacc", [0.09, 0.1], "exit_multiple", [8, 10], "enterprise_value")
