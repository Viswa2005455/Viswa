"""Time value of money and investment appraisal: NPV, IRR, MIRR, payback, PI, EAA."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy.optimize import brentq

from . import FinanceInputError


def _validate_flows(cash_flows: Sequence[float], min_len: int = 2) -> list[float]:
    flows = [float(c) for c in cash_flows]
    if len(flows) < min_len:
        raise FinanceInputError(f"At least {min_len} cash flows are required (t=0 plus at least one future period).")
    if any(math.isnan(c) or math.isinf(c) for c in flows):
        raise FinanceInputError("Cash flows must be finite numbers; missing values are not treated as zero.")
    return flows


def _validate_rate(rate: float, name: str = "rate") -> float:
    rate = float(rate)
    if math.isnan(rate) or math.isinf(rate):
        raise FinanceInputError(f"{name} must be a finite number.")
    if rate <= -1:
        raise FinanceInputError(f"{name} must be greater than -100%.")
    return rate


def discount_factor(rate: float, t: float) -> float:
    """1 / (1 + r)^t"""
    return 1.0 / (1.0 + rate) ** t


def npv(rate: float, cash_flows: Sequence[float]) -> float:
    """Net present value with CF0 at t=0 (undiscounted).

    NPV = sum_{t=0..n} CF_t / (1 + r)^t
    """
    rate = _validate_rate(rate)
    flows = _validate_flows(cash_flows, min_len=1)
    return sum(cf * discount_factor(rate, t) for t, cf in enumerate(flows))


def sign_changes(cash_flows: Sequence[float]) -> int:
    """Number of sign changes, ignoring zeros. By Descartes' rule this bounds the number of IRRs."""
    signs = [1 if c > 0 else -1 for c in cash_flows if c != 0]
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


@dataclass
class IRRResult:
    status: str  # "unique" | "multiple" | "none"
    irrs: list[float] = field(default_factory=list)
    sign_changes: int = 0
    message: str = ""

    @property
    def value(self) -> float | None:
        return self.irrs[0] if self.status == "unique" else None


def irr(cash_flows: Sequence[float], low: float = -0.99, high: float = 10.0) -> IRRResult:
    """Find every IRR (rate where NPV = 0) in [low, high].

    Rather than a single Newton iteration (which can silently converge to one of several
    roots or diverge), the NPV curve is scanned on a dense grid and each sign change is
    refined with Brent's method. Unconventional cash flows can have several IRRs or none.
    """
    flows = _validate_flows(cash_flows)
    changes = sign_changes(flows)
    if changes == 0:
        return IRRResult("none", [], 0, "All cash flows have the same sign, so no IRR exists.")

    def f(r: float) -> float:
        return npv(r, flows)

    # Denser grid near typical rates, coarser further out.
    grid = np.unique(np.concatenate([
        np.linspace(low, -0.5, 200, endpoint=False),
        np.linspace(-0.5, 1.0, 3001),
        np.linspace(1.0, high, 900),
    ]))
    values = [f(r) for r in grid]
    roots: list[float] = []
    for (r0, v0), (r1, v1) in zip(zip(grid, values), zip(grid[1:], values[1:])):
        if v0 == 0:
            roots.append(float(r0))
        elif v0 * v1 < 0:
            roots.append(float(brentq(f, r0, r1, xtol=1e-14, rtol=1e-12, maxiter=200)))
    if values[-1] == 0:
        roots.append(float(grid[-1]))
    # A grid only sees sign changes, so it misses a root where NPV touches zero without crossing
    # (a double root) and two roots closer together than the grid step. NPV is a polynomial in
    # x = 1/(1+r), so its real roots are also taken from the polynomial and verified.
    scale = sum(abs(c) for c in flows)
    for x in np.roots(list(reversed(flows))):
        if abs(x.imag) > 1e-3 * max(1.0, abs(x.real)) or x.real <= 0:  # a double root can come back slightly complex; NPV is checked below
            continue
        r = 1 / x.real - 1
        if low <= r <= high and abs(f(r)) <= 1e-9 * scale and all(abs(r - q) > 1e-7 for q in roots):
            roots.append(float(r))
    roots = sorted({round(r, 12) for r in roots})

    if not roots:
        return IRRResult("none", [], changes,
                         f"No rate between {low:.0%} and {high:.0%} makes NPV zero.")
    if len(roots) == 1:
        msg = "Conventional cash flows: a single IRR exists." if changes == 1 else (
            "Only one IRR was found in the searched range, but the cash flows change sign "
            f"{changes} times; interpret IRR with care and prefer NPV.")
        return IRRResult("unique", roots, changes, msg)
    return IRRResult("multiple", roots, changes,
                     f"{len(roots)} IRRs exist because cash flows change sign {changes} times. "
                     "IRR is ambiguous here; use NPV or MIRR for the decision.")


def mirr(cash_flows: Sequence[float], finance_rate: float, reinvest_rate: float) -> float:
    """Modified IRR (matches Excel MIRR).

    MIRR = (FV of positive flows at reinvest rate / -PV of negative flows at finance rate)^(1/n) - 1
    """
    flows = _validate_flows(cash_flows)
    finance_rate = _validate_rate(finance_rate, "finance_rate")
    reinvest_rate = _validate_rate(reinvest_rate, "reinvest_rate")
    n = len(flows) - 1
    pv_neg = sum(cf / (1 + finance_rate) ** t for t, cf in enumerate(flows) if cf < 0)
    fv_pos = sum(cf * (1 + reinvest_rate) ** (n - t) for t, cf in enumerate(flows) if cf > 0)
    if pv_neg == 0 or fv_pos == 0:
        raise FinanceInputError("MIRR needs at least one negative and one positive cash flow.")
    return (fv_pos / -pv_neg) ** (1 / n) - 1


@dataclass
class PaybackResult:
    period: float | None  # None = never recovered within the horizon
    cumulative: list[float]
    message: str


def _payback_from(flows: list[float]) -> PaybackResult:
    """Time until cumulative cash flow recovers after first going negative. CF0 need not be the
    outlay: [0, -100, 50, 80] pays back at 2.625."""
    cumulative: list[float] = []
    running = 0.0
    for cf in flows:
        running += cf
        cumulative.append(running)
    first_negative = next((t for t, c in enumerate(cumulative) if c < 0), None)
    if first_negative is None:
        return PaybackResult(0.0, cumulative, "Cumulative cash flow never goes negative, so payback is immediate.")
    for t in range(first_negative + 1, len(flows)):
        if cumulative[t] >= 0 > cumulative[t - 1]:
            # Linear interpolation assumes the period's cash flow arrives evenly through the period.
            fraction = -cumulative[t - 1] / flows[t]
            period = (t - 1) + fraction
            # Later negative flows can make cumulative go negative again; warn rather than hide it.
            if any(c < 0 for c in cumulative[t + 1:]):
                return PaybackResult(period, cumulative,
                                     "Cumulative cash flow turns negative again later; payback is misleading here.")
            return PaybackResult(period, cumulative, "Assumes cash flows arrive evenly within each period.")
    return PaybackResult(None, cumulative, "The investment is not recovered within the project life.")


def payback_period(cash_flows: Sequence[float]) -> PaybackResult:
    return _payback_from(_validate_flows(cash_flows))


def discounted_payback_period(rate: float, cash_flows: Sequence[float]) -> PaybackResult:
    rate = _validate_rate(rate)
    flows = _validate_flows(cash_flows)
    return _payback_from([cf * discount_factor(rate, t) for t, cf in enumerate(flows)])


def profitability_index(rate: float, cash_flows: Sequence[float]) -> float:
    """PI = PV of future cash flows (t>=1) / initial investment (|CF0|)."""
    flows = _validate_flows(cash_flows)
    if flows[0] >= 0:
        raise FinanceInputError("Profitability index requires a negative initial investment at t=0.")
    pv_future = npv(rate, [0.0] + flows[1:])
    return pv_future / -flows[0]


def equivalent_annual_annuity(rate: float, cash_flows: Sequence[float]) -> float:
    """EAA = NPV x r / (1 - (1+r)^-n). Useful to compare projects with different lives."""
    rate = _validate_rate(rate)
    flows = _validate_flows(cash_flows)
    n = len(flows) - 1
    value = npv(rate, flows)
    if rate == 0:
        return value / n
    return value * rate / (1 - (1 + rate) ** -n)
