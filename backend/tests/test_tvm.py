import math

import pytest

from app.finance import FinanceInputError
from app.finance import tvm


def test_npv_known_answer_cf0_undiscounted():
    # -1000 + 500/1.1 + 500/1.1^2 + 500/1.1^3
    assert tvm.npv(0.10, [-1000, 500, 500, 500]) == pytest.approx(243.42599549, abs=1e-8)


def test_npv_zero_rate_is_simple_sum():
    assert tvm.npv(0, [-100, 30, 40, 50]) == pytest.approx(20)


def test_npv_rejects_nan_and_rate_below_minus_100pct():
    with pytest.raises(FinanceInputError):
        tvm.npv(0.1, [-100, float("nan")])
    with pytest.raises(FinanceInputError):
        tvm.npv(-1.0, [-100, 50])


def test_irr_matches_excel_documentation_example():
    # Excel IRR docs: -70000, 12000, 15000, 18000, 21000, 26000 -> 8.66%
    r = tvm.irr([-70000, 12000, 15000, 18000, 21000, 26000])
    assert r.status == "unique"
    assert r.value == pytest.approx(0.0866309480, abs=1e-9)
    assert tvm.npv(r.value, [-70000, 12000, 15000, 18000, 21000, 26000]) == pytest.approx(0, abs=1e-6)


def test_irr_negative_rate():
    r = tvm.irr([-100, 40, 40])
    assert r.status == "unique" and r.value < 0


def test_irr_multiple_roots():
    r = tvm.irr([-100, 230, -132])
    assert r.status == "multiple"
    assert r.irrs == pytest.approx([0.10, 0.20], abs=1e-9)
    assert r.value is None


def test_irr_none_when_all_same_sign():
    assert tvm.irr([100, 50, 20]).status == "none"


def test_irr_none_when_npv_never_zero():
    r = tvm.irr([-100, 50, -100])
    assert r.sign_changes == 2 and r.status == "none"


def test_mirr_matches_excel_documentation_example():
    flows = [-120000, 39000, 30000, 21000, 37000, 46000]
    # Independent calculation of the definition
    fv = sum(cf * 1.12 ** (5 - t) for t, cf in enumerate(flows) if cf > 0)
    expected = (fv / 120000) ** (1 / 5) - 1
    assert tvm.mirr(flows, 0.10, 0.12) == pytest.approx(expected, abs=1e-12)
    assert tvm.mirr(flows, 0.10, 0.12) == pytest.approx(0.126094, abs=1e-6)


def test_mirr_requires_mixed_signs():
    with pytest.raises(FinanceInputError):
        tvm.mirr([100, 100], 0.1, 0.1)


def test_payback_interpolates():
    assert tvm.payback_period([-1000, 400, 400, 400]).period == pytest.approx(2.5)


def test_payback_never_recovered():
    r = tvm.payback_period([-1000, 100, 100])
    assert r.period is None


def test_payback_warns_when_cumulative_turns_negative_again():
    r = tvm.payback_period([-100, 150, -200, 10])
    assert r.period == pytest.approx(100 / 150)
    assert "negative again" in r.message


def test_discounted_payback_longer_than_simple():
    flows = [-1000, 400, 400, 400]
    d = tvm.discounted_payback_period(0.10, flows).period
    # cumulative discounted: -636.36, -305.79, -5.26, ... never reaches 0 within 3 years
    assert d is None
    d2 = tvm.discounted_payback_period(0.10, flows + [400]).period
    assert 3 < d2 < 4


def test_profitability_index():
    assert tvm.profitability_index(0.10, [-1000, 500, 500, 500]) == pytest.approx(1.24342599549)


def test_profitability_index_needs_outflow():
    with pytest.raises(FinanceInputError):
        tvm.profitability_index(0.1, [100, 50])


def test_eaa_reproduces_npv_as_annuity():
    flows = [-1000, 500, 500, 500]
    eaa = tvm.equivalent_annual_annuity(0.10, flows)
    # PV of an annuity of `eaa` for 3 years must equal NPV
    assert tvm.npv(0.10, [0, eaa, eaa, eaa]) == pytest.approx(tvm.npv(0.10, flows))


def test_eaa_zero_rate():
    assert tvm.equivalent_annual_annuity(0, [-90, 50, 50, 50]) == pytest.approx(20)
