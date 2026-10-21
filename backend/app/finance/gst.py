"""Indian GST returns: which returns apply, due dates, GSTR-3B set-off, GSTR-1 tables from a
sales register, and purchase register vs GSTR-2B reconciliation.

Rules follow the CGST Act / Rules and GSTN guidance as of October 2026; every rule carries the
section or official page it came from (SOURCES). The 57th GST Council (8 Oct 2026) recommended
further return changes that are not yet notified, so they are not applied.

The app prepares the figures; it does not file. Filing through software needs a licensed GST
Suvidha Provider (GSP) and the taxpayer's API consent; otherwise returns are filed on the GST
portal (or GSTR-1 via the Returns Offline Tool JSON) with EVC or DSC.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import FinanceInputError

SOURCES = {
    "gstr1": "https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm",
    "gstr3b": "https://tutorial.gst.gov.in/userguide/returns/GSTR3B.htm",
    "qrmp": "https://tutorial.gst.gov.in/offlineutilities/returns/QRMP_Advisory.pdf",
    "gstr4": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/rules/cgst_rules/active/chapter8/rule62_v1.00.html",
    "cmp08": "https://tutorial.gst.gov.in/userguide/returns/FAQs_CMP02.htm",
    "gstr9": "https://tutorial.gst.gov.in/userguide/returns/FAQs_gstr9.htm",
    "gstr9c": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/rules/cgst_rules/active/chapter8/rule80_v1.00.html",
    "registration": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/acts/2017_CGST_act/active/chapter6/section22_v1.00.html",
    "composition": "https://cbic-gst.gov.in/pdf/press-release/Changes-recommended-Composition-Scheme.pdf",
    "section49": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/acts/2017_CGST_act/active/chapter10/section49_v1.00.html",
    "rule88a": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/rules/cgst_rules/active/chapter9/rule88a_v1.00.html",
    "rule86b": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/rules/cgst_rules/active/chapter9/rule86b_v1.00.html",
    "interest": "https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/acts/2017_CGST_act/active/chapter10/section50_v1.00.html",
    "late_fee": "https://gstcouncil.gov.in/node/4305",
    "gstr2b": "https://tutorial.gst.gov.in/userguide/returns/FAQ_gstr2b.htm",
    "ims": "https://tutorial.gst.gov.in/downloads/news/revised_advisory_on_ims.pdf",
    "rates": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2163560",
    "offline_tool": "https://www.gst.gov.in/download/returns",
    "gsp_api": "https://tutorial.gst.gov.in/downloads/news/taxpayer_advisory_on_transparency_of_data_access_via_gsp_api.pdf",
    "portal": "https://www.gst.gov.in/",
}

LAKH, CRORE = 100_000, 10_000_000

# GSTIN state codes.
STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
}
# Quarterly GSTR-3B under QRMP is due on the 22nd for these states/UTs and on the 24th for the rest (proviso to Rule 61).
QRMP_22ND = {"22", "23", "24", "26", "27", "29", "30", "32", "33", "36", "37", "34", "35", "31"}
GOODS_THRESHOLD_20L = {"12", "14", "17", "15", "13", "34", "11", "36", "16", "05"}  # kept ₹20 lakh for goods
SERVICES_THRESHOLD_10L = {"14", "15", "13", "16"}
COMPOSITION_75L = {"12", "14", "17", "15", "13", "11", "16", "05"}


def _state(code: str) -> str:
    code = (code or "").strip().zfill(2)[:2]
    if code not in STATES:
        raise FinanceInputError("Choose the state of registration (two-digit GST state code).")
    return code


def _nn(name: str, v: float | None) -> float:
    if v is None:
        return 0.0
    if not math.isfinite(v) or v < 0:
        raise FinanceInputError(f"{name} must be zero or a positive amount.")
    return float(v)


def _next_month(y: int, m: int) -> tuple[int, int]:
    return (y + 1, 1) if m == 12 else (y, m + 1)


def _date(y: int, m: int, d: int) -> str:
    return dt.date(y, m, d).isoformat()


def fy_of(y: int, m: int) -> str:
    start = y if m >= 4 else y - 1
    return f"{start}-{str(start + 1)[-2:]}"


# ---------------------------------------------------------------- which returns apply
@dataclass
class GSTProfile:
    registration: str = "regular"  # regular | composition | non_resident | oidar | isd | tds_deductor | tcs_operator | uin | not_registered
    state_code: str = "27"
    aggregate_turnover_prev_fy: float = 0.0
    aggregate_turnover_current_fy: float | None = None
    supplies: str = "goods"  # goods | services | both
    composition_kind: str = "trader"  # trader | manufacturer | restaurant | services
    qrmp: bool = False
    year: int = 2026  # tax period to compute due dates for
    month: int = 9


def select_returns(p: GSTProfile) -> dict:
    sc = _state(p.state_code)
    ato = _nn("Aggregate turnover", p.aggregate_turnover_prev_fy)
    if not (1 <= p.month <= 12):
        raise FinanceInputError("Month must be 1 to 12.")
    y, m = p.year, p.month
    ny, nm = _next_month(y, m)
    quarter_end = m in (3, 6, 9, 12)
    returns: list[dict] = []
    warnings: list[str] = []
    notes: list[str] = []

    def add(form: str, what: str, frequency: str, due: str, next_due: str | None, source: str, optional: bool = False):
        returns.append({"form": form, "what": what, "frequency": frequency, "due": due, "next_due": next_due,
                        "optional": optional, "source": SOURCES[source]})

    reg = p.registration
    if reg == "not_registered":
        if p.supplies == "goods":
            limit = 20 * LAKH if sc in GOODS_THRESHOLD_20L else 40 * LAKH
        else:
            limit = 10 * LAKH if sc in SERVICES_THRESHOLD_10L else 20 * LAKH
        current = p.aggregate_turnover_current_fy if p.aggregate_turnover_current_fy is not None else ato
        must = current > limit
        return {"returns": [], "registration_required": must, "threshold": limit, "state": STATES[sc],
                "message": (f"Registration is required: aggregate turnover ₹{current:,.0f} exceeds the ₹{limit:,.0f} threshold for "
                            f"{'goods' if p.supplies == 'goods' else 'services'} in {STATES[sc]}." if must else
                            f"Registration is not required on turnover alone (threshold ₹{limit:,.0f}). It is compulsory regardless of "
                            "turnover for inter-state taxable supplies of goods, e-commerce sellers, casual and non-resident taxable "
                            "persons, and those liable under reverse charge (section 24)."),
                "warnings": warnings, "notes": notes, "source": SOURCES["registration"]}

    if reg == "regular":
        if p.qrmp and ato > 5 * CRORE:
            warnings.append("QRMP is only for aggregate turnover up to ₹5 crore in the previous year; you must file monthly.")
        quarterly = p.qrmp and ato <= 5 * CRORE
        if quarterly:
            day = 22 if sc in QRMP_22ND else 24
            if quarter_end:
                add("GSTR-1", "Outward supplies (quarterly)", "Quarterly (QRMP)", "13th of the month after the quarter",
                    _date(ny, nm, 13), "gstr1")
                add("GSTR-3B", "Summary return and tax payment (quarterly)", "Quarterly (QRMP)",
                    f"{day}th of the month after the quarter ({STATES[sc]})", _date(ny, nm, day), "qrmp")
            else:
                add("IFF", "Invoice Furnishing Facility for B2B invoices (months 1 and 2)", "Monthly, optional", "1st to 13th of next month",
                    _date(ny, nm, 13), "gstr1", optional=True)
                add("PMT-06", "Tax payment for months 1 and 2 (fixed-sum or self-assessment)", "Monthly", "25th of next month",
                    _date(ny, nm, 25), "qrmp")
        else:
            add("GSTR-1", "Outward supplies (invoice-wise)", "Monthly", "11th of next month", _date(ny, nm, 11), "gstr1")
            add("GSTR-3B", "Summary return and tax payment", "Monthly", "20th of next month", _date(ny, nm, 20), "gstr3b")
        add("GSTR-1A", "Amendment of GSTR-1 for the same period, before GSTR-3B is filed", "As needed", "Before filing GSTR-3B",
            None, "gstr1", optional=True)
        notes.append("Tax liability in GSTR-3B is auto-filled from GSTR-1/1A/IFF and cannot be edited (from the July 2025 period); "
                     "correct it through GSTR-1A before filing GSTR-3B.")
        notes.append("Input tax credit comes from GSTR-2B (generated on the 14th). Review supplier invoices in the Invoice "
                     "Management System (IMS) first.")
    elif reg == "composition":
        limit = 75 * LAKH if sc in COMPOSITION_75L else 1.5 * CRORE
        if p.composition_kind == "services":
            limit = 50 * LAKH
        if ato > limit:
            warnings.append(f"Composition is allowed only up to ₹{limit:,.0f} aggregate turnover; you should move to the regular scheme.")
        rate = {"trader": 0.01, "manufacturer": 0.01, "restaurant": 0.05, "services": 0.06}.get(p.composition_kind)
        if rate is None:
            raise FinanceInputError("Composition type must be trader, manufacturer, restaurant or services.")
        notes.append(f"Composition tax rate: {rate:.0%} of turnover (half CGST, half SGST), paid in cash; no input tax credit.")
        if quarter_end:
            add("CMP-08", "Quarterly statement and tax payment", "Quarterly", "18th of the month after the quarter", _date(ny, nm, 18), "cmp08")
        fy_end_year = y + 1 if m >= 4 else y
        add("GSTR-4", "Annual return for composition taxpayers", "Annual", "30 June after the financial year", _date(fy_end_year, 6, 30), "gstr4")
    elif reg == "non_resident":
        add("GSTR-5", "Return of a non-resident taxable person", "Monthly",
            "13th of next month, or within 7 days after registration expires if earlier", _date(ny, nm, 13), "gstr1")
    elif reg == "oidar":
        add("GSTR-5A", "Online information and database access services from outside India", "Monthly", "20th of next month",
            _date(ny, nm, 20), "gstr1")
    elif reg == "isd":
        add("GSTR-6", "Input Service Distributor return", "Monthly", "13th of next month", _date(ny, nm, 13), "gstr1")
    elif reg == "tds_deductor":
        add("GSTR-7", "TDS deducted under section 51", "Monthly", "10th of next month", _date(ny, nm, 10), "gstr1")
    elif reg == "tcs_operator":
        add("GSTR-8", "TCS collected by an e-commerce operator under section 52", "Monthly", "10th of next month", _date(ny, nm, 10), "gstr1")
    elif reg == "uin":
        add("GSTR-11", "Inward supplies of UIN holders (embassies, UN bodies), with a refund claim", "Quarterly, when claiming a refund",
            "No fixed due date; file with the refund application (RFD-10)", None, "gstr1")
    else:
        raise FinanceInputError("Unknown registration type.")

    if reg == "regular":
        fy_end_year = y + 1 if m >= 4 else y
        annual = _date(fy_end_year, 12, 31)
        add("GSTR-9", "Annual return", "Annual", "31 December after the financial year", annual, "gstr9", optional=ato <= 2 * CRORE)
        if ato <= 2 * CRORE:
            notes.append("GSTR-9 is optional for aggregate turnover up to ₹2 crore (Notification 15/2025-CT).")
        if ato > 5 * CRORE:
            add("GSTR-9C", "Self-certified reconciliation statement", "Annual", "With GSTR-9, 31 December", annual, "gstr9c")
    notes.append("Returns cannot be filed more than three years after their due date (Finance Act 2023, enforced on the portal).")
    notes.append("GSTR-10 (final return) is due within three months of cancellation of registration.")
    return {"returns": returns, "state": STATES[sc], "period": f"{y}-{m:02d}", "financial_year": fy_of(y, m),
            "warnings": warnings, "notes": notes}


# ---------------------------------------------------------------- GSTR-3B set-off
HEADS = ("igst", "cgst", "sgst", "cess")


@dataclass
class Heads:
    igst: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    cess: float = 0.0

    def get(self) -> dict[str, float]:
        return {h: _nn(h.upper(), getattr(self, h)) for h in HEADS}


@dataclass
class GSTR3BIn:
    outward_tax: Heads = field(default_factory=Heads)  # 3.1(a)+(b) tax, payable from credit or cash
    reverse_charge_tax: Heads = field(default_factory=Heads)  # 3.1(d): cash only
    eco_9_5_tax: Heads = field(default_factory=Heads)  # 3.1.1(i): e-commerce operator under 9(5), cash only
    itc_available: Heads = field(default_factory=Heads)  # Table 4A (from GSTR-2B, imports, RCM paid)
    itc_reversed: Heads = field(default_factory=Heads)  # Table 4B
    opening_credit: Heads = field(default_factory=Heads)  # electronic credit ledger balance brought forward
    taxable_value_month: float | None = None  # for the Rule 86B check
    rule_86b_applies: bool = False
    filing_date: dt.date | None = None
    due_date: dt.date | None = None
    nil_return: bool = False
    aggregate_turnover: float | None = None


def _setoff(L: dict[str, float], C: dict[str, float]) -> tuple[dict, dict, dict]:
    """Order of credit utilisation, section 49(5) with sections 49A/49B and Rule 88A:
    1. IGST credit against IGST, then against CGST and SGST (any order or proportion) — it must be
       used up before CGST/SGST credit is touched (s.49A).
    2. CGST credit against CGST, then IGST; SGST credit against SGST, then IGST.
    CGST credit never pays SGST and vice versa. Cess credit pays only cess.
    The IGST credit left after step 1 is aimed first at the CGST/SGST shortfalls their own credit
    cannot cover, which keeps cash to the minimum."""
    use = {f"{c}->{t}": 0.0 for c in HEADS for t in HEADS}
    L, C = dict(L), dict(C)

    def apply(cr: str, tx: str, amount: float | None = None):
        amt = min(C[cr], L[tx]) if amount is None else min(amount, C[cr], L[tx])
        if amt > 0:
            use[f"{cr}->{tx}"] += amt
            C[cr] -= amt
            L[tx] -= amt

    apply("igst", "igst")
    short_c, short_s = max(0.0, L["cgst"] - C["cgst"]), max(0.0, L["sgst"] - C["sgst"])
    pool = C["igst"]
    if short_c + short_s > 0 and pool > 0:
        k = min(1.0, pool / (short_c + short_s))
        apply("igst", "cgst", short_c * k)
        apply("igst", "sgst", short_s * k)
    if C["igst"] > 0:  # still unused: apply to the remaining CGST/SGST liability in proportion
        rest = L["cgst"] + L["sgst"]
        if rest > 0:
            k = min(1.0, C["igst"] / rest)
            c_part, s_part = L["cgst"] * k, L["sgst"] * k
            apply("igst", "cgst", c_part)
            apply("igst", "sgst", s_part)
    apply("cgst", "cgst")
    apply("sgst", "sgst")
    apply("cgst", "igst")
    apply("sgst", "igst")
    apply("cess", "cess")
    return use, L, C


def late_fee_per_return(days: int, nil: bool, aggregate_turnover: float | None) -> dict:
    """Section 47 as reduced by Notifications 19/2021 and 20/2021: ₹50 a day (₹25 CGST + ₹25 SGST),
    ₹20 for nil returns, capped by turnover. Caps above ₹1.5 crore are from secondary sources."""
    if days <= 0:
        return {"days": 0, "fee": 0.0, "cap": None}
    per_day = 20 if nil else 50
    if nil:
        cap = 500
    elif aggregate_turnover is None:
        cap = 10_000
    elif aggregate_turnover <= 1.5 * CRORE:
        cap = 2_000
    elif aggregate_turnover <= 5 * CRORE:
        cap = 5_000
    else:
        cap = 10_000
    fee = min(days * per_day, cap)
    return {"days": days, "per_day": per_day, "fee": float(fee), "cgst": fee / 2, "sgst": fee / 2, "cap": cap}


def gstr3b(x: GSTR3BIn) -> dict:
    out, rcm, eco = x.outward_tax.get(), x.reverse_charge_tax.get(), x.eco_9_5_tax.get()
    avail, rev, opening = x.itc_available.get(), x.itc_reversed.get(), x.opening_credit.get()
    net_itc = {h: avail[h] - rev[h] for h in HEADS}
    for h in HEADS:
        if net_itc[h] < 0:
            raise FinanceInputError(f"{h.upper()} credit reversed is more than the credit available.")
    credit = {h: net_itc[h] + opening[h] for h in HEADS}
    warnings: list[str] = []
    notes = ["Tax on reverse-charge supplies and on supplies through an e-commerce operator under section 9(5) is paid in cash only; "
             "reverse-charge tax paid becomes input tax credit (Table 4A(3)) once paid."]
    use, left_liab, left_credit = _setoff(out, credit)

    total_out = sum(out.values())
    credit_used = sum(use.values())
    if x.rule_86b_applies or (x.taxable_value_month is not None and x.taxable_value_month > 50 * LAKH):
        cap = 0.99 * total_out
        if credit_used > cap:
            cut = credit_used - cap
            for key in ("sgst->sgst", "cgst->cgst", "igst->sgst", "igst->cgst", "igst->igst"):  # give back credit, last used first
                if cut <= 1e-9:
                    break
                take = min(cut, use[key])
                use[key] -= take
                cr, tx = key.split("->")
                left_credit[cr] += take
                left_liab[tx] += take
                cut -= take
            credit_used = sum(use.values())
        notes.append("Rule 86B: when taxable supplies exceed ₹50 lakh in a month, at most 99% of output tax may be paid from credit "
                     "(exceptions apply, e.g. income tax over ₹1 lakh paid in each of the last two years, or refunds of unutilised credit).")
    cash = {h: left_liab[h] + rcm[h] + eco[h] for h in HEADS}
    total_cash = sum(cash.values())

    interest = None
    late = None
    if x.due_date and x.filing_date:
        days = (x.filing_date - x.due_date).days
        if days > 0:
            # Section 50(1) with its proviso: 18% a year on the tax paid in cash, for the days of delay
            interest = {"days": days, "rate": 0.18, "on": total_cash, "amount": total_cash * 0.18 * days / 365,
                        "by_head": {h: cash[h] * 0.18 * days / 365 for h in HEADS}}
            late = late_fee_per_return(days, x.nil_return, x.aggregate_turnover)
            warnings.append(f"Filed {days} days late: interest and late fee apply.")
    table_6_1 = [{"head": h.upper(), "tax_payable": out[h] + rcm[h] + eco[h],
                  "paid_through_itc": {c.upper(): use[f"{c}->{h}"] for c in HEADS if use[f"{c}->{h}"] > 0},
                  "paid_in_cash": cash[h]} for h in HEADS]
    return {"liability": {"outward": out, "reverse_charge": rcm, "eco_9_5": eco}, "itc": {"available": avail, "reversed": rev,
            "net": net_itc, "opening": opening, "total": credit}, "utilisation": {k: v for k, v in use.items() if v > 0},
            "table_6_1": table_6_1, "cash": cash, "total_cash": total_cash, "credit_used": credit_used,
            "closing_credit": left_credit, "interest": interest, "late_fee": late, "warnings": warnings, "notes": notes,
            "sources": {k: SOURCES[k] for k in ("section49", "rule88a", "rule86b", "interest", "late_fee")}}


# ---------------------------------------------------------------- GSTIN validation
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z]$")
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _B36.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _B36[(36 - total % 36) % 36]


def valid_gstin(g: str) -> bool:
    g = (g or "").strip().upper()
    if not _GSTIN_RE.match(g) or g[:2] not in STATES and g[:2] != "99":
        return False
    return gstin_check_digit(g[:14]) == g[14]


# ---------------------------------------------------------------- GSTR-1 from a sales register
CATEGORIES = {"regular", "export_with_payment", "export_without_payment", "sez_with_payment", "sez_without_payment",
              "nil_rated", "exempt", "non_gst", "deemed_export"}
DOC_TYPES = {"invoice", "credit_note", "debit_note"}
B2CL_LIMIT = 1 * LAKH  # Rule 59(4) as amended by Notification 12/2024-CT, from 1 Aug 2024


@dataclass
class Invoice:
    number: str
    date: str | None = None
    gstin: str | None = None  # recipient
    place_of_supply: str | None = None  # state code; defaults to the recipient's GSTIN state, else the supplier's
    taxable_value: float = 0.0
    rate: float | None = None  # %
    igst: float | None = None
    cgst: float | None = None
    sgst: float | None = None
    cess: float = 0.0
    hsn: str | None = None
    doc_type: str = "invoice"
    category: str = "regular"
    invoice_value: float | None = None
    row: int | None = None  # source row for messages


def _r2(x: float) -> float:
    return round(x + 0.0, 2)


def gstr1(invoices: list[Invoice], supplier_gstin: str, aggregate_turnover: float | None = None) -> dict:
    sup = (supplier_gstin or "").strip().upper()
    if not valid_gstin(sup):
        raise FinanceInputError("Enter your own valid GSTIN (15 characters; the check digit must match).")
    home = sup[:2]
    if not invoices:
        raise FinanceInputError("The sales register has no invoices.")
    if len(invoices) > 100_000:
        raise FinanceInputError("At most 100,000 rows per file.")
    issues: list[dict] = []
    tables: dict[str, list] = {"b2b": [], "b2cl": [], "exp": [], "sez": [], "cdnr": [], "cdnur": []}
    b2cs: dict[tuple, dict] = defaultdict(lambda: {"taxable_value": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0, "count": 0})
    nil = {k: {"inter_registered": 0.0, "inter_unregistered": 0.0, "intra_registered": 0.0, "intra_unregistered": 0.0}
           for k in ("nil_rated", "exempt", "non_gst")}
    hsn: dict[tuple, dict] = defaultdict(lambda: {"taxable_value": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0, "count": 0})
    docs: dict[str, list[str]] = defaultdict(list)
    hsn_digits = 6 if (aggregate_turnover or 0) > 5 * CRORE else 4
    seen: set[tuple] = set()

    def issue(inv: Invoice, msg: str, level: str = "error"):
        issues.append({"row": inv.row, "invoice": inv.number, "level": level, "message": msg})

    for inv in invoices:
        num = (inv.number or "").strip()
        if not num:
            issue(inv, "Invoice number is missing.")
            continue
        if len(num) > 16:
            issue(inv, "Invoice number is longer than 16 characters (GST portal limit).")
        doc = (inv.doc_type or "invoice").strip().lower().replace(" ", "_")
        if doc in ("cn", "credit"):
            doc = "credit_note"
        if doc in ("dn", "debit"):
            doc = "debit_note"
        if doc not in DOC_TYPES:
            issue(inv, f"Unknown document type '{inv.doc_type}'.")
            continue
        cat = (inv.category or "regular").strip().lower().replace(" ", "_")
        if cat not in CATEGORIES:
            issue(inv, f"Unknown category '{inv.category}'.")
            continue
        key = (doc, num.upper())
        if key in seen:
            issue(inv, "Duplicate document number.")
        seen.add(key)
        docs[doc].append(num)
        gstin = (inv.gstin or "").strip().upper() or None
        if gstin and not valid_gstin(gstin):
            issue(inv, f"Recipient GSTIN {gstin} is not valid (format or check digit).")
            gstin = None if len(gstin) != 15 else gstin
        pos = (inv.place_of_supply or "").strip()
        pos = pos.zfill(2)[:2] if pos else (gstin[:2] if gstin else home)
        if pos not in STATES:
            issue(inv, f"Place of supply '{inv.place_of_supply}' is not a valid state code.")
            continue
        tv = inv.taxable_value
        if tv is None or not math.isfinite(tv):
            issue(inv, "Taxable value is missing.")
            continue
        inter = pos != home or cat in ("export_with_payment", "export_without_payment", "sez_with_payment", "sez_without_payment")
        if cat in ("nil_rated", "exempt", "non_gst"):
            bucket = ("inter" if inter else "intra") + ("_registered" if gstin else "_unregistered")
            nil[cat][bucket] += tv
            continue
        rate = inv.rate
        given = [inv.igst, inv.cgst, inv.sgst]
        if rate is None and all(g is None for g in given):
            issue(inv, "Neither a GST rate nor tax amounts are given.")
            continue
        zero = cat in ("export_without_payment", "sez_without_payment")
        if any(g is not None for g in given):
            igst, cgst, sgst = (g or 0.0 for g in given)
            if rate is None and tv:
                rate = round((igst + cgst + sgst) / tv * 100, 2)
        else:
            tax = 0.0 if zero else tv * rate / 100
            igst, cgst, sgst = (tax, 0.0, 0.0) if inter else (0.0, tax / 2, tax / 2)
        if not zero and rate is not None:
            expected = tv * rate / 100
            if abs((igst + cgst + sgst) - expected) > 1:
                issue(inv, f"Tax {igst + cgst + sgst:,.2f} does not match {rate}% of {tv:,.2f} ({expected:,.2f}).", "warning")
        if inter and (cgst or sgst):
            issue(inv, "Inter-state supply (place of supply differs from your state) should carry IGST, not CGST/SGST.")
        if not inter and igst:
            issue(inv, "Intra-state supply should carry CGST and SGST, not IGST.")
        if cgst and sgst and abs(cgst - sgst) > 0.5:
            issue(inv, "CGST and SGST should be equal.", "warning")
        value = inv.invoice_value if inv.invoice_value is not None else tv + igst + cgst + sgst + (inv.cess or 0)
        row = {"number": num, "date": inv.date, "gstin": gstin, "place_of_supply": pos, "state": STATES[pos], "rate": rate,
               "taxable_value": _r2(tv), "igst": _r2(igst), "cgst": _r2(cgst), "sgst": _r2(sgst), "cess": _r2(inv.cess or 0),
               "invoice_value": _r2(value), "row": inv.row}
        sign = -1 if doc == "credit_note" else 1
        if doc != "invoice":
            row["note_type"] = "C" if doc == "credit_note" else "D"
            (tables["cdnr"] if gstin else tables["cdnur"]).append(row)
        elif cat.startswith("export"):
            row["with_payment"] = cat == "export_with_payment"
            tables["exp"].append(row)
        elif cat.startswith("sez") or cat == "deemed_export":
            row["kind"] = cat
            tables["sez"].append(row)
        elif gstin:
            tables["b2b"].append(row)
        elif inter and value > B2CL_LIMIT:
            tables["b2cl"].append(row)
        else:
            k = (pos, rate)
            b = b2cs[k]
            for h in ("igst", "cgst", "sgst"):
                b[h] += row[h]
            b["taxable_value"] += tv
            b["cess"] += row["cess"]
            b["count"] += 1
        code = re.sub(r"\D", "", inv.hsn or "")
        if not code:
            issue(inv, f"HSN/SAC code missing (at least {hsn_digits} digits are required in Table 12).", "warning")
        elif len(code) < hsn_digits:
            issue(inv, f"HSN/SAC {code} has fewer than {hsn_digits} digits.", "warning")
        h = hsn[("B2B" if gstin else "B2C", code or "—", rate)]
        h["taxable_value"] += sign * tv
        for t in ("igst", "cgst", "sgst"):
            h[t] += sign * row[t]
        h["cess"] += sign * row["cess"]
        h["count"] += 1

    def total(rows: list[dict]) -> dict:
        return {k: _r2(sum(r[k] for r in rows)) for k in ("taxable_value", "igst", "cgst", "sgst", "cess")} | {"count": len(rows)}

    b2cs_rows = [{"place_of_supply": k[0], "state": STATES[k[0]], "rate": k[1], **{x: _r2(v) if isinstance(v, float) else v for x, v in b.items()}}
                 for k, b in sorted(b2cs.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))]
    hsn_rows = [{"section": k[0], "hsn": k[1], "rate": k[2], **{x: _r2(v) if isinstance(v, float) else v for x, v in v.items()}}
                for k, v in sorted(hsn.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or 0))]
    doc_summary = [{"document": d, "count": len(nums), "from": min(nums), "to": max(nums)} for d, nums in docs.items() if nums]
    summary = {"4A_b2b": total(tables["b2b"]), "5_b2cl": total(tables["b2cl"]), "6A_exports": total(tables["exp"]),
               "6B_sez": total(tables["sez"]), "7_b2cs": total(b2cs_rows), "9B_cdnr": total(tables["cdnr"]),
               "9B_cdnur": total(tables["cdnur"])}
    notes_rows = tables["cdnr"] + tables["cdnur"]
    liability = {h: _r2(sum(v[h] for k, v in summary.items() if not k.startswith("9B"))
                        + sum(r[h] for r in notes_rows if r["note_type"] == "D")
                        - sum(r[h] for r in notes_rows if r["note_type"] == "C")) for h in ("igst", "cgst", "sgst", "cess")}
    return {"supplier_gstin": sup, "state": STATES[home], "tables": {**tables, "b2cs": b2cs_rows, "nil": nil, "hsn": hsn_rows,
            "documents": doc_summary}, "summary": summary, "liability": liability, "hsn_digits": hsn_digits,
            "issues": issues, "errors": sum(1 for i in issues if i["level"] == "error"),
            "warnings": sum(1 for i in issues if i["level"] == "warning"),
            "notes": [f"B2C inter-state invoices above ₹{B2CL_LIMIT:,.0f} are reported invoice-wise in Table 5 (B2CL); smaller B2C "
                      "supplies are summarised by state and rate in Table 7.",
                      f"Table 12 needs HSN/SAC of at least {hsn_digits} digits for your turnover, split into B2B and B2C.",
                      "Upload through the GST Returns Offline Tool or enter the summaries on the portal; this app does not file."],
            "source": SOURCES["gstr1"]}


# ---------------------------------------------------------------- purchase register vs GSTR-2B
@dataclass
class Purchase:
    gstin: str
    number: str
    date: str | None = None
    taxable_value: float = 0.0
    igst: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    cess: float = 0.0
    row: int | None = None


def norm_invoice(n: str) -> str:
    """Invoice numbers are compared without spaces, slashes, dashes and leading zeros, case-insensitively."""
    s = re.sub(r"[^A-Z0-9]", "", (n or "").upper())
    return s.lstrip("0") or s


def reconcile_2b(books: list[Purchase], portal: list[Purchase], tolerance: float = 1.0) -> dict:
    if not books and not portal:
        raise FinanceInputError("Both the purchase register and GSTR-2B are empty.")

    def tax(p: Purchase) -> float:
        return (p.igst or 0) + (p.cgst or 0) + (p.sgst or 0) + (p.cess or 0)

    def key(p: Purchase) -> tuple[str, str]:
        return ((p.gstin or "").strip().upper(), norm_invoice(p.number))

    portal_by_key: dict[tuple, list[Purchase]] = defaultdict(list)
    for p in portal:
        portal_by_key[key(p)].append(p)
    used: set[int] = set()
    matched, mismatched, missing_in_2b = [], [], []

    def row(b: Purchase | None, p: Purchase | None, status: str, note: str = "") -> dict:
        def side(x: Purchase | None):
            return None if x is None else {"gstin": x.gstin, "number": x.number, "date": x.date, "taxable_value": x.taxable_value,
                                           "tax": _r2(tax(x)), "igst": x.igst, "cgst": x.cgst, "sgst": x.sgst, "cess": x.cess, "row": x.row}
        return {"status": status, "books": side(b), "gstr2b": side(p), "note": note,
                "tax_difference": _r2((tax(b) if b else 0) - (tax(p) if p else 0))}

    for b in books:
        cands = [p for p in portal_by_key.get(key(b), []) if id(p) not in used]
        if cands:
            p = cands[0]
            used.add(id(p))
            dv, dt_ = abs(b.taxable_value - p.taxable_value), abs(tax(b) - tax(p))
            if dv <= tolerance and dt_ <= tolerance:
                matched.append(row(b, p, "matched"))
            else:
                mismatched.append(row(b, p, "mismatch", f"Taxable value differs by {dv:,.2f}, tax by {dt_:,.2f}."))
            continue
        missing_in_2b.append(b)
    # probable matches: same supplier and same tax amount, different invoice number
    leftover = [p for p in portal if id(p) not in used]
    probable, not_found = [], []
    for b in missing_in_2b:
        hit = next((p for p in leftover if id(p) not in used and (p.gstin or "").upper() == (b.gstin or "").upper()
                    and abs(tax(p) - tax(b)) <= tolerance and abs(p.taxable_value - b.taxable_value) <= tolerance), None)
        if hit:
            used.add(id(hit))
            probable.append(row(b, hit, "probable", "Same supplier and amounts; invoice number differs — check for a typing error."))
        else:
            not_found.append(row(b, None, "missing_in_2b",
                                 "Not in GSTR-2B: credit cannot be claimed until the supplier reports it. Follow up with the supplier."))
    only_portal = [row(None, p, "missing_in_books", "In GSTR-2B but not in your books: record it, or reject it in IMS if not genuine.")
                   for p in portal if id(p) not in used]

    def sum_tax(rows: list[dict], side: str) -> float:
        return _r2(sum(r[side]["tax"] for r in rows if r[side]))

    return {"summary": {
                "matched": {"count": len(matched), "tax": sum_tax(matched, "books")},
                "mismatch": {"count": len(mismatched), "tax_books": sum_tax(mismatched, "books"), "tax_2b": sum_tax(mismatched, "gstr2b")},
                "probable": {"count": len(probable), "tax": sum_tax(probable, "books")},
                "missing_in_2b": {"count": len(not_found), "tax": sum_tax(not_found, "books")},
                "missing_in_books": {"count": len(only_portal), "tax": sum_tax(only_portal, "gstr2b")},
                "credit_safe_to_claim": _r2(sum_tax(matched, "gstr2b") + sum(min(r["books"]["tax"], r["gstr2b"]["tax"]) for r in mismatched)
                                            + sum_tax(probable, "gstr2b")),
            },
            "rows": matched + mismatched + probable + not_found + only_portal,
            "notes": ["Credit is claimed on the lower of the books and GSTR-2B amounts until the difference is resolved (section 16(2)(aa)).",
                      "Invoice numbers are compared ignoring spaces, slashes, dashes, case and leading zeros."],
            "source": SOURCES["gstr2b"]}


FILING_STEPS = {
    "gstr1": ["Log in at gst.gov.in → Services → Returns → Returns Dashboard, choose the financial year and period.",
              "Prepare GSTR-1 online, or use the Returns Offline Tool to build the JSON from your invoices and upload it (Prepare Offline).",
              "Check the summary against this app's tables, then file with DSC (mandatory for companies and LLPs) or EVC."],
    "gstr3b": ["Review supplier invoices in IMS (accept / reject / pending) so GSTR-2B is right, then open GSTR-3B.",
               "Liability is auto-filled from GSTR-1/1A; enter or check Table 4 credit against this app's working.",
               "Offset liability (Table 6.1) in the order shown here, pay any cash by challan (PMT-06), then file with DSC or EVC."],
}
