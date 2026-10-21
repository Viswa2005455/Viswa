"""Cost & management accounting: standard-cost variances, CVP, absorption vs marginal costing
reconciliation and limiting-factor product mix.

Sign convention: a positive variance is Favourable (F), a negative one Adverse (A). Every
variance carries its formula and the substituted figures so a reviewer can tick it through.
Terminology follows CIMA / ICAI / IMA usage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import FinanceInputError


@dataclass
class Variance:
    name: str
    value: float
    nature: str  # "F" | "A" | "—"
    formula: str
    working: str
    level: int = 0  # 0 = total, 1 = component, 2 = sub-component


def _v(name: str, value: float, formula: str, working: str, level: int = 1) -> Variance:
    value = round(value, 10)
    return Variance(name, value, "F" if value > 0 else "A" if value < 0 else "—", formula, working, level)


def _pos(name: str, *vals: float):
    for v in vals:
        if v is None or v < 0:
            raise FinanceInputError(f"{name} must be zero or positive.")


def _f(x: float) -> str:
    return f"{x:,.4f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- materials

@dataclass
class MaterialIn:
    name: str
    std_qty: float      # standard quantity allowed for actual output
    std_price: float
    actual_qty: float   # actual quantity used
    actual_price: float


def material_variances(materials: list[MaterialIn]) -> dict:
    if not materials:
        raise FinanceInputError("Enter at least one material.")
    for m in materials:
        _pos(f"{m.name}: quantities and prices", m.std_qty, m.std_price, m.actual_qty, m.actual_price)
    total_sq = sum(m.std_qty for m in materials)
    total_aq = sum(m.actual_qty for m in materials)
    if total_sq == 0:
        raise FinanceInputError("Standard quantity must be greater than zero.")
    rows, out = [], []
    tot = {"cost": 0.0, "price": 0.0, "usage": 0.0, "mix": 0.0, "yield": 0.0}
    for m in materials:
        rsq = total_aq * m.std_qty / total_sq  # revised standard quantity: actual total in standard mix
        cost = m.std_qty * m.std_price - m.actual_qty * m.actual_price
        price = m.actual_qty * (m.std_price - m.actual_price)
        usage = m.std_price * (m.std_qty - m.actual_qty)
        mix = m.std_price * (rsq - m.actual_qty)
        yld = m.std_price * (m.std_qty - rsq)
        for k, v in zip(tot, (cost, price, usage, mix, yld)):
            tot[k] += v
        rows.append({"name": m.name, "rsq": rsq, "cost": cost, "price": price, "usage": usage, "mix": mix, "yield": yld})
    multi = len(materials) > 1
    out = [
        _v("Material cost variance", tot["cost"], "SQ×SP − AQ×AP", " + ".join(f"({_f(m.std_qty)}×{_f(m.std_price)} − {_f(m.actual_qty)}×{_f(m.actual_price)})" for m in materials), 0),
        _v("Material price variance", tot["price"], "AQ × (SP − AP)", " + ".join(f"{_f(m.actual_qty)}×({_f(m.std_price)} − {_f(m.actual_price)})" for m in materials)),
        _v("Material usage variance", tot["usage"], "SP × (SQ − AQ)", " + ".join(f"{_f(m.std_price)}×({_f(m.std_qty)} − {_f(m.actual_qty)})" for m in materials)),
    ]
    if multi:
        out += [
            _v("Material mix variance", tot["mix"], "SP × (RSQ − AQ), RSQ = total AQ in standard mix", "; ".join(f"{r['name']}: RSQ {_f(r['rsq'])}" for r in rows), 2),
            _v("Material yield variance", tot["yield"], "SP × (SQ − RSQ)", f"total SQ {_f(total_sq)} vs total AQ {_f(total_aq)}", 2),
        ]
    check = abs(tot["price"] + tot["usage"] - tot["cost"]) < 1e-6 * max(1.0, abs(tot["cost"]))
    return {"variances": out, "by_material": rows, "reconciles": check,
            "note": "Assumes quantity purchased equals quantity used (price variance at the point of issue)."}


# --------------------------------------------------------------------------- labour & overheads

def labour_variances(std_hours: float, std_rate: float, hours_paid: float, hours_worked: float, actual_rate: float) -> dict:
    _pos("Labour hours and rates", std_hours, std_rate, hours_paid, hours_worked, actual_rate)
    if hours_worked > hours_paid:
        raise FinanceInputError("Hours worked cannot exceed hours paid.")
    cost = std_hours * std_rate - hours_paid * actual_rate
    rate = hours_paid * (std_rate - actual_rate)
    idle = -(hours_paid - hours_worked) * std_rate
    eff = std_rate * (std_hours - hours_worked)
    return {"variances": [
        _v("Labour cost variance", cost, "SH×SR − AH(paid)×AR", f"{_f(std_hours)}×{_f(std_rate)} − {_f(hours_paid)}×{_f(actual_rate)}", 0),
        _v("Labour rate variance", rate, "AH(paid) × (SR − AR)", f"{_f(hours_paid)}×({_f(std_rate)} − {_f(actual_rate)})"),
        _v("Idle time variance", idle, "(AH paid − AH worked) × SR, always adverse", f"({_f(hours_paid)} − {_f(hours_worked)})×{_f(std_rate)}"),
        _v("Labour efficiency variance", eff, "SR × (SH − AH worked)", f"{_f(std_rate)}×({_f(std_hours)} − {_f(hours_worked)})"),
    ], "reconciles": abs(rate + idle + eff - cost) < 1e-6 * max(1.0, abs(cost))}


def variable_overhead_variances(std_hours: float, std_rate: float, hours_worked: float, actual_cost: float) -> dict:
    _pos("Variable overhead inputs", std_hours, std_rate, hours_worked, actual_cost)
    total = std_hours * std_rate - actual_cost
    exp = hours_worked * std_rate - actual_cost
    eff = std_rate * (std_hours - hours_worked)
    return {"variances": [
        _v("Variable overhead cost variance", total, "SH×SR − actual VOH", f"{_f(std_hours)}×{_f(std_rate)} − {_f(actual_cost)}", 0),
        _v("Variable overhead expenditure variance", exp, "AH×SR − actual VOH", f"{_f(hours_worked)}×{_f(std_rate)} − {_f(actual_cost)}"),
        _v("Variable overhead efficiency variance", eff, "SR × (SH − AH)", f"{_f(std_rate)}×({_f(std_hours)} − {_f(hours_worked)})"),
    ], "reconciles": abs(exp + eff - total) < 1e-6 * max(1.0, abs(total))}


def fixed_overhead_variances(budgeted_cost: float, actual_cost: float, budgeted_hours: float, std_hours: float, hours_worked: float) -> dict:
    _pos("Fixed overhead inputs", budgeted_cost, actual_cost, std_hours, hours_worked)
    if budgeted_hours <= 0:
        raise FinanceInputError("Budgeted hours must be greater than zero.")
    rate = budgeted_cost / budgeted_hours
    absorbed = std_hours * rate
    total = absorbed - actual_cost
    exp = budgeted_cost - actual_cost
    vol = absorbed - budgeted_cost
    cap = rate * (hours_worked - budgeted_hours)
    eff = rate * (std_hours - hours_worked)
    return {"absorption_rate": rate, "absorbed": absorbed, "variances": [
        _v("Fixed overhead cost (total) variance", total, "Absorbed − actual = SH×SR − actual", f"{_f(std_hours)}×{_f(rate)} − {_f(actual_cost)}", 0),
        _v("Fixed overhead expenditure variance", exp, "Budgeted − actual", f"{_f(budgeted_cost)} − {_f(actual_cost)}"),
        _v("Fixed overhead volume variance", vol, "SR × (SH − budgeted hours)", f"{_f(rate)}×({_f(std_hours)} − {_f(budgeted_hours)})"),
        _v("Capacity variance", cap, "SR × (AH − budgeted hours)", f"{_f(rate)}×({_f(hours_worked)} − {_f(budgeted_hours)})", 2),
        _v("Efficiency variance", eff, "SR × (SH − AH)", f"{_f(rate)}×({_f(std_hours)} − {_f(hours_worked)})", 2),
    ], "reconciles": abs(exp + vol - total) < 1e-6 * max(1.0, abs(total)) and abs(cap + eff - vol) < 1e-6 * max(1.0, abs(vol))}


def sales_variances(budget_qty: float, budget_price: float, actual_qty: float, actual_price: float, std_margin: float,
                    margin_basis: str = "contribution") -> dict:
    _pos("Sales quantities and prices", budget_qty, budget_price, actual_qty, actual_price)
    price = actual_qty * (actual_price - budget_price)
    volume = (actual_qty - budget_qty) * std_margin
    return {"variances": [
        _v("Sales price variance", price, "AQ × (AP − BP)", f"{_f(actual_qty)}×({_f(actual_price)} − {_f(budget_price)})"),
        _v(f"Sales volume variance ({margin_basis})", volume, "(AQ − BQ) × standard margin per unit", f"({_f(actual_qty)} − {_f(budget_qty)})×{_f(std_margin)}"),
    ]}


# --------------------------------------------------------------------------- CVP

@dataclass
class ProductCVP:
    name: str
    price: float
    variable_cost: float
    mix: float  # sales mix weight (units)


def cvp(products: list[ProductCVP], fixed_costs: float, target_profit: float | None = None, tax_rate: float = 0.0,
        expected_units: float | None = None) -> dict:
    if not products:
        raise FinanceInputError("Enter at least one product.")
    if fixed_costs < 0:
        raise FinanceInputError("Fixed costs cannot be negative.")
    if not 0 <= tax_rate < 1:
        raise FinanceInputError("Tax rate must be between 0 and 1.")
    total_mix = sum(p.mix for p in products)
    if total_mix <= 0:
        raise FinanceInputError("The sales mix must add up to more than zero.")
    w = [p.mix / total_mix for p in products]
    cm_units = [p.price - p.variable_cost for p in products]
    avg_cm = sum(wi * c for wi, c in zip(w, cm_units))
    avg_price = sum(wi * p.price for wi, p in zip(w, products))
    if avg_cm <= 0:
        raise FinanceInputError("The weighted contribution per unit is zero or negative, so there is no break-even point.")
    pv = avg_cm / avg_price
    be_units = fixed_costs / avg_cm
    out: dict = {
        "contribution_per_unit": avg_cm, "pv_ratio": pv, "breakeven_units": be_units, "breakeven_sales": be_units * avg_price,
        "products": [{"name": p.name, "contribution_per_unit": c, "pv_ratio": c / p.price if p.price else None,
                      "breakeven_units": be_units * wi, "breakeven_sales": be_units * wi * p.price}
                     for p, c, wi in zip(products, cm_units, w)],
        "steps": [f"Weighted contribution per unit = Σ(mix × (price − variable cost)) = {_f(avg_cm)}",
                  f"P/V ratio = contribution / sales = {_f(avg_cm)} / {_f(avg_price)} = {pv:.4%}",
                  f"Break-even units = fixed costs / contribution per unit = {_f(fixed_costs)} / {_f(avg_cm)} = {_f(be_units)}"],
    }
    if target_profit is not None:
        pre_tax = target_profit / (1 - tax_rate)
        units = (fixed_costs + pre_tax) / avg_cm
        out["target"] = {"after_tax_profit": target_profit, "pre_tax_profit": pre_tax, "units": units, "sales": units * avg_price}
        out["steps"].append(f"Units for target profit = (fixed costs + target ÷ (1 − tax)) / contribution = "
                            f"({_f(fixed_costs)} + {_f(pre_tax)}) / {_f(avg_cm)} = {_f(units)}")
    if expected_units is not None:
        profit = expected_units * avg_cm - fixed_costs
        mos = expected_units - be_units
        out["at_expected"] = {"units": expected_units, "sales": expected_units * avg_price, "contribution": expected_units * avg_cm,
                              "profit": profit, "margin_of_safety_units": mos,
                              "margin_of_safety_pct": mos / expected_units if expected_units else None,
                              "operating_leverage": (expected_units * avg_cm) / profit if profit > 0 else None}
    top = max(be_units * 2, (expected_units or 0) * 1.25, 1.0)
    out["chart"] = [{"units": u, "sales": u * avg_price, "total_cost": fixed_costs + u * (avg_price - avg_cm), "fixed": fixed_costs}
                    for u in [top * i / 20 for i in range(21)]]
    return out


# --------------------------------------------------------------------------- absorption vs marginal

def absorption_vs_marginal(price: float, variable_prod_cost: float, variable_selling_cost: float, fixed_prod_overhead: float,
                           normal_units: float, produced_units: float, sold_units: float, opening_units: float,
                           fixed_selling_admin: float) -> dict:
    _pos("Costs and units", price, variable_prod_cost, variable_selling_cost, fixed_prod_overhead, produced_units, sold_units,
         opening_units, fixed_selling_admin)
    if normal_units <= 0:
        raise FinanceInputError("Normal (budgeted) production must be greater than zero.")
    closing = opening_units + produced_units - sold_units
    if closing < 0:
        raise FinanceInputError("Sales exceed opening inventory plus production.")
    oar = fixed_prod_overhead / normal_units
    sales = sold_units * price
    # marginal costing
    mc_cogs = sold_units * variable_prod_cost
    contribution = sales - mc_cogs - sold_units * variable_selling_cost
    mc_profit = contribution - fixed_prod_overhead - fixed_selling_admin
    # absorption costing (opening inventory valued at the same full cost)
    full = variable_prod_cost + oar
    under_over = produced_units * oar - fixed_prod_overhead  # + over-absorbed, − under-absorbed
    ac_cogs = (opening_units + produced_units - closing) * full
    ac_gross = sales - ac_cogs + under_over
    ac_profit = ac_gross - sold_units * variable_selling_cost - fixed_selling_admin
    diff = (closing - opening_units) * oar
    return {
        "oar": oar, "closing_units": closing, "full_cost_per_unit": full,
        "marginal": {"sales": sales, "variable_cost_of_sales": mc_cogs, "variable_selling": sold_units * variable_selling_cost,
                     "contribution": contribution, "fixed_production": fixed_prod_overhead, "fixed_selling_admin": fixed_selling_admin,
                     "profit": mc_profit},
        "absorption": {"sales": sales, "cost_of_sales": ac_cogs, "over_under_absorption": under_over, "gross_profit": ac_gross,
                       "variable_selling": sold_units * variable_selling_cost, "fixed_selling_admin": fixed_selling_admin,
                       "profit": ac_profit},
        "reconciliation": {"difference": ac_profit - mc_profit, "explained": diff,
                           "working": f"(closing {_f(closing)} − opening {_f(opening_units)}) units × OAR {_f(oar)} = {_f(diff)}",
                           "reconciles": abs((ac_profit - mc_profit) - diff) < 1e-6 * max(1.0, abs(diff))},
        "note": "Under absorption costing, fixed production overhead in the change in inventory is carried forward, so "
                "profit is higher when inventory builds up and lower when it runs down.",
    }


# --------------------------------------------------------------------------- limiting factor

@dataclass
class LFProduct:
    name: str
    contribution_per_unit: float
    resource_per_unit: float
    max_demand: float


def limiting_factor(products: list[LFProduct], resource_available: float, resource_name: str = "machine hours",
                    fixed_costs: float | None = None) -> dict:
    if not products:
        raise FinanceInputError("Enter at least one product.")
    if resource_available < 0:
        raise FinanceInputError("Available resource cannot be negative.")
    rows = []
    for p in products:
        if p.resource_per_unit <= 0:
            raise FinanceInputError(f"{p.name}: resource per unit must be greater than zero.")
        rows.append({"name": p.name, "contribution_per_unit": p.contribution_per_unit, "resource_per_unit": p.resource_per_unit,
                     "max_demand": p.max_demand, "contribution_per_resource": p.contribution_per_unit / p.resource_per_unit})
    order = sorted(rows, key=lambda r: r["contribution_per_resource"], reverse=True)
    left = resource_available
    for rank, r in enumerate(order, 1):
        r["rank"] = rank
        if r["contribution_per_unit"] <= 0:
            r["units"] = 0.0
            r["reason"] = "Not produced: contribution is zero or negative."
        else:
            units = min(r["max_demand"], left / r["resource_per_unit"])
            r["units"] = units
            r["reason"] = "Full demand met." if units >= r["max_demand"] - 1e-9 else ("Resource exhausted." if units > 0 else "No resource left.")
            left -= units * r["resource_per_unit"]
        r["resource_used"] = r["units"] * r["resource_per_unit"]
        r["contribution"] = r["units"] * r["contribution_per_unit"]
    total = sum(r["contribution"] for r in order)
    needed = sum(r["max_demand"] * r["resource_per_unit"] for r in rows)
    return {"plan": order, "total_contribution": total, "profit": total - fixed_costs if fixed_costs is not None else None,
            "resource_available": resource_available, "resource_needed_for_full_demand": needed,
            "is_binding": needed > resource_available, "resource_unused": max(left, 0.0), "resource_name": resource_name,
            "note": "Ranks by contribution per unit of the scarce resource. With more than one binding constraint, use linear programming."}
