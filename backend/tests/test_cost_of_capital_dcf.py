import pytest

from app.finance import FinanceInputError
from app.finance.cost_of_capital import capm, wacc
from app.finance.dcf import DCFInputs, run_dcf
from app.finance import sensitivity as sens


def test_capm():
    assert capm(0.04, 1.2, 0.10) == pytest.approx(0.112)


def test_wacc_known_answer():
    r = wacc(600, 400, 0.112, 0.06, 0.25)
    assert r.weight_equity == pytest.approx(0.6)
    assert r.after_tax_cost_of_debt == pytest.approx(0.045)
    assert r.wacc == pytest.approx(0.0852)


@pytest.mark.parametrize("args", [(0, 0, 0.1, 0.05, 0.2), (-1, 10, 0.1, 0.05, 0.2), (10, 10, 0.1, 0.05, 25)])
def test_wacc_invalid(args):
    with pytest.raises(FinanceInputError):
        wacc(*args)


def simple(**kw):
    base = dict(base_revenue=100, revenue_growth=[0.10], ebit_margin=[0.20], tax_rate=0.25,
                da_pct_revenue=0, capex_pct_revenue=0, nwc_pct_revenue=0, wacc=0.10, terminal_growth=0.0)
    base.update(kw)
    return DCFInputs(**base)


def test_dcf_hand_calculated():
    r = run_dcf(simple())
    y = r.years[0]
    assert y.revenue == pytest.approx(110)
    assert y.ebit == pytest.approx(22)
    assert y.nopat == pytest.approx(16.5)
    assert y.fcff == pytest.approx(16.5)
    assert y.pv_fcff == pytest.approx(15)
    assert r.terminal_value == pytest.approx(165)
    assert r.pv_terminal_value == pytest.approx(150)
    assert r.enterprise_value == pytest.approx(165)


def test_dcf_fcff_formula_with_all_drivers():
    r = run_dcf(simple(da_pct_revenue=0.05, capex_pct_revenue=0.08, nwc_pct_revenue=0.10,
                       debt=50, cash=20, shares_outstanding=10))
    y = r.years[0]
    # FCFF = EBIT(1-T) + D&A - CapEx - dNWC = 16.5 + 5.5 - 8.8 - (11 - 10)
    assert y.delta_nwc == pytest.approx(1.0)
    assert y.fcff == pytest.approx(16.5 + 5.5 - 8.8 - 1.0)
    assert r.net_debt == pytest.approx(30)
    assert r.equity_value == pytest.approx(r.enterprise_value - 30)
    assert r.value_per_share == pytest.approx(r.equity_value / 10)


def test_dcf_multi_year_discounting_and_gordon():
    r = run_dcf(simple(revenue_growth=[0.1, 0.1, 0.1], terminal_growth=0.02))
    for y in r.years:
        assert y.discount_factor == pytest.approx(1 / 1.1 ** y.year)
    last = r.years[-1]
    assert r.terminal_value == pytest.approx(last.fcff * 1.02 / 0.08)
    assert r.pv_terminal_value == pytest.approx(r.terminal_value / 1.1 ** 3)


def test_dcf_mid_year():
    r = run_dcf(simple(mid_year=True))
    assert r.years[0].discount_period == 0.5


def test_gordon_requires_wacc_above_growth():
    with pytest.raises(FinanceInputError, match="must be greater than terminal growth"):
        run_dcf(simple(wacc=0.03, terminal_growth=0.03))


def test_exit_multiple_and_implied_growth_round_trip():
    r = run_dcf(simple(terminal_method="exit_multiple", exit_multiple=8, revenue_growth=[0.1, 0.05]))
    last = r.years[-1]
    assert r.terminal_value == pytest.approx(last.ebitda * 8)
    g = r.implied_terminal_growth
    assert last.fcff * (1 + g) / (0.10 - g) == pytest.approx(r.terminal_value)


def test_exit_multiple_required():
    with pytest.raises(FinanceInputError):
        run_dcf(simple(terminal_method="exit_multiple", exit_multiple=None))


def test_margin_list_length_validation():
    with pytest.raises(FinanceInputError):
        run_dcf(simple(revenue_growth=[0.1, 0.1, 0.1], ebit_margin=[0.2, 0.2]))


def test_sensitivity_cells_equal_full_model_runs():
    base = simple(revenue_growth=[0.08] * 5, terminal_growth=0.02)
    xs, ys = [0.08, 0.10, 0.12], [0.01, 0.02, 0.03]
    grid = sens.two_way(base, "wacc", xs, "terminal_growth", ys, "enterprise_value")
    for i, g in enumerate(ys):
        for j, w in enumerate(xs):
            expected = run_dcf(simple(revenue_growth=[0.08] * 5, wacc=w, terminal_growth=g)).enterprise_value
            assert grid[i][j].value == pytest.approx(expected)


def test_sensitivity_invalid_combinations_flagged_not_fabricated():
    base = simple(terminal_growth=0.02)
    grid = sens.two_way(base, "wacc", [0.02, 0.10], "terminal_growth", [0.03], "enterprise_value")
    assert grid[0][0].value is None and "terminal growth" in grid[0][0].error
    assert grid[0][1].value is not None


def test_tornado_sorted_by_swing():
    base = simple(revenue_growth=[0.08] * 5, terminal_growth=0.02)
    base_out, bars = sens.tornado(base, {"wacc": (0.09, 0.11), "tax_rate": (0.24, 0.26)}, "enterprise_value")
    assert bars[0].variable == "wacc"
    assert bars[0].swing >= bars[1].swing
    assert base_out == pytest.approx(run_dcf(base).enterprise_value)


def test_scenario_shifts():
    base = simple(revenue_growth=[0.05, 0.05], ebit_margin=[0.2])
    s = sens.apply_scenario(base, sens.ScenarioDef("Up", revenue_growth_shift=0.02, ebit_margin_shift=0.01, overrides={"wacc": 0.09}))
    assert s.revenue_growth == pytest.approx([0.07, 0.07])
    assert s.ebit_margin == pytest.approx([0.21])
    assert s.wacc == 0.09


def test_break_even_wacc_for_target_ev():
    base = simple(revenue_growth=[0.05] * 3, terminal_growth=0.02)
    target = run_dcf(simple(revenue_growth=[0.05] * 3, terminal_growth=0.02, wacc=0.12)).enterprise_value
    be = sens.break_even(base, "wacc", "enterprise_value", target, 0.05, 0.20)
    assert be == pytest.approx(0.12, abs=1e-6)
