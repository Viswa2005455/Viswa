"""Budget preparation: monthly phasing, budgeting methods, roll-ups, versions, flexible budgets.

Methods per line
* "monthly"     — twelve values entered directly.
* "annual"      — an annual amount spread by a phasing profile (even or custom weights).
* "incremental" — prior-year actual x (1 + change %), then phased (incremental budgeting).
* "driver"      — quantity per month x rate (used for zero-based budgeting: every line is built
                  up from drivers and carries a justification).

Money is handled with Decimal and rounded to 2 decimals per month; any rounding remainder is
placed in the latest month with the largest weight (the final month for even phasing), so the
months always add up exactly to the annual amount and a zero-weight month stays zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from . import FinanceInputError

Kind = Literal["revenue", "expense", "capex"]
Method = Literal["monthly", "annual", "incremental", "driver"]
CENT = Decimal("0.01")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def D(x) -> Decimal:
    d = x if isinstance(x, Decimal) else Decimal(str(x))
    if not d.is_finite():
        raise FinanceInputError("Amounts must be finite numbers.")
    return d


def month_labels(start_month: int, start_year: int) -> list[str]:
    if not 1 <= start_month <= 12:
        raise FinanceInputError("Fiscal year start month must be between 1 and 12.")
    out = []
    for i in range(12):
        m = (start_month - 1 + i) % 12
        y = start_year + (start_month - 1 + i) // 12
        out.append(f"{MONTHS[m]}-{str(y)[-2:]}")
    return out


def phase(annual: Decimal, weights: list[float] | None = None) -> list[Decimal]:
    """Spread an annual amount over 12 months; months sum exactly to `annual` (to the cent)."""
    annual = D(annual)
    if weights is None:
        w = [Decimal(1)] * 12
    else:
        if len(weights) != 12:
            raise FinanceInputError("A phasing profile needs exactly 12 weights.")
        if any(x is None or x < 0 for x in weights):
            raise FinanceInputError("Phasing weights must be zero or positive.")
        w = [D(x) for x in weights]
    total_w = sum(w)
    if total_w == 0:
        raise FinanceInputError("Phasing weights cannot all be zero.")
    months = [(annual * wi / total_w).quantize(CENT, ROUND_HALF_UP) for wi in w]
    target = max(range(12), key=lambda i: (w[i], i))
    months[target] += annual.quantize(CENT, ROUND_HALF_UP) - sum(months)
    return months


@dataclass
class BudgetLineIn:
    name: str
    kind: Kind
    method: Method
    department: str = "General"
    product: str | None = None
    monthly: list[float] | None = None
    annual: float | None = None
    prior_actual: float | None = None
    change_pct: float | None = None  # e.g. 5 for +5%
    quantity: list[float] | None = None
    rate: float | None = None
    weights: list[float] | None = None
    justification: str | None = None


@dataclass
class BudgetLineOut:
    name: str
    kind: str
    department: str
    product: str | None
    method: str
    monthly: list[Decimal]
    quarterly: list[Decimal]
    annual: Decimal
    explanation: str
    justification: str | None = None


def build_line(line: BudgetLineIn) -> BudgetLineOut:
    if not line.name.strip():
        raise FinanceInputError("Every budget line needs a name.")
    m = line.method
    if m == "monthly":
        if not line.monthly or len(line.monthly) != 12 or any(v is None for v in line.monthly):
            raise FinanceInputError(f"'{line.name}': enter all 12 monthly values (use 0 for none).")
        months = [D(v).quantize(CENT, ROUND_HALF_UP) for v in line.monthly]
        expl = "Entered month by month."
    elif m == "annual":
        if line.annual is None:
            raise FinanceInputError(f"'{line.name}': annual amount is required.")
        months = phase(D(line.annual), line.weights)
        expl = f"Annual {D(line.annual):,.2f} phased {'by custom weights' if line.weights else 'evenly'}."
    elif m == "incremental":
        if line.prior_actual is None or line.change_pct is None:
            raise FinanceInputError(f"'{line.name}': prior-year actual and % change are required for incremental budgeting.")
        annual = D(line.prior_actual) * (1 + D(line.change_pct) / 100)
        months = phase(annual, line.weights)
        expl = f"Prior year {D(line.prior_actual):,.2f} × (1 {'+' if line.change_pct >= 0 else '−'} {abs(line.change_pct)}%) = {annual:,.2f}."
    elif m == "driver":
        if not line.quantity or len(line.quantity) != 12 or any(v is None for v in line.quantity) or line.rate is None:
            raise FinanceInputError(f"'{line.name}': 12 monthly quantities and a rate are required for a driver-based line.")
        months = [(D(q) * D(line.rate)).quantize(CENT, ROUND_HALF_UP) for q in line.quantity]
        expl = f"Quantity × rate ({D(line.rate):,.2f} per unit)."
    else:
        raise FinanceInputError(f"Unknown method '{m}'.")
    quarterly = [sum(months[q * 3:(q + 1) * 3]) for q in range(4)]
    return BudgetLineOut(line.name.strip(), line.kind, line.department or "General", line.product, m, months, quarterly,
                         sum(months), expl, line.justification)


@dataclass
class BudgetResult:
    months: list[str]
    lines: list[BudgetLineOut]
    totals_monthly: dict[str, list[Decimal]]  # revenue / expense / capex / operating_result
    totals_annual: dict[str, Decimal]
    by_department: dict[str, dict[str, Decimal]]
    by_product: dict[str, Decimal]
    warnings: list[str] = field(default_factory=list)


def build_budget(lines: list[BudgetLineIn], start_month: int = 4, start_year: int = 2026, zero_based: bool = False) -> BudgetResult:
    if not lines:
        raise FinanceInputError("Add at least one budget line.")
    labels = month_labels(start_month, start_year)
    outs = [build_line(l) for l in lines]

    def total(kind: str) -> list[Decimal]:
        return [sum((o.monthly[i] for o in outs if o.kind == kind), Decimal(0)) for i in range(12)]

    rev, exp, cap = total("revenue"), total("expense"), total("capex")
    op = [r - e for r, e in zip(rev, exp)]
    by_dept: dict[str, dict[str, Decimal]] = {}
    for o in outs:
        d = by_dept.setdefault(o.department, {"revenue": Decimal(0), "expense": Decimal(0), "capex": Decimal(0)})
        d[o.kind] += o.annual
    by_prod: dict[str, Decimal] = {}
    for o in outs:
        if o.product and o.kind == "revenue":
            by_prod[o.product] = by_prod.get(o.product, Decimal(0)) + o.annual

    warnings = []
    if zero_based:
        missing = [o.name for o in outs if not (o.justification or "").strip()]
        if missing:
            warnings.append(f"Zero-based budgeting: {len(missing)} line(s) have no justification ({', '.join(missing[:5])}).")
        non_driver = [o.name for o in outs if o.method not in ("driver",) and o.kind != "revenue"]
        if non_driver:
            warnings.append("Zero-based budgeting normally builds cost lines from drivers; these are not driver-based: "
                            + ", ".join(non_driver[:5]) + ".")
    if any(r < 0 for r in rev):
        warnings.append("Some months have negative total revenue.")
    return BudgetResult(labels, outs, {"revenue": rev, "expense": exp, "capex": cap, "operating_result": op},
                        {"revenue": sum(rev), "expense": sum(exp), "capex": sum(cap), "operating_result": sum(op)},
                        by_dept, by_prod, warnings)


@dataclass
class VersionDiff:
    name: str
    kind: str
    a: Decimal | None
    b: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    status: Literal["added", "removed", "changed", "unchanged"]


def compare_versions(a: list[tuple[str, str, Decimal]], b: list[tuple[str, str, Decimal]]) -> list[VersionDiff]:
    """Compare annual totals of two budget versions, matching lines by (kind, name)."""
    ma = {(k, n): D(v) for n, k, v in a}
    mb = {(k, n): D(v) for n, k, v in b}
    out = []
    for key in list(dict.fromkeys(list(ma) + list(mb))):
        kind, name = key
        va, vb = ma.get(key), mb.get(key)
        if va is None:
            out.append(VersionDiff(name, kind, None, vb, vb, None, "added"))
        elif vb is None:
            out.append(VersionDiff(name, kind, va, None, -va, None, "removed"))
        else:
            ch = vb - va
            pct = (ch / abs(va) * 100) if va != 0 else None
            out.append(VersionDiff(name, kind, va, vb, ch, pct, "unchanged" if ch == 0 else "changed"))
    return out


@dataclass
class FlexLevel:
    activity: Decimal
    fixed: Decimal
    variable: Decimal
    total: Decimal
    cost_per_unit: Decimal | None


def flexible_budget(fixed_cost, variable_cost_per_unit, activity_levels: list[float]) -> list[FlexLevel]:
    """Cost at several activity levels: total = fixed + variable rate x activity."""
    if not activity_levels or len(activity_levels) > 20:
        raise FinanceInputError("Provide between 1 and 20 activity levels.")
    f, v = D(fixed_cost), D(variable_cost_per_unit)
    out = []
    for a in activity_levels:
        a = D(a)
        if a < 0:
            raise FinanceInputError("Activity levels cannot be negative.")
        var = v * a
        tot = f + var
        out.append(FlexLevel(a, f, var, tot, (tot / a) if a else None))
    return out
