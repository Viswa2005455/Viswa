"""Budget-versus-actual variance analysis.

Arithmetic uses Decimal so that budget totals and variances add up exactly to the cent.

Policies
--------
* Absolute variance = Actual - Budget (always).
* Percentage variance = (Actual - Budget) / |Budget| x 100.
  - Budget = 0  -> percentage is None ("not meaningful"); the absolute variance is still shown.
  - Budget < 0  -> |Budget| keeps the sign of the percentage aligned with the absolute
    variance, and a note warns that the percentage needs care.
* Favourable / adverse depends on the line type: higher revenue is favourable, higher
  expense is adverse. Zero difference is "on budget".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from . import FinanceInputError

LineKind = Literal["revenue", "expense"]


def D(x: float | int | str | Decimal) -> Decimal:
    # str() avoids binary-float artefacts such as Decimal(0.1) = 0.1000000000000000055...
    d = x if isinstance(x, Decimal) else Decimal(str(x))
    if not d.is_finite():
        raise FinanceInputError("Amounts must be finite numbers.")
    return d


@dataclass
class VarianceLine:
    name: str
    kind: LineKind
    budget: Decimal
    actual: Decimal
    variance: Decimal
    variance_pct: Decimal | None
    status: Literal["favourable", "adverse", "on_budget"]
    profit_impact: Decimal  # effect of this variance on profit (+ helps profit)
    material: bool
    notes: list[str] = field(default_factory=list)
    group: str | None = None


def percentage_variance(budget: Decimal, actual: Decimal) -> tuple[Decimal | None, list[str]]:
    if budget == 0:
        return None, ["Budget is zero, so a percentage variance is not meaningful."]
    notes = []
    if budget < 0:
        notes.append("Budget is negative; the percentage is measured against |budget| and needs care.")
    return (actual - budget) / abs(budget) * 100, notes


def classify(kind: LineKind, variance: Decimal) -> str:
    if variance == 0:
        return "on_budget"
    if kind == "revenue":
        return "favourable" if variance > 0 else "adverse"
    return "favourable" if variance < 0 else "adverse"


def analyse_line(name: str, kind: LineKind, budget, actual, *, materiality_pct: float | None = 10,
                 materiality_abs: float | None = None, group: str | None = None) -> VarianceLine:
    if kind not in ("revenue", "expense"):
        raise FinanceInputError(f"Line '{name}': kind must be 'revenue' or 'expense'.")
    if budget is None or actual is None:
        raise FinanceInputError(f"Line '{name}': budget and actual are both required (missing values are not assumed to be zero).")
    b, a = D(budget), D(actual)
    var = a - b
    pct, notes = percentage_variance(b, a)
    impact = var if kind == "revenue" else -var
    material = False
    if materiality_pct is not None and pct is not None and abs(pct) >= D(materiality_pct):
        material = True
    if materiality_pct is not None and pct is None and var != 0:
        material = True  # an unbudgeted amount is an unlimited percentage variance
        notes.append("Not in the budget (budget is zero), so it is treated as material.")
    if materiality_abs is not None and abs(var) >= D(materiality_abs):
        material = True
    return VarianceLine(name, kind, b, a, var, pct, classify(kind, var), impact, material, notes, group)


@dataclass
class VarianceReport:
    lines: list[VarianceLine]
    totals: dict[str, VarianceLine]
    largest_contributors: list[VarianceLine]


def analyse(lines: list[dict], materiality_pct: float | None = 10, materiality_abs: float | None = None) -> VarianceReport:
    if not lines:
        raise FinanceInputError("Provide at least one budget line.")
    out = [analyse_line(l["name"], l["kind"], l.get("budget"), l.get("actual"),
                        materiality_pct=materiality_pct, materiality_abs=materiality_abs, group=l.get("group"))
           for l in lines]
    totals: dict[str, VarianceLine] = {}
    rev = [l for l in out if l.kind == "revenue"]
    exp = [l for l in out if l.kind == "expense"]
    if rev:
        totals["revenue"] = analyse_line("Total revenue", "revenue", sum(l.budget for l in rev), sum(l.actual for l in rev),
                                         materiality_pct=materiality_pct, materiality_abs=materiality_abs)
    if exp:
        totals["expense"] = analyse_line("Total expenses", "expense", sum(l.budget for l in exp), sum(l.actual for l in exp),
                                         materiality_pct=materiality_pct, materiality_abs=materiality_abs)
    if rev and exp:
        b = totals["revenue"].budget - totals["expense"].budget
        a = totals["revenue"].actual - totals["expense"].actual
        # Profit behaves like revenue: higher is favourable.
        totals["profit"] = analyse_line("Net result (revenue - expenses)", "revenue", b, a,
                                        materiality_pct=materiality_pct, materiality_abs=materiality_abs)
    largest = sorted((l for l in out if l.variance != 0), key=lambda l: abs(l.profit_impact), reverse=True)[:5]
    return VarianceReport(out, totals, largest)


@dataclass
class PriceVolumeResult:
    budget_revenue: Decimal
    actual_revenue: Decimal
    total_variance: Decimal
    price_variance: Decimal
    volume_variance: Decimal


def sales_price_volume(budget_price, budget_qty, actual_price, actual_qty) -> PriceVolumeResult:
    """Price variance = (AP - BP) x AQ ; Volume variance = (AQ - BQ) x BP. They sum to the total."""
    bp, bq, ap, aq = map(D, (budget_price, budget_qty, actual_price, actual_qty))
    price = (ap - bp) * aq
    volume = (aq - bq) * bp
    return PriceVolumeResult(bp * bq, ap * aq, ap * aq - bp * bq, price, volume)


@dataclass
class FlexibleBudgetResult:
    static_budget: Decimal
    flexed_budget: Decimal
    actual: Decimal
    flexible_budget_variance: Decimal  # actual - flexed (spending/efficiency)
    activity_variance: Decimal  # flexed - static (due to volume)
    total_variance: Decimal


def flexible_budget_cost(fixed_cost, variable_cost_per_unit, budget_units, actual_units, actual_cost) -> FlexibleBudgetResult:
    f, v, bu, au, ac = map(D, (fixed_cost, variable_cost_per_unit, budget_units, actual_units, actual_cost))
    static = f + v * bu
    flexed = f + v * au
    return FlexibleBudgetResult(static, flexed, ac, ac - flexed, flexed - static, ac - static)
