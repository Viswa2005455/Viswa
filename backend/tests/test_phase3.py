from decimal import Decimal

import pytest

from app.finance import FinanceInputError
from app.finance import budgeting as bud
from app.finance import cashflow as cf
from app.finance import statements as st


# ---------------------------------------------------------------- statements

def L(label, statement, values, key=None):
    return st.StatementLine(label, statement, values, key)


def sample():
    periods = ["FY2023", "FY2024", "FY2025"]
    lines = [
        L("Revenue", "income", [1000, 1200, 1500], "revenue"),
        L("COGS", "income", [600, 700, 900], "cogs"),
        L("Gross profit", "income", [400, 500, 600], "gross_profit"),
        L("D&A", "income", [50, 60, 70], "depreciation_amortization"),
        L("EBIT", "income", [150, 200, 240], "operating_income"),
        L("PBT", "income", [130, 185, 230], "pretax_income"),
        L("Tax", "income", [30, 45, 55], "income_tax"),
        L("Net income", "income", [100, 140, 175], "net_income"),
        L("Cash", "balance", [80, 100, 120], "cash"),
        L("Receivables", "balance", [150, 180, 300], "receivables"),
        L("Inventory", "balance", [100, 120, 150], "inventory"),
        L("Current assets", "balance", [350, 420, 590], "current_assets"),
        L("Total assets", "balance", [1000, 1100, 1300], "total_assets"),
        L("Current liabilities", "balance", [200, 230, 260], "current_liabilities"),
        L("Total liabilities", "balance", [500, 520, 600], "total_liabilities"),
        L("Equity", "balance", [500, 580, 700], "total_equity"),
        L("CFO", "cashflow", [90, 120, 110], "operating_cash_flow"),
        L("CapEx", "cashflow", [-40, -50, -60], "capex"),
        L("CFI", "cashflow", [-40, -50, -60], "investing_cash_flow"),
        L("CFF", "cashflow", [-30, -50, -30], "financing_cash_flow"),
        L("Net change", "cashflow", [20, 20, 20], "net_change_in_cash"),
        L("Opening cash", "cashflow", [60, 80, 100], "beginning_cash"),
        L("Closing cash", "cashflow", [80, 100, 120], "ending_cash"),
    ]
    return periods, lines


def test_horizontal_and_vertical():
    r = st.analyse(*sample())
    rev = r.lines[0]
    assert rev.changes[0] is None
    assert rev.changes[1].absolute == 200 and rev.changes[1].pct == pytest.approx(20)
    assert rev.changes[2].pct == pytest.approx(25)
    assert rev.cagr == pytest.approx((1500 / 1000) ** 0.5 - 1)
    cogs = r.lines[1]
    assert cogs.common_size == pytest.approx([60, 700 / 1200 * 100, 60])
    cash = next(l for l in r.lines if l.key == "cash")
    assert cash.common_size[0] == pytest.approx(8)  # % of total assets


def test_metrics():
    r = st.analyse(*sample())
    assert r.metrics["free_cash_flow"] == [50, 70, 50]  # OCF − |CapEx|, capex entered negative
    assert r.metrics["net_working_capital"] == [150, 190, 330]
    assert r.metrics["change_in_nwc"] == [None, 40, 140]
    assert r.metrics["ebitda"] == [200, 260, 310]
    assert r.metrics["gross_margin_pct"][0] == pytest.approx(40)
    assert r.metrics["cash_conversion"][2] == pytest.approx(110 / 175)
    assert r.metrics["accruals_ratio_pct"][0] is None
    assert r.metrics["accruals_ratio_pct"][2] == pytest.approx((175 - 110) / 1200 * 100)


def test_all_checks_pass_on_consistent_statements():
    r = st.analyse(*sample())
    failed = [c for c in r.checks if c.status == "fail"]
    assert not failed, failed
    names = {c.name for c in r.checks}
    assert "Assets = Liabilities + Equity" in names and "Beginning cash = prior period ending cash" in names


def test_balance_sheet_imbalance_detected():
    periods, lines = sample()
    lines[14] = L("Total liabilities", "balance", [500, 520, 500], "total_liabilities")
    r = st.analyse(periods, lines)
    bad = [c for c in r.checks if c.name == "Assets = Liabilities + Equity" and c.status == "fail"]
    assert len(bad) == 1 and bad[0].period == "FY2025" and bad[0].difference == 100


def test_rounding_tolerance():
    periods, lines = sample()
    lines[12] = L("Total assets", "balance", [1000.4, 1100, 1300], "total_assets")
    r = st.analyse(periods, lines)
    assert all(c.status != "fail" for c in r.checks if c.name.startswith("Assets"))


def test_quality_flags():
    r = st.analyse(*sample())
    assert any("Receivables grew" in f for f in r.quality_flags)
    assert any("not evidence" in n for n in r.notes)


def test_missing_values_and_zero_prior():
    r = st.analyse(["A", "B", "C"], [L("Other", "income", [0, 50, None])])
    ch = r.lines[0].changes
    assert ch[1].absolute == 50 and ch[1].pct is None and "zero" in ch[1].note
    assert ch[2] is None
    assert r.lines[0].common_size == [None, None, None]  # no revenue line to base on
    assert r.lines[0].cagr is None


def test_insufficient_check_when_period_missing():
    periods, lines = sample()
    lines[15] = L("Equity", "balance", [500, None, 700], "total_equity")
    r = st.analyse(periods, lines)
    c = [c for c in r.checks if c.name.startswith("Assets") and c.period == "FY2024"][0]
    assert c.status == "insufficient"


def test_sign_change_note():
    c = st.change(-50, 30)
    assert c.pct == pytest.approx(160) and c.note


@pytest.mark.parametrize("bad", [
    (["A"], [L("x", "income", [1, 2])]),
    (["A"], [L("x", "income", [1], "nope")]),
    (["A"], [L("x", "income", [1], "revenue"), L("y", "income", [2], "revenue")]),
])
def test_statement_validation(bad):
    with pytest.raises(FinanceInputError):
        st.analyse(*bad)


# ---------------------------------------------------------------- cash flow

def test_cash_budget_with_minimum_balance():
    r = cf.cash_budget(["M1", "M2", "M3"], 100,
                       [cf.CashLine("Sales", [50, 50, 200])], [cf.CashLine("Costs", [120, 120, 60])], minimum_cash=20)
    p = r.periods
    # M1: 100 + 50 − 120 = 30 (≥ 20, no financing)
    assert p[0].closing == 30 and p[0].financing == 0
    # M2: 30 + 50 − 120 = −40 → financing 60 to reach 20
    assert p[1].financing == 60 and p[1].closing == 20
    # M3: 20 + 200 − 60 = 160
    assert p[2].closing == 160 and p[2].opening == 20
    assert r.total_financing == 60
    assert [x.closing_without_financing for x in p] == [30, -40, 100]
    assert r.first_negative_period == "M2" and r.lowest_closing_without_financing == -40


def test_cash_budget_validation():
    with pytest.raises(FinanceInputError):
        cf.cash_budget(["M1", "M2"], 0, [cf.CashLine("x", [1])], [])
    with pytest.raises(FinanceInputError):
        cf.cash_budget(["M1"], 0, [cf.CashLine("x", [-5])], [])
    with pytest.raises(FinanceInputError):
        cf.cash_budget(["M1"], 0, [cf.CashLine("x", [None])], [])


def test_runway():
    r = cf.runway(1200, [-100, -300, -200])
    assert r.average_net_burn == 200 and r.months == 6
    assert cf.runway(100, [50, -10]).months is None


def test_working_capital_cash_release():
    w = cf.working_capital(revenue=3650, cogs=1825, receivables=500, inventory=300, payables=150,
                           target_dso=40, target_dio=50, target_dpo=40)
    assert w.dso == pytest.approx(50) and w.dio == pytest.approx(60) and w.dpo == pytest.approx(30)
    assert w.ccc == pytest.approx(80) and w.target_ccc == pytest.approx(50)
    assert w.target_receivables == pytest.approx(400) and w.target_inventory == pytest.approx(250) and w.target_payables == pytest.approx(200)
    assert w.cash_released == pytest.approx(100 + 50 + 50)
    assert sum(w.breakdown.values()) == pytest.approx(w.cash_released)


def test_working_capital_rejects_zero_revenue():
    with pytest.raises(FinanceInputError):
        cf.working_capital(0, 10, 1, 1, 1, 1, 1, 1)


# ---------------------------------------------------------------- budgeting

def test_phase_even_sums_exactly():
    m = bud.phase(Decimal("1000"))
    assert len(m) == 12 and sum(m) == Decimal("1000.00")
    assert m[0] == Decimal("83.33") and m[-1] == Decimal("83.37")


def test_phase_weights():
    w = [1] * 11 + [3]
    m = bud.phase(Decimal("1400"), w)
    assert m[-1] == Decimal("300.00") and m[0] == Decimal("100.00") and sum(m) == Decimal("1400.00")


@pytest.mark.parametrize("w", [[1] * 11, [0] * 12, [1] * 11 + [-1]])
def test_phase_invalid(w):
    with pytest.raises(FinanceInputError):
        bud.phase(Decimal(100), w)


def test_month_labels_indian_fy():
    labels = bud.month_labels(4, 2026)
    assert labels[0] == "Apr-26" and labels[-1] == "Mar-27"


def test_methods():
    inc = bud.build_line(bud.BudgetLineIn("Rent", "expense", "incremental", prior_actual=1200, change_pct=5))
    assert inc.annual == Decimal("1260.00")
    drv = bud.build_line(bud.BudgetLineIn("Sales", "revenue", "driver", quantity=[10] * 12, rate=25.5))
    assert drv.annual == Decimal("3060.00") and drv.quarterly[0] == Decimal("765.00")
    mon = bud.build_line(bud.BudgetLineIn("Misc", "expense", "monthly", monthly=list(range(12))))
    assert mon.annual == Decimal("66.00")


def test_method_missing_inputs_rejected():
    with pytest.raises(FinanceInputError):
        bud.build_line(bud.BudgetLineIn("Rent", "expense", "incremental", prior_actual=1200))
    with pytest.raises(FinanceInputError):
        bud.build_line(bud.BudgetLineIn("Misc", "expense", "monthly", monthly=[1] * 11 + [None]))


def test_build_budget_rollups_and_zbb_warnings():
    r = bud.build_budget([
        bud.BudgetLineIn("Product A", "revenue", "annual", annual=12000, department="Sales", product="A"),
        bud.BudgetLineIn("Product B", "revenue", "annual", annual=6000, department="Sales", product="B"),
        bud.BudgetLineIn("Salaries", "expense", "annual", annual=9600, department="Ops"),
        bud.BudgetLineIn("Laptops", "capex", "annual", annual=2400, department="Ops", justification="Replace 6 laptops"),
    ], start_month=4, start_year=2026, zero_based=True)
    assert r.totals_annual["revenue"] == Decimal("18000.00")
    assert r.totals_annual["operating_result"] == Decimal("8400.00")
    assert r.totals_monthly["operating_result"][0] == Decimal("700.00")
    assert r.by_department["Ops"]["capex"] == Decimal("2400.00")
    assert r.by_product == {"A": Decimal("12000.00"), "B": Decimal("6000.00")}
    assert any("justification" in w for w in r.warnings)


def test_compare_versions():
    a = [("Sales", "revenue", Decimal(100)), ("Rent", "expense", Decimal(50)), ("Old", "expense", Decimal(5))]
    b = [("Sales", "revenue", Decimal(110)), ("Rent", "expense", Decimal(50)), ("New", "capex", Decimal(20))]
    d = {x.name: x for x in bud.compare_versions(a, b)}
    assert d["Sales"].change == 10 and d["Sales"].change_pct == 10 and d["Sales"].status == "changed"
    assert d["Rent"].status == "unchanged"
    assert d["Old"].status == "removed" and d["Old"].change == -5
    assert d["New"].status == "added"


def test_flexible_budget():
    lv = bud.flexible_budget(1000, 5, [0, 100, 200])
    assert [x.total for x in lv] == [1000, 1500, 2000]
    assert lv[0].cost_per_unit is None and lv[2].cost_per_unit == 10
