"""Financial accounting and audit schedules for practitioners.

Each function returns a full schedule plus journal entries and the standard it follows, so the
output can be tied out and filed as a workpaper. References:
* Bonds: effective interest method (ASC 835-30; IFRS 9 amortised cost; Ind AS 109).
* Leases (lessee): ASC 842 finance and operating; IFRS 16 / Ind AS 116 single model.
* Depreciation: ASC 360; IAS 16 / Ind AS 16.
* EPS: ASC 260; IAS 33 / Ind AS 33 (treasury stock and if-converted methods).
* Deferred tax: ASC 740; IAS 12 / Ind AS 12 (temporary differences).
* Materiality: AU-C 320 / ISA 320 / SA 320 (common benchmark ranges; professional judgement applies).

Amounts are not rounded inside the engine; the last period absorbs floating-point residue so
schedules close exactly to zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import FinanceInputError


@dataclass
class JournalEntry:
    when: str
    lines: list[dict]  # {"account", "debit", "credit"}
    memo: str = ""


def _je(when: str, memo: str, *lines: tuple[str, float, float]) -> JournalEntry:
    return JournalEntry(when, [{"account": a, "debit": round(d, 2) if d else None, "credit": round(c, 2) if c else None}
                               for a, d, c in lines if (d or c)], memo)


# --------------------------------------------------------------------------- bonds

def bond_schedule(face: float, coupon_rate: float, market_rate: float, years: float, payments_per_year: int = 2,
                  perspective: str = "issuer") -> dict:
    if face <= 0 or years <= 0:
        raise FinanceInputError("Face value and term must be positive.")
    if payments_per_year not in (1, 2, 4, 12):
        raise FinanceInputError("Payments per year must be 1, 2, 4 or 12.")
    if coupon_rate < 0 or market_rate <= -1:
        raise FinanceInputError("Rates must be decimals (0.08 = 8%).")
    n = round(years * payments_per_year)
    if abs(n - years * payments_per_year) > 1e-9:
        raise FinanceInputError("The term must be a whole number of payment periods.")
    c = face * coupon_rate / payments_per_year
    r = market_rate / payments_per_year
    pv = sum(c / (1 + r) ** t for t in range(1, n + 1)) + face / (1 + r) ** n
    rows, carrying = [], pv
    for t in range(1, n + 1):
        interest = carrying * r
        amort = interest - c
        closing = carrying + amort
        if t == n:  # close exactly to face value
            amort = face - carrying
            interest = c + amort
            closing = face
        rows.append({"period": t, "opening": carrying, "cash": c, "interest": interest, "amortisation": amort, "closing": closing})
        carrying = closing
    kind = "premium" if pv > face + 1e-9 else "discount" if pv < face - 1e-9 else "par"
    diff = abs(pv - face)
    first = rows[0]
    if perspective == "issuer":
        jes = [
            _je("Issue", f"Bonds issued at {kind}", ("Cash", pv, 0), ("Discount on bonds payable", diff if kind == "discount" else 0, 0),
                ("Bonds payable", 0, face), ("Premium on bonds payable", 0, diff if kind == "premium" else 0)),
            _je("Period 1", "Interest expense at the market rate on the carrying amount",
                ("Interest expense", first["interest"], 0),
                ("Premium on bonds payable", -first["amortisation"] if kind == "premium" else 0, 0),
                ("Discount on bonds payable", 0, first["amortisation"] if kind == "discount" else 0),
                ("Cash", 0, first["cash"])),
        ]
    elif perspective == "investor":
        jes = [
            _je("Purchase", "Held-to-maturity / amortised-cost investment", ("Investment in bonds", pv, 0), ("Cash", 0, pv)),
            _je("Period 1", "Interest income at the effective rate", ("Cash", first["cash"], 0),
                ("Investment in bonds", first["amortisation"] if first["amortisation"] > 0 else 0, -first["amortisation"] if first["amortisation"] < 0 else 0),
                ("Interest income", 0, first["interest"])),
        ]
    else:
        raise FinanceInputError("Perspective must be 'issuer' or 'investor'.")
    return {"issue_price": pv, "kind": kind, "premium_or_discount": diff, "periods": n, "period_rate": r, "coupon_per_period": c,
            "schedule": rows, "journal_entries": [e.__dict__ for e in jes],
            "total_interest": sum(x["interest"] for x in rows),
            "standard": "Effective interest method — ASC 835-30 (US GAAP); amortised cost under IFRS 9 / Ind AS 109.",
            "steps": [f"Issue price = PV of coupons + PV of face at {r:.4%} per period = {pv:,.2f}",
                      f"Interest = opening carrying amount × {r:.4%}; amortisation = interest − cash coupon {c:,.2f}"]}


# --------------------------------------------------------------------------- leases (lessee)

def lease_schedule(payment: float, periods: int, annual_rate: float, periods_per_year: int = 1, timing: str = "advance",
                   initial_direct_costs: float = 0.0, incentives: float = 0.0, prepaid: float = 0.0,
                   classification: str = "finance") -> dict:
    if payment <= 0 or periods <= 0:
        raise FinanceInputError("Payment and number of periods must be positive.")
    if periods_per_year not in (1, 2, 4, 12):
        raise FinanceInputError("Periods per year must be 1, 2, 4 or 12.")
    if timing not in ("advance", "arrears"):
        raise FinanceInputError("Timing must be 'advance' (start of period) or 'arrears' (end of period).")
    if classification not in ("finance", "operating"):
        raise FinanceInputError("Classification must be 'finance' or 'operating'.")
    if annual_rate <= -1:
        raise FinanceInputError("Discount rate must be a decimal greater than -100%.")
    r = annual_rate / periods_per_year
    disc = [1 / (1 + r) ** (t if timing == "arrears" else t - 1) for t in range(1, periods + 1)]
    liability0 = payment * sum(disc)
    rou0 = liability0 + initial_direct_costs + prepaid - incentives
    total_cost = payment * periods + initial_direct_costs + prepaid - incentives
    sl_cost = total_cost / periods
    rows, liab, rou = [], liability0, rou0
    for t in range(1, periods + 1):
        if timing == "advance":
            pay = payment
            after_pay = liab - pay
            interest = after_pay * r
            closing = after_pay + interest
        else:
            interest = liab * r
            pay = payment
            closing = liab + interest - pay
        if t == periods:
            closing = 0.0
        if classification == "finance":
            amort = rou0 / periods
            expense = {"interest": interest, "amortisation": amort, "total": interest + amort}
        else:
            amort = sl_cost - interest  # ASC 842 operating: single straight-line cost; ROU is the plug
            expense = {"interest": None, "amortisation": amort, "total": sl_cost}
        rou_close = rou - amort if t < periods else 0.0
        rows.append({"period": t, "opening_liability": liab, "payment": pay, "interest": interest, "closing_liability": closing,
                     "opening_rou": rou, "rou_amortisation": amort, "closing_rou": rou_close, "expense": expense})
        liab, rou = closing, rou_close
    first = rows[0]
    jes = [_je("Commencement", "Recognise lease liability and right-of-use asset",
               ("Right-of-use asset", rou0, 0), ("Lease liability", 0, liability0),
               ("Cash (initial direct costs)", 0, initial_direct_costs), ("Cash / receivable (incentives received)", incentives, 0),
               ("Prepaid lease payments", 0, prepaid))]
    if classification == "finance":
        jes.append(_je("Period 1", "Finance lease (ASC 842) / IFRS 16: interest + straight-line ROU amortisation",
                       ("Interest expense", first["interest"], 0), ("Lease liability", first["payment"] - (first["interest"] if timing == "arrears" else 0), 0),
                       ("Cash", 0, first["payment"]), ("Lease liability (interest accrued)", 0, first["interest"] if timing == "advance" else 0),
                       ("Amortisation expense — ROU asset", first["rou_amortisation"], 0), ("Right-of-use asset", 0, first["rou_amortisation"])))
    else:
        jes.append(_je("Period 1", "ASC 842 operating lease: single straight-line lease cost",
                       ("Lease expense", sl_cost, 0), ("Lease liability", first["payment"] - first["interest"], 0),
                       ("Cash", 0, first["payment"]), ("Right-of-use asset", 0, first["rou_amortisation"])))
    return {"initial_liability": liability0, "initial_rou_asset": rou0, "period_rate": r, "total_cash": payment * periods,
            "straight_line_cost": sl_cost if classification == "operating" else None, "schedule": rows,
            "journal_entries": [e.__dict__ for e in jes], "classification": classification,
            "standard": ("ASC 842 finance lease; same pattern as the IFRS 16 / Ind AS 116 lessee model."
                         if classification == "finance" else
                         "ASC 842 operating lease (US GAAP only). Under IFRS 16 / Ind AS 116 every lease follows the finance pattern."),
            "steps": [f"Lease liability = PV of {periods} payments of {payment:,.2f} in {timing} at {r:.4%} per period = {liability0:,.2f}",
                      f"ROU asset = liability + initial direct costs + prepaid − incentives = {rou0:,.2f}"]}


# --------------------------------------------------------------------------- depreciation

def depreciation_schedule(cost: float, salvage: float, life: int, method: str = "straight_line", units: list[float] | None = None,
                          ddb_factor: float = 2.0, switch_to_sl: bool = True) -> dict:
    if cost <= 0 or life <= 0 or salvage < 0 or salvage > cost:
        raise FinanceInputError("Cost and life must be positive, and salvage between zero and cost.")
    base = cost - salvage
    rows, nbv, acc = [], cost, 0.0
    if method == "units":
        if not units or len(units) != life or any(u < 0 for u in units) or sum(units) <= 0:
            raise FinanceInputError("Units-of-production needs one non-negative unit figure per year.")
        total_units = sum(units)
    for y in range(1, life + 1):
        if method == "straight_line":
            dep = base / life
        elif method == "syd":
            dep = base * (life - y + 1) / (life * (life + 1) / 2)
        elif method == "ddb":
            dep = nbv * ddb_factor / life
            if switch_to_sl:
                sl = (nbv - salvage) / (life - y + 1)
                dep = max(dep, sl)
            dep = min(dep, max(nbv - salvage, 0.0))
        elif method == "units":
            dep = base * units[y - 1] / total_units  # type: ignore[index]
        else:
            raise FinanceInputError("Method must be straight_line, ddb, syd or units.")
        if y == life:
            dep = nbv - salvage
        acc += dep
        rows.append({"year": y, "opening_nbv": nbv, "depreciation": dep, "accumulated": acc, "closing_nbv": nbv - dep})
        nbv -= dep
    return {"method": method, "schedule": rows, "depreciable_base": base,
            "standard": "ASC 360 (US GAAP); IAS 16 / Ind AS 16. Choose the method that reflects the pattern of consumption of benefits."}


# --------------------------------------------------------------------------- EPS

@dataclass
class Dilutive:
    kind: str  # "options" | "convertible_preferred" | "convertible_debt"
    name: str
    shares: float  # options: number of options; convertibles: shares on conversion
    exercise_price: float | None = None
    preferred_dividends: float | None = None
    interest_after_tax: float | None = None


def eps(net_income: float, preferred_dividends: float, weighted_shares: float, average_price: float | None,
        securities: list[Dilutive]) -> dict:
    if weighted_shares <= 0:
        raise FinanceInputError("Weighted average shares must be positive.")
    num = net_income - preferred_dividends
    basic = num / weighted_shares
    cands = []
    for s in securities:
        if s.kind == "options":
            if average_price is None or average_price <= 0 or s.exercise_price is None:
                raise FinanceInputError(f"{s.name}: options need an exercise price and the average market price.")
            if s.exercise_price >= average_price:
                cands.append({**s.__dict__, "incremental_shares": 0.0, "numerator_effect": 0.0, "per_share": None,
                              "included": False, "reason": "Out of the money (exercise price ≥ average price): antidilutive."})
                continue
            inc = s.shares - s.shares * s.exercise_price / average_price  # treasury stock method
            cands.append({**s.__dict__, "incremental_shares": inc, "numerator_effect": 0.0, "per_share": 0.0,
                          "working": f"{s.shares:,.0f} − {s.shares:,.0f} × {s.exercise_price} / {average_price} = {inc:,.2f}"})
        elif s.kind == "convertible_preferred":
            add = s.preferred_dividends or 0.0
            cands.append({**s.__dict__, "incremental_shares": s.shares, "numerator_effect": add,
                          "per_share": add / s.shares if s.shares else None, "working": f"add back preferred dividends {add:,.2f}"})
        elif s.kind == "convertible_debt":
            add = s.interest_after_tax or 0.0
            cands.append({**s.__dict__, "incremental_shares": s.shares, "numerator_effect": add,
                          "per_share": add / s.shares if s.shares else None, "working": f"add back after-tax interest {add:,.2f}"})
        else:
            raise FinanceInputError(f"Unknown security type '{s.kind}'.")
    # include in order of increasing incremental EPS while each one still dilutes (ASC 260-10-45-18)
    order = sorted([c for c in cands if c.get("per_share") is not None], key=lambda c: c["per_share"])
    n, d, running = num, weighted_shares, basic
    for c in order:
        new = (n + c["numerator_effect"]) / (d + c["incremental_shares"])
        if new < running - 1e-12:
            n, d, running = n + c["numerator_effect"], d + c["incremental_shares"], new
            c["included"], c["reason"] = True, f"Dilutive: EPS falls to {new:,.4f}."
        else:
            c["included"], c["reason"] = False, f"Antidilutive at this step (EPS would be {new:,.4f})."
    diluted = running if net_income - preferred_dividends > 0 else basic
    return {"basic": basic, "diluted": diluted, "numerator_basic": num, "numerator_diluted": n, "shares_basic": weighted_shares,
            "shares_diluted": d, "securities": cands,
            "notes": [] if num > 0 else ["With a loss, potential shares are antidilutive, so diluted EPS equals basic."],
            "standard": "ASC 260 (US GAAP); IAS 33 / Ind AS 33. Securities enter in order of incremental EPS, most dilutive first."}


# --------------------------------------------------------------------------- deferred tax

@dataclass
class TempDiff:
    name: str
    kind: str  # "asset" | "liability" (balance-sheet item)
    carrying_amount: float
    tax_base: float


def deferred_tax(items: list[TempDiff], tax_rate: float, current_tax: float | None = None, opening_net_dtl: float = 0.0) -> dict:
    if not 0 <= tax_rate < 1:
        raise FinanceInputError("Tax rate must be a decimal between 0 and 1.")
    rows, dta, dtl = [], 0.0, 0.0
    for it in items:
        if it.kind not in ("asset", "liability"):
            raise FinanceInputError(f"{it.name}: kind must be 'asset' or 'liability'.")
        diff = it.carrying_amount - it.tax_base
        # assets: carrying > tax base -> taxable difference (DTL); liabilities: carrying > tax base -> deductible (DTA)
        taxable = diff if it.kind == "asset" else -diff
        amount = taxable * tax_rate
        nature = "DTL" if amount > 0 else "DTA" if amount < 0 else "—"
        if amount > 0:
            dtl += amount
        else:
            dta += -amount
        rows.append({"name": it.name, "kind": it.kind, "carrying_amount": it.carrying_amount, "tax_base": it.tax_base,
                     "temporary_difference": diff, "type": "taxable" if taxable > 0 else "deductible" if taxable < 0 else "none",
                     "deferred_tax": abs(amount), "nature": nature})
    net = dtl - dta
    movement = net - opening_net_dtl
    out = {"items": rows, "total_dta": dta, "total_dtl": dtl, "net_dtl": net, "deferred_tax_expense": movement,
           "standard": "ASC 740 (US GAAP); IAS 12 / Ind AS 12 — balance-sheet liability method. Assess DTAs for recoverability "
                       "(valuation allowance under ASC 740; probable future taxable profit under IAS 12)."}
    if current_tax is not None:
        out["income_tax_expense"] = current_tax + movement
        out["journal_entries"] = [_je("Year end", "Current and deferred tax",
                                      ("Income tax expense", current_tax + movement if current_tax + movement > 0 else 0, 0),
                                      ("Deferred tax liability (net)", -movement if movement < 0 else 0, movement if movement > 0 else 0),
                                      ("Income taxes payable", 0, current_tax)).__dict__]
    return out


# --------------------------------------------------------------------------- materiality

BENCHMARKS = {
    "profit_before_tax": ("Profit before tax", 0.05, 0.10),
    "revenue": ("Revenue", 0.005, 0.01),
    "total_assets": ("Total assets", 0.01, 0.02),
    "equity": ("Equity", 0.01, 0.05),
    "expenses": ("Total expenses (not-for-profit / public sector)", 0.005, 0.02),
}


def materiality(values: dict[str, float], selected: str, pct: float, performance_pct: float = 0.75, trivial_pct: float = 0.05) -> dict:
    if selected not in BENCHMARKS:
        raise FinanceInputError(f"Benchmark must be one of {', '.join(BENCHMARKS)}.")
    if selected not in values or values[selected] is None or values[selected] <= 0:
        raise FinanceInputError("Enter a positive amount for the selected benchmark.")
    if not 0 < pct <= 0.2 or not 0 < performance_pct <= 1 or not 0 < trivial_pct <= 0.2:
        raise FinanceInputError("Percentages must be decimals in a sensible range (e.g. 0.05 = 5%).")
    ranges = []
    for k, (label, lo, hi) in BENCHMARKS.items():
        v = values.get(k)
        if v is not None and v > 0:
            ranges.append({"benchmark": k, "label": label, "amount": v, "low_pct": lo, "high_pct": hi, "low": v * lo, "high": v * hi})
    lo, hi = BENCHMARKS[selected][1], BENCHMARKS[selected][2]
    overall = values[selected] * pct
    notes = []
    if not lo <= pct <= hi:
        notes.append(f"The chosen {pct:.2%} is outside the common range of {lo:.2%}–{hi:.2%} for this benchmark; document the rationale.")
    return {"overall": overall, "performance": overall * performance_pct, "clearly_trivial": overall * trivial_pct,
            "selected": selected, "pct": pct, "performance_pct": performance_pct, "trivial_pct": trivial_pct, "ranges": ranges, "notes": notes,
            "standard": "AU-C 320 (AICPA) / PCAOB AS 2105 / ISA 320 / SA 320. Ranges are common practice, not requirements; "
                        "materiality is a matter of professional judgement and must be documented."}
