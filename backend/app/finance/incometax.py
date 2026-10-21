"""Indian income tax for FY 2025-26 (AY 2026-27), under the Income-tax Act, 1961.

The Income-tax Act, 2025 applies from 1 April 2026 ("tax year" 2026-27 onwards), but income
earned in FY 2025-26 is still assessed, and its returns filed, under the 1961 Act (savings
clause, s.536 of the 2025 Act). This module covers that year only; every rule names its section
and the official page it was taken from (SOURCES), so a reviewer can check it.

What it does:
  * select_itr      which ITR form a taxpayer should file, with the reason for each exclusion
  * individual_tax  old vs new regime for an individual or HUF, with surcharge marginal relief
  * entity_tax      firm / LLP, domestic company (normal, 115BAA, 115BAB, MAT) and co-operative
  * due_dates       return due dates for AY 2026-27 and the 234F fee / 234A interest

It does not file a return: only an e-Return Intermediary registered with the Income Tax
Department may submit returns through the department's APIs. The output is a computation the
taxpayer or their CA checks and enters (or imports as JSON) in the official utility or portal.
All amounts are in rupees. Missing inputs are treated as "none", never invented.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass, field

from . import FinanceInputError

YEAR = {"financial_year": "2025-26", "assessment_year": "2026-27", "law": "Income-tax Act, 1961"}

SOURCES = {
    "rates": "https://www.incometaxindia.gov.in/w/tax-rates%E2%80%8B",
    "itr1": "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1",
    "itr2": "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-2/itr-2-faqs",
    "itr3": "https://www.incometax.gov.in/iec/foportal/help/individual-business-profession",
    "itr4": "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr%204-faqs",
    "itr5_7": "https://www.incometaxindia.gov.in/w/what-are-the-forms-of-return-prescribed-under-the-income-tax-law-",
    "itr6": "https://www.incometax.gov.in/iec/foportal/help/company/return-applicable",
    "rebate_old": "https://www.incometaxindia.gov.in/w/what-is-rebate-under-section-87a-for-f.y-2025-26-and-who-can-claim-it-",
    "capital_gains": "https://www.incometaxindia.gov.in/w/section-112a-60",
    "due_dates": "https://www.incometaxindia.gov.in/w/section-139-93",
    "circular_7_2026": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-09/Circular-7-2026.pdf",
    "fee_234f": "https://www.incometaxindia.gov.in/w/section-234f-11",
    "interest": "https://www.incometaxindia.gov.in/w/interest-payable-by-the-taxpayer-under-the-income-tax-act%E2%80%8B%E2%80%8B",
    "tax_audit": "https://www.incometaxindia.gov.in/w/section-44ab-38",
    "transition": "https://www.incometaxindia.gov.in/documents/81799/11848482/FAQs-on-Interplay-and-Transition.pdf",
    "offline_utility": "https://www.incometax.gov.in/iec/foportal/downloads",
    "eri": "https://www.incometax.gov.in/iec/foportal/help/eri/registration",
    "efiling": "https://www.incometax.gov.in/iec/foportal/",
}

LAKH = 100_000
CRORE = 10_000_000
CESS = 0.04
INF = math.inf

# Section 115BAC(1A) slabs (new regime, default) and the old-regime slabs above the exemption limit.
NEW_SLABS = [(4 * LAKH, 0.0), (8 * LAKH, 0.05), (12 * LAKH, 0.10), (16 * LAKH, 0.15), (20 * LAKH, 0.20), (24 * LAKH, 0.25), (INF, 0.30)]
OLD_EXEMPTION = {"below_60": 2.5 * LAKH, "60_to_79": 3 * LAKH, "80_plus": 5 * LAKH}
STANDARD_DEDUCTION = {"new": 75_000, "old": 50_000}
REBATE = {"new": (12 * LAKH, 60_000), "old": (5 * LAKH, 12_500)}  # (income limit, maximum rebate)
SURCHARGE_INDIVIDUAL = [(50 * LAKH, 0.10), (1 * CRORE, 0.15), (2 * CRORE, 0.25), (5 * CRORE, 0.37)]
SPECIAL_SURCHARGE_CAP = 0.15  # dividends and gains under 111A / 112 / 112A
NEW_REGIME_SURCHARGE_CAP = 0.25
LTCG_112A_EXEMPT = 1.25 * LAKH
RATE_111A, RATE_112A, RATE_112, RATE_115BB = 0.20, 0.125, 0.125, 0.30
CAPS_OLD = {"80C": 150_000, "80CCD(1B)": 50_000, "80TTA": 10_000, "80TTB": 50_000}
HP_LOSS_SETOFF_CAP = 2 * LAKH  # s.71(3A), old regime


def _nn(name: str, v: float) -> float:
    if v is None:
        return 0.0
    if v < 0 or not math.isfinite(v):
        raise FinanceInputError(f"{name} must be zero or a positive amount.")
    return float(v)


def round10(x: float) -> float:
    """Sections 288A/288B: income and tax are rounded to the nearest multiple of ten rupees."""
    return math.floor(x / 10 + 0.5) * 10 if x > 0 else 0.0


def slab_tax(income: float, slabs: list[tuple[float, float]]) -> tuple[float, list[dict]]:
    tax, lower, rows = 0.0, 0.0, []
    for upper, rate in slabs:
        if income <= lower:
            break
        part = min(income, upper) - lower
        if part > 0:
            rows.append({"from": lower, "to": None if upper == INF else upper, "amount": part, "rate": rate, "tax": part * rate})
            tax += part * rate
        lower = upper
    return tax, rows


def old_slabs(exemption: float) -> list[tuple[float, float]]:
    slabs = [(exemption, 0.0)]
    if exemption < 5 * LAKH:
        slabs.append((5 * LAKH, 0.05))
    slabs += [(10 * LAKH, 0.20), (INF, 0.30)]
    return slabs


# ---------------------------------------------------------------- ITR form selection
@dataclass
class TaxpayerProfile:
    taxpayer_type: str = "individual"  # individual | huf | firm | llp | company | aop_boi | cooperative | local_authority | trust_or_institution
    residential_status: str = "resident"  # resident | rnor | non_resident
    total_income: float = 0.0
    salary_or_pension: bool = False
    house_properties: int = 0
    business_income: bool = False
    presumptive: str = "none"  # none | 44AD | 44ADA | 44AE
    partner_remuneration: bool = False  # interest / salary / bonus / commission from a firm
    stcg: bool = False
    ltcg_112a: float = 0.0
    other_capital_gains: bool = False  # e.g. 112 LTCG on property, debt funds
    agricultural_income: float = 0.0
    director: bool = False
    unlisted_equity: bool = False
    foreign_assets_or_income: bool = False
    tds_194n: bool = False
    esop_tax_deferred: bool = False
    losses_to_carry_forward: bool = False
    files_under_139_4a_to_4d: bool = False  # charitable/religious trusts, political parties, research bodies, universities
    claims_section_11: bool = False


def select_itr(p: TaxpayerProfile) -> dict:
    _nn("Total income", p.total_income)
    _nn("LTCG under 112A", p.ltcg_112a)
    _nn("Agricultural income", p.agricultural_income)
    if p.house_properties < 0:
        raise FinanceInputError("Number of house properties cannot be negative.")
    t = p.taxpayer_type
    reasons: list[str] = []
    excluded: list[dict] = []

    def out(form: str, name: str, src: str) -> dict:
        return {"form": form, "name": name, "reasons": reasons, "simpler_forms_excluded": excluded,
                "due_date_category": _due_category(p, form), "source": SOURCES[src], "year": YEAR,
                "note": "Check the form's instructions on the e-filing portal before filing; eligibility rules change each year."}

    if p.files_under_139_4a_to_4d or (t == "company" and p.claims_section_11) or t == "trust_or_institution":
        reasons.append("Required to file under section 139(4A), (4B), (4C) or (4D), or a company claiming exemption under section 11.")
        return out("ITR-7", "ITR-7", "itr5_7")
    if t == "company":
        reasons.append("Companies file ITR-6 unless they claim exemption under section 11.")
        return out("ITR-6", "ITR-6", "itr6")

    common_44 = []  # disqualifiers shared by ITR-1 and ITR-4
    if p.residential_status != "resident":
        common_44.append("Only residents (ordinarily resident) can use it.")
    if p.total_income > 50 * LAKH:
        common_44.append("Total income is above ₹50 lakh.")
    if p.director:
        common_44.append("A company director cannot use it.")
    if p.unlisted_equity:
        common_44.append("Held unlisted equity shares during the year.")
    if p.stcg:
        common_44.append("Has short-term capital gains.")
    if p.ltcg_112a > LTCG_112A_EXEMPT:
        common_44.append("Long-term capital gains under 112A exceed ₹1.25 lakh.")
    if p.other_capital_gains:
        common_44.append("Has capital gains other than 112A long-term gains.")
    if p.agricultural_income > 5_000:
        common_44.append("Agricultural income is above ₹5,000.")
    if p.foreign_assets_or_income:
        common_44.append("Has foreign assets, foreign income or signing authority outside India.")
    if p.house_properties > 2:
        common_44.append("Has more than two house properties.")
    if p.losses_to_carry_forward:
        common_44.append("Has losses to carry forward or brought-forward losses to set off.")

    if t in ("firm", "llp", "aop_boi", "cooperative", "local_authority"):
        if t == "firm" and p.business_income and p.presumptive in ("44AD", "44ADA", "44AE"):
            firm_bars = [c for c in common_44 if "director" not in c and "unlisted" not in c]
            if not firm_bars:
                reasons.append(f"A resident firm (not an LLP) with presumptive income under section {p.presumptive} and total income up to ₹50 lakh.")
                return out("ITR-4", "ITR-4 (Sugam)", "itr4")
            excluded.append({"form": "ITR-4 (Sugam)", "why": firm_bars})
        elif t == "llp":
            excluded.append({"form": "ITR-4 (Sugam)", "why": ["LLPs cannot use ITR-4."]})
        reasons.append("Firms, LLPs, AOPs, BOIs, co-operative societies and local authorities file ITR-5 (unless required to file ITR-7).")
        return out("ITR-5", "ITR-5", "itr5_7")

    if t not in ("individual", "huf"):
        raise FinanceInputError("Unknown taxpayer type.")

    if p.business_income or p.partner_remuneration:
        if p.partner_remuneration:
            reasons.append("Receives interest, salary, bonus or commission from a partnership firm, which is business income.")
        bars = list(common_44)
        if p.presumptive not in ("44AD", "44ADA", "44AE"):
            bars.append("Business or professional income is not computed on a presumptive basis (44AD / 44ADA / 44AE).")
        if t == "huf" and p.presumptive == "44ADA":
            bars.append("A HUF cannot use section 44ADA.")
        if p.partner_remuneration:
            bars.append("Partner's remuneration from a firm requires ITR-3.")
        if p.esop_tax_deferred:
            bars.append("Has deferred tax on ESOPs.")
        if not bars:
            reasons.append(f"Presumptive business or professional income under section {p.presumptive}, total income up to ₹50 lakh.")
            return out("ITR-4", "ITR-4 (Sugam)", "itr4")
        excluded.append({"form": "ITR-4 (Sugam)", "why": bars})
        reasons.append("Individuals and HUFs with income from business or profession file ITR-3.")
        return out("ITR-3", "ITR-3", "itr3")

    bars = list(common_44)
    if t == "huf":
        bars.append("ITR-1 is for individuals only, not HUFs.")
    if p.tds_194n:
        bars.append("Tax was deducted under section 194N (cash withdrawals).")
    if p.esop_tax_deferred:
        bars.append("Has deferred tax on ESOPs.")
    if not bars:
        reasons.append("Resident individual, total income up to ₹50 lakh, from salary or pension, up to two house properties, other sources, "
                       "112A long-term gains up to ₹1.25 lakh and agricultural income up to ₹5,000.")
        return out("ITR-1", "ITR-1 (Sahaj)", "itr1")
    excluded.append({"form": "ITR-1 (Sahaj)", "why": bars})
    reasons.append("Individuals and HUFs without business or professional income file ITR-2.")
    return out("ITR-2", "ITR-2", "itr2")


def _due_category(p: TaxpayerProfile, form: str) -> str:
    if p.taxpayer_type == "company" or form in ("ITR-6", "ITR-7"):
        return "audit"
    if p.business_income or p.partner_remuneration or form in ("ITR-3", "ITR-4", "ITR-5"):
        return "business_no_audit"
    return "no_business"


# ---------------------------------------------------------------- individuals and HUFs
@dataclass
class IndividualIncome:
    taxpayer_type: str = "individual"  # individual | huf
    age: str = "below_60"  # below_60 | 60_to_79 | 80_plus
    resident: bool = True
    salary: float = 0.0  # gross salary / pension after exempt allowances
    house_property: float = 0.0  # net income from house property (negative = loss)
    business: float = 0.0
    other_sources: float = 0.0  # interest, dividends, family pension etc. taxed at slab rates
    stcg_111a: float = 0.0
    ltcg_112a: float = 0.0  # before the ₹1.25 lakh exemption
    ltcg_112: float = 0.0  # other long-term gains at 12.5% without indexation
    winnings_115bb: float = 0.0  # lottery, online games etc. at 30%
    deductions_old: dict[str, float] = field(default_factory=dict)  # 80C, 80CCD(1B), 80D, 80TTA, 80TTB, 80G, other
    employer_nps_80ccd2: float = 0.0  # allowed in both regimes
    tds_and_advance_tax: float = 0.0
    count_special_income_for_rebate: bool = True  # see REBATE_NOTE


REBATE_NOTE = ("From FY 2025-26 the new-regime 87A rebate cannot exceed the tax on slab-rate income, so it never reduces tax on "
               "111A / 112 / 112A gains. Commentators differ on whether those gains count towards the ₹12 lakh limit; by default "
               "they are counted (the statute tests 'total income'), which is the cautious reading. Switch it off to see the other reading.")


def _special_taxes(inc: IndividualIncome, unused_exemption: float) -> tuple[dict, float]:
    """Tax on special-rate income. A resident may use the unexhausted basic exemption against 111A /
    112 / 112A gains (provisos to those sections); it is applied to the highest-taxed gains first."""
    stcg, ltcg112, ltcg112a = inc.stcg_111a, inc.ltcg_112, max(0.0, inc.ltcg_112a - LTCG_112A_EXEMPT)
    used = {"111A": 0.0, "112": 0.0, "112A": 0.0}
    left = unused_exemption if inc.resident else 0.0
    for key in ("111A", "112", "112A"):
        base = {"111A": stcg, "112": ltcg112, "112A": ltcg112a}[key]
        take = min(base, left)
        used[key] = take
        left -= take
    rows = {
        "111A": {"income": stcg, "exemption_used": used["111A"], "rate": RATE_111A, "tax": (stcg - used["111A"]) * RATE_111A},
        "112": {"income": ltcg112, "exemption_used": used["112"], "rate": RATE_112, "tax": (ltcg112 - used["112"]) * RATE_112},
        "112A": {"income": inc.ltcg_112a, "exempt_1_25_lakh": min(inc.ltcg_112a, LTCG_112A_EXEMPT), "exemption_used": used["112A"],
                 "rate": RATE_112A, "tax": (ltcg112a - used["112A"]) * RATE_112A},
        "115BB": {"income": inc.winnings_115bb, "exemption_used": 0.0, "rate": RATE_115BB, "tax": inc.winnings_115bb * RATE_115BB},
    }
    return rows, sum(used.values())


def _surcharge_rate(total_income: float, regime: str) -> float:
    rate = 0.0
    for threshold, r in SURCHARGE_INDIVIDUAL:
        if total_income > threshold:
            rate = r
    return min(rate, NEW_REGIME_SURCHARGE_CAP) if regime == "new" else rate


def _regime(inc: IndividualIncome, regime: str) -> dict:
    notes: list[str] = []
    std = min(inc.salary, STANDARD_DEDUCTION[regime])
    salary_income = inc.salary - std
    hp = inc.house_property
    if hp < 0:
        if regime == "new":
            notes.append("New regime: a house-property loss cannot be set off against other income (s.115BAC(2)); it is ignored here.")
            hp = 0.0
        elif -hp > HP_LOSS_SETOFF_CAP:
            notes.append("Old regime: house-property loss set off against other income is limited to ₹2 lakh (s.71(3A)); the rest is carried forward.")
            hp = -HP_LOSS_SETOFF_CAP
    gross_normal = max(0.0, salary_income + hp + inc.business + inc.other_sources)

    deductions: dict[str, float] = {}
    if regime == "old":
        d = {k: _nn(f"Deduction {k}", v) for k, v in (inc.deductions_old or {}).items()}
        for k, cap in CAPS_OLD.items():
            if k in d and d[k] > cap:
                notes.append(f"Section {k} is limited to ₹{cap:,.0f}.")
                d[k] = cap
        if inc.age != "below_60" and inc.resident:
            if "80TTA" in d:
                notes.append("Senior citizens claim interest under 80TTB, not 80TTA.")
                d.pop("80TTA")
        elif "80TTB" in d:
            notes.append("80TTB is only for resident senior citizens.")
            d.pop("80TTB")
        deductions.update(d)
    else:
        if inc.deductions_old:
            notes.append("New regime: Chapter VI-A deductions such as 80C, 80D and 80TTA are not allowed (only 80CCD(2) and a few others).")
    if inc.employer_nps_80ccd2:
        deductions["80CCD(2)"] = _nn("Employer NPS contribution", inc.employer_nps_80ccd2)
    claimed = sum(deductions.values())
    allowed = min(claimed, gross_normal)  # Chapter VI-A deductions cannot exceed the slab-rate income
    if claimed > allowed:
        notes.append("Deductions are limited to the income taxed at slab rates; they cannot reduce special-rate income.")
    normal_income = gross_normal - allowed

    special_income = inc.stcg_111a + inc.ltcg_112a + inc.ltcg_112 + inc.winnings_115bb
    total_income = round10(normal_income + special_income)

    if regime == "new":
        slabs = NEW_SLABS
        exemption = NEW_SLABS[0][0]
    else:
        exemption = OLD_EXEMPTION[inc.age] if (inc.taxpayer_type == "individual" and inc.resident) else OLD_EXEMPTION["below_60"]
        if inc.age != "below_60" and not (inc.taxpayer_type == "individual" and inc.resident):
            notes.append("The higher exemption limit for senior citizens applies only to resident individuals.")
        slabs = old_slabs(exemption)
    normal_tax, slab_rows = slab_tax(normal_income, slabs)
    special, _ = _special_taxes(inc, max(0.0, exemption - normal_income))
    special_tax = sum(r["tax"] for r in special.values())

    # 87A rebate (resident individuals only)
    rebate = 0.0
    limit, max_rebate = REBATE[regime]
    if inc.taxpayer_type == "individual" and inc.resident:
        if regime == "new":
            test_income = total_income if inc.count_special_income_for_rebate else normal_income
            if test_income <= limit:
                rebate = min(normal_tax, max_rebate)
            elif normal_tax > test_income - limit:
                rebate = normal_tax - (test_income - limit)  # marginal relief: tax limited to income above ₹12 lakh
                notes.append("Marginal relief under 87A: tax on slab income is limited to the income above ₹12 lakh.")
        else:
            if total_income <= limit:
                rebate = min(normal_tax + special["111A"]["tax"] + special["112"]["tax"], max_rebate)  # not against 112A (s.112A(6))
    tax_after_rebate = max(0.0, normal_tax + special_tax - rebate)

    # surcharge (on tax after rebate); 15% cap on 111A / 112 / 112A tax; marginal relief at each threshold
    def tax_and_surcharge(norm_inc: float, specials: dict, total: float) -> float:
        n_tax, _ = slab_tax(norm_inc, slabs)
        sp_capped = specials["111A"]["tax"] + specials["112"]["tax"] + specials["112A"]["tax"]
        other = n_tax + specials["115BB"]["tax"]
        rate = _surcharge_rate(total, regime)
        return other * (1 + rate) + sp_capped * (1 + min(rate, SPECIAL_SURCHARGE_CAP))

    rate = _surcharge_rate(total_income, regime)
    capped_part = special["111A"]["tax"] + special["112"]["tax"] + special["112A"]["tax"]
    surcharge = 0.0
    marginal_relief = 0.0
    if rate > 0:
        other_part = max(0.0, tax_after_rebate - capped_part)
        surcharge = other_part * rate + min(capped_part, tax_after_rebate) * min(rate, SPECIAL_SURCHARGE_CAP)
        threshold = max(t for t, r in SURCHARGE_INDIVIDUAL if total_income > t)
        excess = total_income - threshold
        reduced = IndividualIncome(**asdict(inc))
        cut_normal = min(excess, normal_income)
        rest = excess - cut_normal
        for key in ("winnings_115bb", "ltcg_112", "ltcg_112a", "stcg_111a"):
            take = min(rest, getattr(reduced, key))
            setattr(reduced, key, getattr(reduced, key) - take)
            rest -= take
        sp_at_threshold, _ = _special_taxes(reduced, max(0.0, exemption - (normal_income - cut_normal)))
        at_threshold = tax_and_surcharge(normal_income - cut_normal, sp_at_threshold, threshold)
        limit_total = at_threshold + excess
        if tax_after_rebate + surcharge > limit_total:
            marginal_relief = tax_after_rebate + surcharge - limit_total
            surcharge -= marginal_relief
            notes.append(f"Marginal relief on surcharge: tax plus surcharge cannot exceed the tax at ₹{threshold:,.0f} plus the income above it.")
    cess = (tax_after_rebate + surcharge) * CESS
    total_tax = round10(tax_after_rebate + surcharge + cess)
    paid = _nn("TDS and advance tax", inc.tds_and_advance_tax)
    return {
        "regime": regime, "standard_deduction": std, "gross_slab_income": gross_normal, "deductions": deductions,
        "deductions_allowed": allowed, "slab_income": normal_income, "special_income": special_income, "total_income": total_income,
        "slab_rows": slab_rows, "slab_tax": normal_tax, "special_rate_tax": special, "rebate_87a": rebate,
        "tax_after_rebate": tax_after_rebate, "surcharge_rate": rate, "surcharge": surcharge, "marginal_relief": marginal_relief,
        "cess": cess, "total_tax": total_tax, "tds_and_advance_tax": paid, "balance": total_tax - paid,
        "effective_rate": total_tax / total_income if total_income else None, "notes": notes,
    }


def individual_tax(inc: IndividualIncome) -> dict:
    if inc.taxpayer_type not in ("individual", "huf"):
        raise FinanceInputError("This calculator is for individuals and HUFs; use the entity calculator for firms and companies.")
    if inc.age not in OLD_EXEMPTION:
        raise FinanceInputError("Age must be below_60, 60_to_79 or 80_plus.")
    for name in ("salary", "business", "other_sources", "stcg_111a", "ltcg_112a", "ltcg_112", "winnings_115bb"):
        _nn(name.replace("_", " ").capitalize(), getattr(inc, name))
    if not math.isfinite(inc.house_property):
        raise FinanceInputError("House property income must be a number.")
    new, old = _regime(inc, "new"), _regime(inc, "old")
    better = "new" if new["total_tax"] <= old["total_tax"] else "old"
    return {
        "year": YEAR, "new": new, "old": old, "better_regime": better, "saving": abs(new["total_tax"] - old["total_tax"]),
        "rebate_note": REBATE_NOTE,
        "notes": [
            "The new regime is the default; to choose the old regime a salaried person states it in the return, while a person "
            "with business income files Form 10-IEA by the due date.",
            "Dividends are taxed at slab rates; their 15% surcharge cap is not modelled, so surcharge may be slightly overstated at high incomes.",
            "Interest under sections 234A/B/C and losses carried forward are not included.",
        ],
        "sources": {k: SOURCES[k] for k in ("rates", "rebate_old", "capital_gains")},
    }


# ---------------------------------------------------------------- firms, companies, co-operatives
def _surcharge_with_relief(income: float, tax_fn, tiers: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Generic surcharge with marginal relief: returns (rate, surcharge, relief, base tax)."""
    base = tax_fn(income)
    rate = 0.0
    threshold = None
    for t, r in tiers:
        if income > t:
            rate, threshold = r, t
    if rate == 0:
        return 0.0, 0.0, 0.0, base
    surcharge = base * rate
    lower_rate = max([r for t, r in tiers if t < threshold], default=0.0)
    limit = tax_fn(threshold) * (1 + lower_rate) + (income - threshold)
    relief = max(0.0, base + surcharge - limit)
    return rate, surcharge - relief, relief, base


@dataclass
class EntityIncome:
    entity: str = "company"  # company | firm | llp | cooperative
    total_income: float = 0.0
    turnover_fy_2023_24: float | None = None  # companies: decides 25% vs 30%
    book_profit: float | None = None  # companies: MAT under section 115JB
    total_income_115baa: float | None = None  # if different (115BAA disallows some deductions)
    manufacturing_115bab_eligible: bool = False
    adjusted_total_income_amt: float | None = None  # co-operatives: AMT


def entity_tax(e: EntityIncome) -> dict:
    ti = _nn("Total income", e.total_income)
    options: list[dict] = []
    notes: list[str] = []

    def option(code: str, label: str, base_tax: float, rate: float, surcharge: float, relief: float, extra: dict | None = None) -> dict:
        cess = (base_tax + surcharge) * CESS
        total = round10(base_tax + surcharge + cess)
        return {"code": code, "label": label, "tax": base_tax, "surcharge_rate": rate, "surcharge": surcharge, "marginal_relief": relief,
                "cess": cess, "total_tax": total, "effective_rate": total / ti if ti else None, **(extra or {})}

    if e.entity in ("firm", "llp"):
        rate, sc, relief, base = _surcharge_with_relief(ti, lambda x: x * 0.30, [(1 * CRORE, 0.12)])
        options.append(option("normal", "Firm / LLP at 30%", base, rate, sc, relief))
        if e.entity == "llp":
            notes.append("An LLP claiming certain deductions may owe alternate minimum tax (18.5% under section 115JC); not modelled.")
    elif e.entity == "company":
        if e.turnover_fy_2023_24 is None:
            raise FinanceInputError("Enter the company's turnover or gross receipts for FY 2023-24 (it decides the 25% or 30% rate).")
        normal_rate = 0.25 if _nn("Turnover", e.turnover_fy_2023_24) <= 400 * CRORE else 0.30
        tiers = [(1 * CRORE, 0.07), (10 * CRORE, 0.12)]
        rate, sc, relief, base = _surcharge_with_relief(ti, lambda x: x * normal_rate, tiers)
        normal = option("normal", f"Normal provisions at {normal_rate:.0%}", base, rate, sc, relief)
        if e.book_profit is not None:
            bp = _nn("Book profit", e.book_profit)
            mrate, msc, mrelief, mbase = _surcharge_with_relief(bp, lambda x: x * 0.15, tiers)
            mat_total = round10((mbase + msc) * (1 + CESS))
            normal["mat"] = {"book_profit": bp, "tax": mbase, "surcharge": msc, "marginal_relief": mrelief, "total": mat_total}
            if mat_total > normal["total_tax"]:
                normal["mat_credit"] = mat_total - normal["total_tax"]
                normal["total_tax"] = mat_total
                normal["effective_rate"] = mat_total / ti if ti else None
                normal["label"] += " (MAT applies: 15% of book profit is higher)"
        options.append(normal)
        ti_baa = ti if e.total_income_115baa is None else _nn("Total income under 115BAA", e.total_income_115baa)
        base = ti_baa * 0.22
        options.append(option("115BAA", "Section 115BAA at 22% (no MAT)", base, 0.10, base * 0.10, 0.0, {"total_income": ti_baa}))
        if e.manufacturing_115bab_eligible:
            base = ti_baa * 0.15
            options.append(option("115BAB", "Section 115BAB at 15% (new manufacturing company, no MAT)", base, 0.10, base * 0.10, 0.0,
                                  {"total_income": ti_baa}))
        notes += ["115BAA / 115BAB carry a flat 10% surcharge at any income and are irrevocable once opted (Form 10-IC / 10-ID).",
                  "Under 115BAA / 115BAB certain deductions and incentives are not allowed, so enter the income computed without them.",
                  "115BAB applies only to companies set up on or after 1 Oct 2019 that began manufacturing by 31 Mar 2024; it taxes "
                  "only manufacturing income at 15%."]
    elif e.entity == "cooperative":
        def coop(x: float) -> float:
            return slab_tax(x, [(10_000, 0.10), (20_000, 0.20), (INF, 0.30)])[0]
        rate, sc, relief, base = _surcharge_with_relief(ti, coop, [(1 * CRORE, 0.07), (10 * CRORE, 0.12)])
        normal = option("normal", "Normal slabs (10% / 20% / 30%)", base, rate, sc, relief)
        if e.adjusted_total_income_amt is not None:
            ati = _nn("Adjusted total income", e.adjusted_total_income_amt)
            amt = round10(ati * 0.15 * (1 + CESS))
            normal["amt"] = {"adjusted_total_income": ati, "total": amt}
            if amt > normal["total_tax"]:
                normal["total_tax"] = amt
                normal["label"] += " (AMT at 15% is higher)"
        options.append(normal)
        base = ti * 0.22
        options.append(option("115BAD", "Section 115BAD at 22% (no AMT)", base, 0.10, base * 0.10, 0.0))
        notes.append("Co-operative surcharge tiers (7% above ₹1 crore, 12% above ₹10 crore) should be checked against the Finance Act text.")
    else:
        raise FinanceInputError("Entity must be company, firm, llp or cooperative.")
    best = min(options, key=lambda o: o["total_tax"])
    return {"year": YEAR, "entity": e.entity, "options": options, "lowest": best["code"], "notes": notes, "source": SOURCES["rates"]}


# ---------------------------------------------------------------- due dates, 234F fee, 234A interest
DUE_DATES = {
    "no_business": {"date": dt.date(2026, 7, 31), "label": "Individuals / HUFs without business income, accounts not audited"},
    "business_no_audit": {"date": dt.date(2026, 8, 31), "label": "Business or profession, accounts not audited (new category, Finance Act 2026)"},
    "audit": {"date": dt.date(2026, 11, 21), "statutory": dt.date(2026, 10, 31),
              "label": "Companies and taxpayers whose accounts are audited (extended by CBDT Circular 07/2026)"},
    "transfer_pricing": {"date": dt.date(2026, 11, 30), "label": "Taxpayers who must file a transfer-pricing report (Form 3CEB)"},
}
BELATED_LAST = dt.date(2026, 12, 31)
REVISED_LAST = dt.date(2027, 3, 31)


def _months_or_part(start: dt.date, end: dt.date) -> int:
    """Interest runs for each month or part of a month (1% simple)."""
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day >= start.day:
        months += 1
    return max(months, 1)


def due_dates(category: str | None = None, filing_date: dt.date | None = None, total_income: float | None = None,
              tax_unpaid: float | None = None) -> dict:
    rows = [{"category": k, "label": v["label"], "due_date": v["date"].isoformat(),
             "statutory_due_date": v.get("statutory", v["date"]).isoformat()} for k, v in DUE_DATES.items()]
    out = {"year": YEAR, "due_dates": rows, "belated_return_last_date": BELATED_LAST.isoformat(),
           "revised_return_last_date": REVISED_LAST.isoformat(),
           "updated_return": "ITR-U can be filed within 48 months from the end of the assessment year, with additional tax of 25% to 70% of tax and interest.",
           "notes": ["Revising a return more than 9 months after the year ends attracts a fee under section 234-I (₹1,000 if income up to ₹5 lakh, else ₹5,000).",
                     "Tax audit report (Form 3CA/3CB-3CD) for AY 2026-27 was due 21 Oct 2026 under Circular 07/2026."],
           "sources": {k: SOURCES[k] for k in ("due_dates", "circular_7_2026", "fee_234f", "interest")}}
    if category is not None and filing_date is not None:
        if category not in DUE_DATES:
            raise FinanceInputError("Unknown due-date category.")
        due = DUE_DATES[category]["date"]
        late = filing_date > due
        fee = 0.0
        if late:
            if total_income is None:
                raise FinanceInputError("Enter total income to work out the late fee.")
            # no fee for someone not required to file (income below the basic exemption limit)
            fee = 0.0 if total_income <= 2.5 * LAKH else 1_000.0 if total_income <= 5 * LAKH else 5_000.0
        interest = 0.0
        months = 0
        if late and tax_unpaid:
            months = _months_or_part(due + dt.timedelta(days=1), filing_date)
            interest = _nn("Unpaid tax", tax_unpaid) * 0.01 * months
        out["late_filing"] = {
            "due_date": due.isoformat(), "filing_date": filing_date.isoformat(), "late": late,
            "fee_234f": fee, "interest_234a": interest, "interest_months": months,
            "allowed": filing_date <= BELATED_LAST,
            "message": ("Filed on time." if not late else
                        "Late: a belated return under section 139(4) is allowed until 31 Dec 2026." if filing_date <= BELATED_LAST else
                        "After 31 Dec 2026 a belated return is no longer possible; only an updated return (ITR-U) can be filed."),
        }
    return out


FILING_STEPS = [
    "Download the pre-filled data (Form 26AS, AIS and TIS) from the e-filing portal and match it with this computation.",
    "Open the portal (e-File → Income Tax Returns → File Income Tax Return), choose AY 2026-27, the form and 'Online', "
    "or use the Common Offline Utility and upload its JSON.",
    "Enter the figures from this computation, pay any balance tax with Challan 280 (e-Pay Tax), and add the challan details.",
    "Submit and e-verify within 30 days (Aadhaar OTP, net banking, bank/demat EVC, or a signed ITR-V by post).",
]
