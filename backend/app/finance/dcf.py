"""Driver-based unlevered DCF (FCFF) valuation.

FCFF_t = EBIT_t x (1 - T) + D&A_t - CapEx_t - dNWC_t
TV (Gordon) = FCFF_n x (1 + g) / (WACC - g)
TV (exit multiple) = EBITDA_n x multiple
EV = sum PV(FCFF_t) + PV(TV); Equity = EV - debt + cash

Timing: end-of-period discounting by default (t = 1..n). With mid_year=True, forecast
flows are discounted at t - 0.5; the terminal value is still discounted at t = n.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field, replace
from typing import Literal

from . import FinanceInputError


@dataclass
class DCFInputs:
    base_revenue: float
    revenue_growth: list[float]
    ebit_margin: list[float]
    tax_rate: float
    da_pct_revenue: float
    capex_pct_revenue: float
    nwc_pct_revenue: float
    wacc: float
    terminal_growth: float = 0.02
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    exit_multiple: float | None = None
    debt: float = 0.0
    cash: float = 0.0
    shares_outstanding: float | None = None
    mid_year: bool = False


@dataclass
class DCFYear:
    year: int
    revenue: float
    revenue_growth: float
    ebit: float
    ebit_margin: float
    taxes: float
    nopat: float
    da: float
    ebitda: float
    capex: float
    delta_nwc: float
    fcff: float
    discount_period: float
    discount_factor: float
    pv_fcff: float


@dataclass
class DCFResult:
    years: list[DCFYear]
    sum_pv_fcff: float
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    net_debt: float
    equity_value: float
    value_per_share: float | None
    terminal_value_share_of_ev: float
    implied_exit_multiple: float | None
    implied_terminal_growth: float | None
    warnings: list[str] = field(default_factory=list)


def _expand(values: list[float], n: int, name: str) -> list[float]:
    if len(values) == 1:
        return values * n
    if len(values) != n:
        raise FinanceInputError(f"{name} must have one value or exactly {n} values (one per forecast year).")
    return list(values)


def validate(inp: DCFInputs) -> None:
    n = len(inp.revenue_growth)
    if n < 1 or n > 30:
        raise FinanceInputError("Forecast period must be between 1 and 30 years.")
    if not math.isfinite(inp.base_revenue) or inp.base_revenue <= 0:
        raise FinanceInputError("Base-year revenue must be a positive number.")
    for name, values in (("Revenue growth", inp.revenue_growth), ("EBIT margin", inp.ebit_margin)):
        if any(v is None or not math.isfinite(v) for v in values):
            raise FinanceInputError(f"{name}: every year needs a number (blanks are not treated as zero).")
    if any(g <= -1 for g in inp.revenue_growth):
        raise FinanceInputError("Revenue growth must be above -100% in every year.")
    if any(m > 1 for m in inp.ebit_margin):
        raise FinanceInputError("EBIT margin cannot exceed 100% of revenue (enter 0.20 for 20%).")
    if not 0 <= inp.tax_rate < 1:
        raise FinanceInputError("Tax rate must be a decimal between 0 and 1 (e.g. 0.25 for 25%).")
    if inp.wacc <= -1:
        raise FinanceInputError("WACC must be greater than -100%.")
    if inp.terminal_method == "gordon" and inp.wacc <= inp.terminal_growth:
        raise FinanceInputError(
            f"WACC ({inp.wacc:.2%}) must be greater than terminal growth ({inp.terminal_growth:.2%}) "
            "for the Gordon Growth Method; otherwise the terminal value is infinite or negative.")
    if inp.terminal_method == "exit_multiple" and (inp.exit_multiple is None or inp.exit_multiple <= 0):
        raise FinanceInputError("An exit multiple greater than zero is required for the exit-multiple method.")
    if inp.shares_outstanding is not None and inp.shares_outstanding <= 0:
        raise FinanceInputError("Shares outstanding must be positive when provided.")


def run_dcf(inp: DCFInputs) -> DCFResult:
    validate(inp)
    n = len(inp.revenue_growth)
    margins = _expand(inp.ebit_margin, n, "EBIT margin")
    warnings: list[str] = []

    years: list[DCFYear] = []
    prev_rev = inp.base_revenue
    prev_nwc = inp.nwc_pct_revenue * inp.base_revenue
    for i in range(n):
        g = inp.revenue_growth[i]
        rev = prev_rev * (1 + g)
        ebit = rev * margins[i]
        # Taxes are only applied to positive EBIT; operating losses are not given a tax refund.
        taxes = max(ebit, 0.0) * inp.tax_rate
        nopat = ebit - taxes
        da = rev * inp.da_pct_revenue
        capex = rev * inp.capex_pct_revenue
        nwc = rev * inp.nwc_pct_revenue
        d_nwc = nwc - prev_nwc
        fcff = nopat + da - capex - d_nwc
        t = (i + 1) - (0.5 if inp.mid_year else 0.0)
        df = 1 / (1 + inp.wacc) ** t
        years.append(DCFYear(i + 1, rev, g, ebit, margins[i], taxes, nopat, da, ebit + da,
                             capex, d_nwc, fcff, t, df, fcff * df))
        prev_rev, prev_nwc = rev, nwc

    last = years[-1]
    df_n = 1 / (1 + inp.wacc) ** n
    if inp.terminal_method == "gordon":
        tv = last.fcff * (1 + inp.terminal_growth) / (inp.wacc - inp.terminal_growth)
        implied_multiple = tv / last.ebitda if last.ebitda > 0 else None
        implied_g = None
        if inp.terminal_growth > 0.04:
            warnings.append("Terminal growth above ~4% may exceed long-run nominal economic growth.")
    else:
        tv = last.ebitda * float(inp.exit_multiple)
        implied_multiple = None
        # Solve TV = FCFF(1+g)/(WACC-g) for g
        implied_g = (tv * inp.wacc - last.fcff) / (tv + last.fcff) if (tv + last.fcff) != 0 else None

    if last.fcff < 0:
        warnings.append("Final-year FCFF is negative; a terminal value based on it is not meaningful.")
    if inp.mid_year:
        warnings.append("Mid-year convention: yearly cash flows are discounted at t − 0.5, the terminal value at the end of year n "
                        "(a conservative choice; some practitioners discount a Gordon terminal value at n − 0.5).")
    if inp.capex_pct_revenue < inp.da_pct_revenue and inp.terminal_method == "gordon" and inp.terminal_growth > 0:
        warnings.append("CapEx is below D&A while assuming perpetual growth; reinvestment may be understated.")

    pv_tv = tv * df_n
    sum_pv = sum(y.pv_fcff for y in years)
    ev = sum_pv + pv_tv
    net_debt = inp.debt - inp.cash
    equity = ev - net_debt
    per_share = equity / inp.shares_outstanding if inp.shares_outstanding else None
    if equity < 0:
        warnings.append("Net debt exceeds enterprise value, so implied equity value is negative.")
    tv_share = pv_tv / ev if ev != 0 else float("nan")
    if ev > 0 and tv_share > 0.75:
        warnings.append(f"Terminal value is {tv_share:.0%} of enterprise value; the valuation is highly "
                        "sensitive to terminal assumptions.")

    return DCFResult(years, sum_pv, tv, pv_tv, ev, net_debt, equity, per_share, tv_share,
                     implied_multiple, implied_g, warnings)


# ---- variable access used by scenario & sensitivity analysis ----

SENSITIVITY_VARIABLES = {
    "wacc": "WACC",
    "terminal_growth": "Terminal growth",
    "revenue_growth": "Revenue growth (average of all years)",
    "ebit_margin": "EBIT margin (average of all years)",
    "tax_rate": "Tax rate",
    "capex_pct_revenue": "CapEx % of revenue",
    "da_pct_revenue": "D&A % of revenue",
    "nwc_pct_revenue": "NWC % of revenue",
    "exit_multiple": "Exit multiple",
}


def get_variable(inp: DCFInputs, name: str) -> float:
    if name not in SENSITIVITY_VARIABLES:
        raise FinanceInputError(f"Unknown variable '{name}'.")
    value = getattr(inp, name)
    if isinstance(value, list):
        return sum(value) / len(value)
    if value is None:
        raise FinanceInputError(f"'{name}' has no base value.")
    return float(value)


def set_variable(inp: DCFInputs, name: str, value: float) -> DCFInputs:
    """Set one assumption. For year-by-year assumptions (growth, margin) every year is shifted by the
    same amount so their average equals `value`; the year profile is kept, and the base average
    reproduces the base case exactly."""
    if name not in SENSITIVITY_VARIABLES:
        raise FinanceInputError(f"Unknown variable '{name}'.")
    if name in ("revenue_growth", "ebit_margin"):
        years = len(inp.revenue_growth)
        current = list(getattr(inp, name))
        current = current * years if len(current) == 1 else current
        shift = value - sum(current) / len(current)
        return replace(inp, **{name: [v + shift for v in current]})
    return replace(inp, **{name: value})


def check_variable(inp: DCFInputs, name: str) -> None:
    """Refuse assumptions the chosen terminal method ignores (varying them would show a flat, misleading result)."""
    if name not in SENSITIVITY_VARIABLES:
        raise FinanceInputError(f"Unknown variable '{name}'.")
    if name == "exit_multiple" and inp.terminal_method != "exit_multiple":
        raise FinanceInputError("Exit multiple has no effect with the Gordon growth terminal method.")
    if name == "terminal_growth" and inp.terminal_method != "gordon":
        raise FinanceInputError("Terminal growth has no effect with the exit-multiple terminal method.")


OUTPUTS = {
    "enterprise_value": lambda r: r.enterprise_value,
    "equity_value": lambda r: r.equity_value,
    "value_per_share": lambda r: r.value_per_share,
    "final_year_fcff": lambda r: r.years[-1].fcff,
    "final_year_ebitda": lambda r: r.years[-1].ebitda,
}
