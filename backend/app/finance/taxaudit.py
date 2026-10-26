"""Tax audit under section 44AB for FY 2025-26 (AY 2026-27), Income-tax Act, 1961.

What it does:
  * applicability  whether a tax audit is required, under which clause of s.44AB, with each test shown
  * report_form    Form 3CA (accounts already audited under another law) or 3CB, each with Form 3CD
  * draft_3cb      the Form 3CB wording with the assessee's details; the auditor's fields stay blank
  * clauses_3cd    every Form 3CD clause (as amended by Notification 23/2025 from 1 April 2025) marked
                   "filled from your files", "review" or "needs input", each with its working and source
  * ledger_checks  cash tests on a cash book / ledger: s.40A(3) (clause 21(d)), s.269SS/269ST/269T
                   (clause 31), the 5% cash test of s.44AB(a), GST break-up of expenses (clause 44)

It prepares a draft for a chartered accountant. Only a CA in practice can sign a tax audit report
and upload it (with a UDIN) on the e-filing portal; the auditor's name, membership number, firm
registration number and UDIN are never filled in. Missing inputs stay missing, never zero.

From 1 April 2026 the Income-tax Act, 2025 replaces s.44AB with s.63 (audit report in Form 26) for
tax year 2026-27 onwards; FY 2025-26 is still audited under the 1961 Act.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass

from . import FinanceInputError
from .incometax import CRORE, LAKH, basic_exemption

YEAR = {"financial_year": "2025-26", "assessment_year": "2026-27", "previous_year": "01-04-2025 to 31-03-2026",
        "law": "Income-tax Act, 1961"}
RULESET = {"id": "IN-44AB-AY2026-27", "version": "2026.10.1", "rules_checked_on": "2026-10-26"}
REPORT_DUE = dt.date(2026, 10, 21)     # CBDT Circular 07/2026 (was 30 Sep 2026)
ITR_DUE = dt.date(2026, 11, 21)        # CBDT Circular 07/2026 (was 31 Oct 2026)
PENALTY_271B_CAP = 150_000.0

SOURCES = {
    "s44ab": "https://www.incometaxindia.gov.in/w/section-44ab-43",
    "s44ad": "https://www.incometaxindia.gov.in/w/tax-on-presumptive-basis-in-case-of-certain-businesses",
    "form_3cd_changes": "https://www.taxmann.com/post/blog/govt-amends-form-3cd-new-clause-36b-inserted-to-report-sum-received-for-buyback-of-shares",
    "circular_7_2026": "https://incometaxindia.gov.in/documents/d/guest/circular-7-2026-pdf",
    "cash_limits": "https://www.incometaxindia.gov.in/w/prohibited-transaction-in-cash/limit-on-cash-transactions%E2%80%8B",
    "s269st": "https://www.incometaxindia.gov.in/w/section-269st",
    "s271b": "https://www.incometaxindia.gov.in/w/section-271b-24",
    "penalties": "https://www.incometaxindia.gov.in/w/penalties-under-the-income-tax-law",
}

PRESUMPTIVE = ("none", "44AD", "44ADA", "44AE", "44BB", "44BBB")
TYPES = ("individual", "huf", "firm", "llp", "company", "aop_boi", "cooperative", "local_authority", "trust_or_institution")


@dataclass
class AuditProfile:
    taxpayer_type: str = "individual"
    activity: str = "business"                       # business | profession | both
    business_turnover: float | None = None           # total sales, turnover or gross receipts of the business
    professional_receipts: float | None = None       # gross receipts of the profession
    cash_receipts: float | None = None               # all amounts received in cash (incl. non-account-payee cheques/drafts)
    total_receipts: float | None = None
    cash_payments: float | None = None
    total_payments: float | None = None
    presumptive: str = "none"
    profit_below_presumptive: bool = False           # profit declared lower than the presumptive rate
    opted_out_of_44ad: bool = False                  # s.44AD(4): left 44AD within five years of opting in
    total_income: float | None = None
    regime: str = "new"
    age: str = "below_60"
    resident: bool = True
    audited_under_other_law: bool | None = None      # e.g. Companies Act; None = assume yes for a company
    turnover_source: str | None = None
    cash_source: str | None = None


def _pct(part: float, whole: float) -> float:
    return part / whole * 100


def _inr(v: float) -> str:
    """Indian grouping: 12,34,56,789."""
    neg, v = v < 0, abs(round(v))
    s = str(int(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"{'-' if neg else ''}₹{s}"


def max_not_chargeable(p: AuditProfile) -> float:
    """'Maximum amount which is not chargeable to income-tax': the basic exemption for individuals and
    HUFs (by regime and age); nil for firms, LLPs and companies, which are taxed from the first rupee."""
    if p.taxpayer_type == "individual":
        return basic_exemption(p.regime, p.age, p.resident)
    if p.taxpayer_type == "huf":
        return basic_exemption(p.regime, "below_60", True)
    return 0.0


def applicability(p: AuditProfile) -> dict:
    if p.taxpayer_type not in TYPES:
        raise FinanceInputError("Unknown taxpayer type.")
    if p.activity not in ("business", "profession", "both"):
        raise FinanceInputError("Activity must be business, profession or both.")
    if p.presumptive not in PRESUMPTIVE:
        raise FinanceInputError("Unknown presumptive scheme.")
    for name in ("business_turnover", "professional_receipts", "cash_receipts", "total_receipts", "cash_payments", "total_payments"):
        v = getattr(p, name)
        if v is not None and v < 0:
            raise FinanceInputError(f"{name.replace('_', ' ').capitalize()} cannot be negative.")
    if p.cash_receipts is not None and p.total_receipts is not None and p.cash_receipts > p.total_receipts:
        raise FinanceInputError("Cash receipts cannot exceed total receipts.")
    if p.cash_payments is not None and p.total_payments is not None and p.cash_payments > p.total_payments:
        raise FinanceInputError("Cash payments cannot exceed total payments.")

    tests: list[dict] = []
    missing: list[str] = []
    limit_nc = max_not_chargeable(p)

    def add(clause: str, rule: str, working: str, result: bool | None, source: str = "s44ab"):
        tests.append({"clause": clause, "rule": rule, "working": working, "result": result, "source": SOURCES[source]})

    rp = pp = None
    if p.cash_receipts is not None and p.total_receipts:
        rp = _pct(p.cash_receipts, p.total_receipts)
    if p.cash_payments is not None and p.total_payments:
        pp = _pct(p.cash_payments, p.total_payments)

    # ---- 44AB(a): business
    if p.activity in ("business", "both"):
        t = p.business_turnover
        rule = ("Business turnover above ₹1 crore needs an audit; the limit is ₹10 crore when cash receipts and cash payments "
                "are each no more than 5% of the totals. A 44AD case within the 44AD limit is exempt (first proviso).")
        if t is None:
            missing.append("business_turnover")
            add("44AB(a)", rule, "Business turnover is not known yet.", None)
        else:
            src = f" (from {p.turnover_source})" if p.turnover_source else ""
            res: bool | None
            work = [f"Turnover {_inr(t)}{src}."]
            cash_ok = None if rp is None or pp is None else (rp <= 5 and pp <= 5)
            if rp is not None or pp is not None:
                work.append(f"Cash receipts {rp:.2f}% of receipts" if rp is not None else "Cash receipts share not known")
                work[-1] += f"; cash payments {pp:.2f}% of payments." if pp is not None else "; cash payments share not known."
            in_44ad = False
            if p.presumptive == "44AD" and not p.profit_below_presumptive:
                eligible = p.taxpayer_type in ("individual", "huf", "firm") and p.resident
                limit44 = 3 * CRORE if rp is not None and rp <= 5 else 2 * CRORE
                if not eligible:
                    work.append("44AD is only for resident individuals, HUFs and partnership firms (not LLPs), so the proviso does not apply.")
                elif t <= limit44:
                    in_44ad = True
                    work.append(f"Profit declared under 44AD and turnover is within the 44AD limit of {_inr(limit44)}: no audit under clause (a).")
                else:
                    work.append(f"Turnover is above the 44AD limit of {_inr(limit44)}, so 44AD is not available.")
            if in_44ad:
                res = False
            elif t <= 1 * CRORE:
                res = False
                work.append("Not above ₹1 crore: no audit under clause (a).")
            elif t > 10 * CRORE:
                res = True
                work.append("Above ₹10 crore: audit required whatever the cash share.")
            elif cash_ok is None:
                res = None
                missing += [k for k, v in (("cash_receipts", p.cash_receipts), ("total_receipts", p.total_receipts),
                                           ("cash_payments", p.cash_payments), ("total_payments", p.total_payments)) if v is None]
                work.append("Between ₹1 crore and ₹10 crore: the answer depends on the 5% cash test. Upload a cash book / ledger "
                            "with a payment-mode column, or enter cash and total receipts and payments.")
            elif cash_ok:
                res = False
                work.append("Both cash shares are 5% or less, so the limit is ₹10 crore: no audit under clause (a).")
            else:
                res = True
                work.append("A cash share is above 5%, so the limit stays ₹1 crore: audit required.")
            if p.cash_source and (rp is not None or pp is not None):
                work.append(f"Cash figures from {p.cash_source}.")
            add("44AB(a)", rule, " ".join(work), res)

    # ---- 44AB(b): profession
    if p.activity in ("profession", "both"):
        r = p.professional_receipts
        rule = "Gross receipts of a profession above ₹50 lakh need an audit. (₹75 lakh is the 44ADA eligibility limit, not the audit limit.)"
        if r is None:
            missing.append("professional_receipts")
            add("44AB(b)", rule, "Professional receipts are not known yet.", None)
        else:
            src = f" (from {p.turnover_source})" if p.turnover_source and p.activity == "profession" else ""
            add("44AB(b)", rule, f"Gross receipts {_inr(r)}{src} {'exceed' if r > 50 * LAKH else 'do not exceed'} ₹50 lakh.", r > 50 * LAKH)

    def above_nc(clause: str, rule: str, cond_text: str) -> None:
        if p.total_income is None:
            missing.append("total_income")
            add(clause, rule, f"{cond_text} Total income is needed to compare with the exemption limit of {_inr(limit_nc)}.", None)
        else:
            over = p.total_income > limit_nc
            add(clause, rule, f"{cond_text} Total income {_inr(p.total_income)} is {'above' if over else 'not above'} the "
                              f"maximum amount not chargeable to tax ({_inr(limit_nc)}).", over)

    # ---- 44AB(c): 44AE / 44BB / 44BBB with lower profits
    if p.presumptive in ("44AE", "44BB", "44BBB"):
        add("44AB(c)", f"Claiming profits lower than the deemed profits under section {p.presumptive} needs an audit.",
            "Profit declared is lower than the presumptive amount." if p.profit_below_presumptive else
            "Profit declared is not lower than the presumptive amount.", p.profit_below_presumptive)

    # ---- 44AB(d): 44ADA with lower profits and income above the exemption limit
    if p.presumptive == "44ADA":
        rule = "Under 44ADA, declaring profit below 50% of receipts with total income above the exemption limit needs an audit."
        if p.profit_below_presumptive:
            above_nc("44AB(d)", rule, "Profit declared is below 50% of gross receipts.")
        else:
            add("44AB(d)", rule, "Profit declared is at least 50% of gross receipts.", False)

    # ---- 44AB(e): 44AD(4) cases
    if p.opted_out_of_44ad:
        above_nc("44AB(e)", "Someone who left 44AD within five years of opting in (s.44AD(4)) needs an audit when total income "
                            "exceeds the exemption limit (s.44AD(5)).", "Section 44AD(4) applies.")
    elif p.presumptive == "44AD" and p.profit_below_presumptive:
        tests.append({"clause": "44AB(e)", "rule": "Declaring profit below 6% / 8% under 44AD triggers an audit only through s.44AD(4).",
                      "working": "Lower profit alone does not trigger clause (e) unless 44AD(4) applies (you left 44AD in one of the "
                                 "last five years). Tick that box if it does. Clause (a) is still tested on turnover above.",
                      "result": False, "source": SOURCES["s44ad"]})

    decided = [t["result"] for t in tests]
    required = True if any(r is True for r in decided) else None if any(r is None for r in decided) else False
    clauses = [t["clause"] for t in tests if t["result"] is True]
    other_law = p.audited_under_other_law if p.audited_under_other_law is not None else p.taxpayer_type in ("company",)
    form = None
    if required:
        form = "3CA" if other_law else "3CB"
    gross = (p.business_turnover or 0) + (p.professional_receipts or 0)
    penalty = min(0.005 * gross, PENALTY_271B_CAP) if required and gross else None
    return {
        "required": required, "clauses": clauses, "tests": tests, "missing": list(dict.fromkeys(missing)),
        "form": form, "forms": f"Form {form} + Form 3CD" if form else None,
        "form_reason": None if not form else (
            "Form 3CA: the accounts are already audited under another law (for a company, the Companies Act, 2013)." if form == "3CA"
            else "Form 3CB: the accounts are not audited under any other law."),
        "max_not_chargeable": limit_nc,
        "penalty_271b": penalty,
        "penalty_note": ("Section 271B: 0.5% of turnover or gross receipts, at most ₹1,50,000, if the audit is not done or the report "
                         "is not furnished by the due date. Section 273B waives it for a reasonable cause."),
    }


def due(today: dt.date) -> dict:
    late = today > REPORT_DUE
    return {"report_due": REPORT_DUE.isoformat(), "itr_due": ITR_DUE.isoformat(), "report_overdue": late,
            "days_to_itr_due": (ITR_DUE - today).days,
            "message": ("The tax audit report for AY 2026-27 was due on 21 Oct 2026 (CBDT Circular 07/2026). It is now late: upload it "
                        "as soon as possible to limit the s.271B exposure. The return is due 21 Nov 2026."
                        if late else
                        "Tax audit report due 21 Oct 2026 and the return 21 Nov 2026 (CBDT Circular 07/2026)."),
            "source": SOURCES["circular_7_2026"]}


# ---------------------------------------------------------------- ledger checks
CONTRA = re.compile(r"\bcontra\b|cash (deposited|withdrawn)|deposited (in|into|to) bank|withdrawn from bank|\bself\b|atm\b|cash withdrawal", re.I)
LOAN = re.compile(r"\bloans?\b|\bdeposits?\b|unsecured|borrow|advance (against|for) (property|land|building|flat)|property advance", re.I)
REPAY = re.compile(r"repa(id|y|yment)|refund of (loan|deposit)|returned", re.I)
NOT_EXPENSE = re.compile(r"\bloans?\b|\bdeposits?\b|unsecured|borrow|capital|drawings?|\bbank\b|investment|advance tax|"
                         r"income[- ]?tax|tds|tcs|gst (paid|payment)|challan", re.I)
TRANSPORT = re.compile(r"goods carriage|lorry|truck|tempo|transport|freight|cartage|carriage", re.I)
RULE_21A = [("Penalty or fine", re.compile(r"penalt|\bfines?\b|late fee|compounding|settlement of (contravention|proceeding)", re.I)),
            ("Donation", re.compile(r"donation|charity", re.I)),
            ("Personal expense", re.compile(r"personal|household|drawings", re.I)),
            ("Club expense", re.compile(r"\bclub\b", re.I)),
            ("Advertisement in a souvenir / brochure of a political party", re.compile(r"souvenir|political", re.I)),
            ("CSR expenditure (s.37 Explanation 2)", re.compile(r"\bcsr\b|corporate social", re.I))]


def _text(r: dict) -> str:
    return f"{r.get('account', '')} {r.get('narration', '')} {r.get('party', '')}"


def ledger_checks(rows: list[dict], file: str) -> dict:
    """Cash checks on transaction rows (from files.ledger.read_ledger). Every flagged item keeps its file and cell."""
    out: dict = {"file": file, "rows": len(rows)}
    usable = [r for r in rows if not CONTRA.search(_text(r))]
    out["contra_excluded"] = len(rows) - len(usable)
    known = [r for r in usable if r["cash"] is not None]
    out["mode_known"] = len(known)
    if not known:
        out["cash_known"] = False
        return out
    out["cash_known"] = True
    all_modes = all(r["cash"] is not None for r in usable) and any(r["cash"] is False for r in usable)

    def ref(r: dict) -> dict:
        return {"file": file, "where": r["ref"], "date": r["date"], "party": r["party"], "account": r["account"],
                "narration": r["narration"][:120]}

    cash_r = sum(r["receipt"] for r in known if r["cash"])
    cash_p = sum(r["payment"] for r in known if r["cash"])
    out["cash_receipts"], out["cash_payments"] = cash_r, cash_p
    if all_modes:
        out["total_receipts"] = sum(r["receipt"] for r in usable)
        out["total_payments"] = sum(r["payment"] for r in usable)
    out["totals_complete"] = all_modes

    # 40A(3): expenditure paid in cash to one person in one day above ₹10,000 (₹35,000 for goods carriages)
    day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in known:
        if r["cash"] and r["payment"] and not NOT_EXPENSE.search(_text(r)):
            day[(r["party"].lower() or r["account"].lower(), r["date"])].append(r)
    flagged_40a3 = []
    for (_, date), rs in day.items():
        total = sum(r["payment"] for r in rs)
        limit = 35_000 if any(TRANSPORT.search(_text(r)) for r in rs) else 10_000
        if total > limit:
            flagged_40a3.append({**ref(rs[0]), "amount": total, "limit": limit, "entries": len(rs),
                                 "refs": [r["ref"] for r in rs],
                                 "working": f"{' + '.join(_inr(r['payment']) for r in rs)} = {_inr(total)} in cash on {date} > {_inr(limit)}"})
    out["s40a3"] = sorted(flagged_40a3, key=lambda x: (x["date"], x["party"]))

    # 269SS: loans/deposits/property advances accepted in cash, ₹20,000 or more
    # 269T: such loans/deposits repaid in cash, ₹20,000 or more
    # 269ST: other cash receipts of ₹2 lakh or more from a person in a day
    ss, t_, st = [], [], []
    st_day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in known:
        if not r["cash"]:
            continue
        txt = _text(r)
        if r["receipt"] and LOAN.search(txt) and not REPAY.search(txt):
            if r["receipt"] >= 20_000:
                ss.append({**ref(r), "amount": r["receipt"], "working": f"{_inr(r['receipt'])} loan/deposit accepted in cash ≥ ₹20,000"})
        elif r["payment"] and LOAN.search(txt):
            if r["payment"] >= 20_000:
                t_.append({**ref(r), "amount": r["payment"], "working": f"{_inr(r['payment'])} loan/deposit repaid in cash ≥ ₹20,000"})
        elif r["receipt"]:
            st_day[(r["party"].lower() or r["account"].lower(), r["date"])].append(r)
    for (_, date), rs in st_day.items():
        total = sum(r["receipt"] for r in rs)
        if total >= 2 * LAKH:
            st.append({**ref(rs[0]), "amount": total, "entries": len(rs), "refs": [r["ref"] for r in rs],
                       "working": f"{' + '.join(_inr(r['receipt']) for r in rs)} = {_inr(total)} received in cash on {date} ≥ ₹2,00,000"})
    out["s269ss"], out["s269t"], out["s269st"] = ss, t_, st

    # Clause 21(a) heads for review
    heads = []
    for label, rx in RULE_21A:
        hits = [r for r in usable if r["payment"] and rx.search(_text(r))]
        if hits:
            heads.append({"head": label, "amount": sum(r["payment"] for r in hits), "entries": len(hits),
                          "refs": [r["ref"] for r in hits[:8]], "examples": [ref(r) for r in hits[:3]]})
    out["c21a"] = heads

    # Clause 44: expenses split by whether the payee's GSTIN is recorded
    if any(r["gstin"] for r in usable):
        exp = [r for r in usable if r["payment"] and not NOT_EXPENSE.search(_text(r))]
        reg = sum(r["payment"] for r in exp if re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]", r["gstin"]))
        out["c44"] = {"total": sum(r["payment"] for r in exp), "registered": reg, "unregistered": sum(r["payment"] for r in exp) - reg}
    return out


# ---------------------------------------------------------------- Form 3CB
def draft_3cb(entity: dict, form: str | None) -> dict:
    name = entity.get("name") or "[name of the assessee]"
    addr = entity.get("address") or "[address]"
    pan = entity.get("pan_masked") or "[PAN]"
    blank = "__________"
    paras = [
        f"1. I/We have examined the balance sheet as on 31 March 2026, and the profit and loss account for the period beginning from "
        f"1 April 2025 and ending on 31 March 2026, attached herewith, of {name}, {addr}, PAN {pan}.",
        f"2. I/We certify that the balance sheet and the profit and loss account are in agreement with the books of account maintained "
        f"at the head office at {blank} and {blank} branches.",
        "3. (a) I/We report the following observations / comments / discrepancies / inconsistencies, if any: [to be completed by the auditor]",
        "3. (b) Subject to the above — (A) I/We have obtained all the information and explanations which, to the best of my/our "
        "knowledge and belief, were necessary for the purpose of the audit. (B) In my/our opinion, proper books of account have been "
        "kept by the head office and branches of the assessee so far as appears from my/our examination of the books. (C) In my/our "
        "opinion and to the best of my/our information and according to the explanations given to me/us, the said accounts, read with "
        "notes thereon, if any, give a true and fair view: (i) in the case of the balance sheet, of the state of the affairs of the "
        "assessee as at 31 March 2026; and (ii) in the case of the profit and loss account, of the profit or loss of the assessee for "
        "the year ended on that date.",
        "4. The statement of particulars required to be furnished under section 44AB is annexed herewith in Form No. 3CD.",
        "5. In my/our opinion and to the best of my/our information and according to the explanations given to me/us, the particulars "
        "given in the said Form No. 3CD and the Annexure thereto are true and correct subject to the following observations / "
        "qualifications, if any: [to be completed by the auditor]",
    ]
    return {
        "title": "FORM NO. 3CB — Audit report under section 44AB of the Income-tax Act, 1961, in the case of a person referred to in "
                 "clause (b) of sub-rule (1) of rule 6G",
        "applies": form == "3CB",
        "note": ("This person's accounts are audited under another law, so the report is Form 3CA, not 3CB. The 3CB text is shown for "
                 "reference; Form 3CD below applies to both." if form == "3CA" else
                 "Draft wording for the auditor. The final report is filed on the e-filing portal by the chartered accountant."),
        "paragraphs": paras,
        "auditor_fields": ["Place", "Date", "Name of the signatory", "Membership number", "Firm registration number",
                           "Address of the auditor", "UDIN"],
        "auditor_note": "Left blank on purpose: only the chartered accountant who signs the report can fill these.",
    }


# ---------------------------------------------------------------- Form 3CD
# (number, part, short title, what is needed to complete it). Titles are plain-English summaries;
# the auditor uses the official wording in the e-filing utility.
CLAUSES: list[tuple[str, str, str, str]] = [
    ("1", "A", "Name of the assessee", "Name as per PAN"),
    ("2", "A", "Address", "Registered / business address"),
    ("3", "A", "Permanent Account Number (PAN) / Aadhaar", "PAN"),
    ("4", "A", "Liable to pay indirect tax (GST, customs…)? Registration numbers", "GSTIN and other registrations"),
    ("5", "A", "Status", "Individual, HUF, firm, LLP, company…"),
    ("6", "A", "Previous year", "Fixed"),
    ("7", "A", "Assessment year", "Fixed"),
    ("8", "A", "Relevant clause of section 44AB under which the audit is done", "From the applicability test"),
    ("8a", "A", "Opted for taxation under section 115BA / 115BAA / 115BAB / 115BAC / 115BAD / 115BAE?", "Regime chosen and the year it was opted"),
    ("9", "B", "Partners / members, profit-sharing ratios and changes (firms, LLPs, AOPs)", "Partnership deed or LLP agreement"),
    ("10", "B", "Nature of business or profession, and any change", "Description of the business"),
    ("11", "B", "Books of account prescribed under s.44AA, books kept and books examined, where kept", "List of books and their location"),
    ("12", "B", "Profits included on a presumptive basis (44AD, 44ADA, 44AE, 44B, 44BB, 44BBA, 44BBB, 44BBC…)", "Presumptive scheme and amount"),
    ("13", "B", "Method of accounting, changes, and ICDS adjustments and disclosures", "Accounting policies"),
    ("14", "B", "Method of valuing closing stock; deviation from s.145A", "Stock valuation policy"),
    ("15", "B", "Capital asset converted into stock-in-trade", "Details if any"),
    ("16", "B", "Amounts not credited to the profit and loss account", "Refunds, escalation claims, capital receipts…"),
    ("17", "B", "Land or building transferred below the stamp duty value (s.43CA / s.50C)", "Sale deeds and stamp duty values"),
    ("18", "B", "Depreciation allowable under the Income-tax Act (block-wise)", "Fixed asset register with additions, dates and deletions"),
    ("19", "B", "Amounts admissible under s.33AB, 33ABA, 35 and related sections (rows for 32AC, 32AD, 35AC, 35CCB removed from 1 Apr 2025)", "Details of claims"),
    ("20", "B", "(a) Bonus / commission to employees; (b) employees' PF/ESI contributions and dates paid (s.36(1)(va))", "Payroll and challans"),
    ("21", "B", "Amounts debited to P&L that are not allowable: (a) capital, personal, penalty, donation, club and similar items, "
                "including expenses to settle contraventions (new row from 1 Apr 2025); (b) s.40(a) TDS defaults; (c) s.40(b)/40(ba); "
                "(d) cash payments under s.40A(3)/(3A); (e)–(i) gratuity provision, non-approved funds, contingent liabilities, "
                "s.14A, s.36(1)(iii)", "General ledger"),
    ("22", "B", "MSME: interest not allowable under s.23 of the MSMED Act; amounts payable to micro and small enterprises paid within / "
                "beyond the s.15 time limit (s.43B(h)) — substituted from 1 Apr 2025", "Creditor list with Udyam status and payment dates"),
    ("23", "B", "Payments to related persons under s.40A(2)(b)", "List of related parties and payments"),
    ("24", "B", "Deemed profits and gains under s.33AB, 33ABA and related sections", "Details if any"),
    ("25", "B", "Profit chargeable under s.41 (remission or cessation of liability)", "Written-back liabilities"),
    ("26", "B", "Sums under s.43B(a)–(g): statutory dues, employer PF/ESI, bonus, interest to banks, leave encashment — paid or not "
                "by the due date of the return", "Payables at year end and the dates they were paid"),
    ("27", "B", "(a) GST input tax credit — treatment in the accounts; (b) prior-period income and expenses", "GST credit ledger"),
    ("28", "B", "Omitted from 1 Apr 2025 (shares received for inadequate consideration, s.56(2)(viia))", ""),
    ("29", "B", "Omitted from 1 Apr 2025 (share premium above fair value, s.56(2)(viib))", ""),
    ("29A", "B", "Advance received and forfeited (s.56(2)(ix))", "Details if any"),
    ("29B", "B", "Income under s.56(2)(x) (property received without or for inadequate consideration)", "Details if any"),
    ("30", "B", "Amounts borrowed or repaid on hundi otherwise than by account-payee cheque (s.69D)", "Details if any"),
    ("30A", "B", "Primary / secondary transfer-pricing adjustment (s.92CE)", "Details if any"),
    ("30B", "B", "Interest limitation on borrowings from non-residents (s.94B)", "Details if any"),
    ("30C", "B", "Impermissible avoidance arrangement (s.96)", "Details if any"),
    ("31", "B", "Loans, deposits and specified sums accepted or repaid, and receipts of ₹2 lakh or more, other than by account-payee "
                "cheque, draft or electronic mode (s.269SS, 269ST, 269T) — recast from 1 Apr 2025", "Cash book / ledger with payment mode"),
    ("32", "B", "Brought-forward losses and depreciation; change in shareholding (s.79); speculation loss (s.73)", "Previous returns and assessment orders"),
    ("33", "B", "Deductions under Chapter VI-A or Chapter III (s.10A, 10AA)", "Deduction workings"),
    ("34", "B", "TDS / TCS: deducted and paid correctly and in time, statements filed, interest under s.201(1A) / 206C(7)", "TDS returns (24Q, 26Q, 27Q), challans"),
    ("35", "B", "Quantitative details of principal goods traded, raw materials, finished goods and by-products", "Stock register"),
    ("36", "B", "Dividend distribution tax (s.115-O)", "Not applicable — dividend distribution tax was abolished from 1 April 2020"),
    ("36A", "B", "Deemed dividend under s.2(22)(e)", "Loans from closely held companies"),
    ("36B", "B", "Sums received on buy-back of shares (new from 1 Apr 2025)", "Details if any"),
    ("37", "B", "Cost audit carried out?", "Cost audit report"),
    ("38", "B", "Audit under the Central Excise Act?", "Details if any"),
    ("39", "B", "Audit of the value of taxable services (s.72A, Finance Act 1994)?", "Details if any"),
    ("40", "B", "Turnover, gross profit, net profit, stock-in-trade and material-consumed ratios — this year and last year", "P&L and balance sheet"),
    ("41", "B", "Demands raised and refunds issued under any tax law", "Orders and intimations received"),
    ("42", "B", "Statements in Form 61 / 61A / 61B furnished", "Details if any"),
    ("43", "B", "Country-by-country report (s.286)", "Details if any"),
    ("44", "B", "Break-up of total expenditure by the GST status of the payees (registered, composition, unregistered)", "Purchase / expense register with GSTINs"),
]
OMITTED = {"28", "29"}
NOT_APPLICABLE = {"36"}
STAT_DUE = re.compile(r"gst|goods and services tax|excise|customs|\bduty\b|\bcess\b|professional tax|property tax|municipal|"
                      r"provident fund|\bpf\b|\besi\b|employees'? state insurance|gratuity|bonus|leave (encashment|salary)|"
                      r"interest .*(bank|loan|financial institution)", re.I)
NOT_43B = re.compile(r"\btds\b|\btcs\b|tax deducted|tax collected|income[- ]?tax|provision for tax", re.I)
DUE_WORDS = re.compile(r"payable|outstanding|provision|accrued|\bdue\b|liabilit", re.I)
TYPE_LABEL = {"individual": "Individual", "huf": "Hindu undivided family", "firm": "Firm", "llp": "Limited liability partnership",
              "company": "Company", "aop_boi": "Association of persons / body of individuals", "cooperative": "Co-operative society",
              "local_authority": "Local authority", "trust_or_institution": "Trust / institution"}


def _row(metric: str, formula: str, substituted: str, result: str, source: str) -> dict:
    return {"metric": metric, "formula": formula, "substituted": substituted, "result": result, "source": source}


def ratios_40(items: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Clause 40 from statement lines. items: key -> {value, prior_value, source, prior_source}."""
    rows, notes = [], []
    rev = items.get("revenue")
    if not rev:
        return rows, ["Turnover (revenue) was not found in the files."]

    def val(key: str, which: str) -> tuple[float | None, str | None]:
        it = items.get(key)
        if not it:
            return None, None
        return (it["value"], it["source"]) if which == "cy" else (it.get("prior_value"), it.get("prior_source"))

    for which, label in (("cy", "This year"), ("py", "Last year")):
        t, ts = val("revenue", which)
        if t is None or t == 0:
            continue
        rows.append(_row(f"Turnover — {label}", "Revenue from operations as reported", "as reported", _inr(t), ts or ""))
        gp, gps = val("gross_profit", which)
        if gp is None:
            c, cs = val("cogs", which)
            if c is not None:
                gp, gps = t - c, f"{ts}; {cs}"
                gp_sub = f"({_inr(t)} − {_inr(c)}) ÷ {_inr(t)} × 100"
            else:
                gp_sub = None
        else:
            gp_sub = f"{_inr(gp)} ÷ {_inr(t)} × 100"
        if gp is not None and gp_sub:
            rows.append(_row(f"Gross profit / turnover — {label}", "Gross profit ÷ turnover × 100", gp_sub, f"{gp / t * 100:.2f}%", gps or ""))
        np_, nps = val("pretax_income", which)
        np_label = "Profit before tax"
        if np_ is None:
            np_, nps = val("net_income", which)
            np_label = "Net profit after tax"
        if np_ is not None:
            rows.append(_row(f"Net profit / turnover — {label}", f"{np_label} ÷ turnover × 100", f"{_inr(np_)} ÷ {_inr(t)} × 100",
                             f"{np_ / t * 100:.2f}%", nps or ""))
        st, sts = val("inventory", which)
        if st is not None:
            rows.append(_row(f"Stock-in-trade / turnover — {label}", "Closing stock ÷ turnover × 100", f"{_inr(st)} ÷ {_inr(t)} × 100",
                             f"{st / t * 100:.2f}%", sts or ""))
    if "gross_profit" not in items and "cogs" not in items:
        notes.append("Gross profit needs a 'Gross profit' or 'Cost of goods sold' line.")
    if "pretax_income" not in items:
        notes.append("Net profit uses profit after tax because no 'Profit before tax' line was found." if "net_income" in items
                     else "Net profit needs a 'Profit before tax' or 'Net profit' line.")
    notes.append("Material consumed ÷ finished goods produced (manufacturers) needs quantities from the stock register.")
    return rows, notes


def clauses_3cd(entity: dict, app: dict, items: dict[str, dict], ledgers: list[dict], dues: list[dict], presumptive: str) -> list[dict]:
    out = []
    for no, part, title, needed in CLAUSES:
        c = {"no": no, "part": part, "title": title, "status": "needs_input", "answer": None, "rows": [], "evidence": [],
             "needed": needed, "note": None}
        if no in OMITTED:
            c.update(status="omitted", answer="Omitted by Notification 23/2025 (from 1 April 2025).", needed="")
        elif no in NOT_APPLICABLE:
            c.update(status="not_applicable", answer="Not applicable: dividend distribution tax was abolished from 1 April 2020.", needed="")
        out.append(c)
    by = {c["no"]: c for c in out}

    def fill(no: str, status: str, answer: str | None = None, **kw):
        by[no].update(status=status, answer=answer, **kw)

    if entity.get("name"):
        fill("1", "filled", entity["name"], evidence=[{"file": "You entered", "where": "Assessee details"}])
    if entity.get("address"):
        fill("2", "filled", entity["address"], evidence=[{"file": "You entered", "where": "Assessee details"}])
    if entity.get("pan_masked"):
        fill("3", "filled", entity["pan_masked"], note="Shown masked. Enter the full PAN in the e-filing utility.",
             evidence=[entity.get("pan_evidence") or {"file": "You entered", "where": "Assessee details"}])
    if entity.get("gstins"):
        fill("4", "review", "Yes — GST: " + ", ".join(g["masked"] for g in entity["gstins"]),
             note="GSTIN found in your files (masked). Add any other indirect-tax registrations.",
             evidence=[g["evidence"] for g in entity["gstins"][:3]])
    fill("5", "filled", TYPE_LABEL.get(entity.get("taxpayer_type", ""), entity.get("taxpayer_type", "")),
         evidence=[{"file": "You entered", "where": "Taxpayer type"}])
    fill("6", "filled", "01-04-2025 to 31-03-2026")
    fill("7", "filled", "2026-27")
    if app["required"]:
        fill("8", "filled", ", ".join(f"Clause ({c.split('(')[1]}" for c in app["clauses"]) + " of section 44AB",
             note="From the applicability test above.")
    elif app["required"] is False:
        fill("8", "not_applicable", "No tax audit is required on the figures given.")
    if entity.get("nature"):
        fill("10", "review", entity["nature"], note="Add the business code from the ITR list of codes.")
    if presumptive != "none":
        fill("12", "review", f"Profit declared under section {presumptive}. Enter the amount included in the P&L.")
    else:
        fill("12", "review", "No presumptive income declared (you answered 'none').")

    # Clause 18: show book depreciation only as a reference
    dep = items.get("depreciation_amortization")
    if dep:
        fill("18", "needs_input", None, note=f"Book depreciation in your file is {_inr(dep['value'])} ({dep['source']}). The Act's "
             "depreciation is worked block-wise (WDV) from the fixed asset register; upload it to complete this clause.")

    # Clause 26: statutory dues found on the balance sheet
    if dues:
        fill("26", "review", f"{len(dues)} statutory due(s) payable at 31 March 2026 found — enter the date each was paid.",
             rows=[_row(d["label"], "Closing balance", _inr(d["value"]), _inr(d["value"]), d["source"]) for d in dues],
             note="Amounts paid after the due date of the return are not allowed until paid (s.43B). TDS payable is not a 43B item "
                  "(it goes to clause 21(b) / 34) and is left out.")

    # Clause 40 from the P&L
    r40, n40 = ratios_40(items)
    if r40:
        fill("40", "filled", None, rows=r40, note=" ".join(n40))
    elif items:
        by["40"]["note"] = " ".join(n40)

    # Ledger-based clauses
    known = [lg for lg in ledgers if lg.get("cash_known")]
    if ledgers and not known:
        for no in ("21", "31"):
            by[no]["note"] = ("Your ledger has no payment-mode column, so cash payments could not be identified. Add a 'Mode' column "
                              "(Cash / Bank / UPI…) or upload the cash book.")
    if known:
        f40a3 = [x for lg in known for x in lg["s40a3"]]
        h21 = [h for lg in known for h in lg["c21a"]]
        rows = [_row(f"40A(3) — {x['party'] or x['account']} on {x['date']}", f"Cash paid to one person in a day > {_inr(x['limit'])}",
                     x["working"], f"{_inr(x['amount'])} disallowable unless a Rule 6DD exception applies", f"{x['file']} › {', '.join(x['refs'])}")
                for x in f40a3]
        rows += [_row(f"21(a) — {h['head']}", "Ledger heads / narrations matching this item", f"{h['entries']} entr{'y' if h['entries'] == 1 else 'ies'}",
                      _inr(h["amount"]), f"{', '.join(h['refs'])}") for h in h21]
        fill("21", "review", (f"{len(f40a3)} cash payment(s) above the s.40A(3) limit" if f40a3 else "No cash payment above the s.40A(3) limit")
             + (f"; {len(h21)} head(s) for clause 21(a) to review." if h21 else "."),
             rows=rows, note="21(b), (c) and (e)–(i) still need the TDS records, partnership deed and provisions. "
                             "Check Rule 6DD exceptions (e.g. payments to banks, in villages without banks, to farmers) before disallowing.")
        ss = [x for lg in known for x in lg["s269ss"]]
        tt = [x for lg in known for x in lg["s269t"]]
        st = [x for lg in known for x in lg["s269st"]]
        rows = ([_row(f"269SS — {x['party'] or x['account']} on {x['date']}", "Loan / deposit accepted in cash ≥ ₹20,000", x["working"],
                      "Report under 31(a); penalty s.271D", f"{x['file']} › {x['where']}") for x in ss]
                + [_row(f"269T — {x['party'] or x['account']} on {x['date']}", "Loan / deposit repaid in cash ≥ ₹20,000", x["working"],
                        "Report under 31(b)/(c); penalty s.271E", f"{x['file']} › {x['where']}") for x in tt]
                + [_row(f"269ST — {x['party'] or x['account']} on {x['date']}", "Cash received from a person in a day ≥ ₹2,00,000", x["working"],
                        "Report under 31(ba)/(bb); penalty s.271DA", f"{x['file']} › {', '.join(x['refs'])}") for x in st])
        fill("31", "filled" if not rows else "review",
             "No cash loans, deposits or receipts above the limits were found in the ledger." if not rows else
             f"{len(rows)} item(s) found: " + ", ".join(f"{n} under {s}" for n, s in ((len(ss), '269SS'), (len(tt), '269T'), (len(st), '269ST')) if n) + ".",
             rows=rows, note="Account-payee cheques, drafts and electronic transfers are not cash. Loans and deposits taken through "
                             "banking channels are also reported under clause 31 — add them from the bank book.")
        c44 = [lg["c44"] for lg in known if lg.get("c44")]
        if c44:
            tot = sum(c["total"] for c in c44)
            reg = sum(c["registered"] for c in c44)
            fill("44", "review", None, rows=[
                _row("Total expenditure (from ledger)", "Payments excluding loans, capital, taxes and contra", _inr(tot), _inr(tot), "ledger"),
                _row("Paid to GST-registered payees", "Rows with a valid GSTIN", _inr(reg), _inr(reg), "ledger"),
                _row("Paid to unregistered payees", "Total − registered", f"{_inr(tot)} − {_inr(reg)}", _inr(tot - reg), "ledger")],
                note="Split the registered amount into exempt, composition-scheme and other registered payees as the form asks.")
    return out


SUMMARY = {"filled": "Filled in", "review": "Filled — please review", "needs_input": "Needs your input",
           "not_applicable": "Not applicable", "omitted": "Omitted from 1 Apr 2025"}


def mask_gstin(g: str) -> str:
    return f"{g[:2]}XXX{g[5]}X####{g[11]}{g[12:]}" if len(g) == 15 else g
