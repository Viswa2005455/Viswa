"""Income tax (AY 2026-27) and GST endpoints. The app prepares computations; it does not file returns."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.security import limiter
from ..config import Settings, get_settings
from ..db.models import User
from ..db.session import get_db
from ..files import ledger, service, taxdocs
from ..files.routing import suggest_statement_mapping
from ..files.registers import PURCHASE_TEMPLATE, SALES_TEMPLATE, read_register
from ..finance import FinanceInputError, gst, incometax, taxaudit
from ..reports.taxaudit_doc import build_docx
from .base import BaseModel
from .finance import clean

router = APIRouter(prefix="/api/tax", tags=["income tax"])
# Only the assessment year whose rules were checked is accepted; anything else is refused, never estimated.
AssessmentYear = Literal["2026-27"]
gst_router = APIRouter(prefix="/api/gst", tags=["gst"])
Money = Field(default=0.0, ge=0, le=1e13)


# ---------------------------------------------------------------- income tax
@router.get("/info")
def info():
    return {"year": incometax.YEAR, "ruleset": incometax.RULESET, "sources": incometax.SOURCES, "filing_steps": incometax.FILING_STEPS,
            "filing_note": "Only an e-Return Intermediary registered with the Income Tax Department can submit returns through "
                           "its APIs. Use these figures on the e-filing portal or in the official offline utility."}


class ProfileIn(BaseModel):
    taxpayer_type: Literal["individual", "huf", "firm", "llp", "company", "aop_boi", "cooperative", "local_authority",
                           "trust_or_institution"] = "individual"
    residential_status: Literal["resident", "rnor", "non_resident"] = "resident"
    total_income: float = Money
    salary_or_pension: bool = False
    house_properties: int = Field(default=0, ge=0, le=1000)
    business_income: bool = False
    presumptive: Literal["none", "44AD", "44ADA", "44AE"] = "none"
    partner_remuneration: bool = False
    stcg: bool = False
    ltcg_112a: float = Money
    other_capital_gains: bool = False
    agricultural_income: float = Money
    director: bool = False
    unlisted_equity: bool = False
    foreign_assets_or_income: bool = False
    tds_194n: bool = False
    esop_tax_deferred: bool = False
    losses_to_carry_forward: bool = False
    files_under_139_4a_to_4d: bool = False
    claims_section_11: bool = False
    accounts_audited: bool = False
    assessment_year: AssessmentYear = "2026-27"


@router.post("/itr-form")
def itr_form(p: ProfileIn):
    return incometax.select_itr(incometax.TaxpayerProfile(**p.model_dump(exclude={"assessment_year"})))


class DocsIn(BaseModel):
    upload_ids: list[str] = Field(min_length=1, max_length=10)


@router.post("/itr-from-uploads")
def itr_from_uploads(req: DocsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Read the user's uploaded tax documents for the facts that decide the ITR form.

    Returns each fact with its evidence (file, page/line or cell, masked text), what is only
    suggested, and the questions no document answers. The form itself is chosen by /itr-form from
    the answers the user confirms; nothing here is assumed."""
    lines, documents = [], []
    for uid in dict.fromkeys(req.upload_ids):
        try:
            up = service.get_upload(db, user.id, uid)
        except service.UploadError as e:
            raise HTTPException(400, str(e)) from e
        if up is None:
            raise HTTPException(404, "Upload not found.")
        own = taxdocs.lines_of(up.analysis or {}, up.name)
        lines += own
        notes = list((up.analysis or {}).get("warnings", []))
        if up.status != "processed":
            notes.insert(0, up.error or "The file could not be read.")
        elif not own:
            notes.insert(0, "No readable text was found (a scanned PDF needs OCR, which is not configured here).")
        documents.append({"upload_id": up.id.hex, "file": up.name, "label": up.label, "lines_read": len(own), "types": [], "notes": notes[:5]})
    facts, types = taxdocs.extract(lines)
    by_file = {t["file"]: t["types"] for t in types}
    for d in documents:
        d["types"] = by_file.get(d["file"], [])
    order = list(taxdocs.QUESTIONS)
    return {
        "documents": documents,
        "facts": [{"field": f.field, "question": taxdocs.QUESTIONS[f.field], "value": f.value, "status": f.status, "note": f.note,
                   "evidence": f.evidence} for f in sorted(facts.values(), key=lambda f: order.index(f.field))],
        "unanswered": [{"field": k, "question": q} for k, q in taxdocs.QUESTIONS.items() if k not in facts],
        "rules": "Rule-based reading: 'found' means the document states it; 'suggested' needs your confirmation. "
                 "Questions no document answers keep your own answers.",
    }


# ---------------------------------------------------------------- tax audit (s.44AB, Forms 3CA/3CB + 3CD)
OptMoney = Field(default=None, ge=0, le=1e15)


class AuditIn(BaseModel):
    taxpayer_type: Literal["individual", "huf", "firm", "llp", "company", "aop_boi", "cooperative", "local_authority",
                           "trust_or_institution"] = "individual"
    activity: Literal["business", "profession", "both"] = "business"
    business_turnover: float | None = OptMoney
    professional_receipts: float | None = OptMoney
    cash_receipts: float | None = OptMoney
    total_receipts: float | None = OptMoney
    cash_payments: float | None = OptMoney
    total_payments: float | None = OptMoney
    presumptive: Literal["none", "44AD", "44ADA", "44AE", "44BB", "44BBB"] = "none"
    profit_below_presumptive: bool = False
    opted_out_of_44ad: bool = False
    total_income: float | None = Field(default=None, ge=-1e15, le=1e15)
    regime: Literal["new", "old"] = "new"
    age: Literal["below_60", "60_to_79", "80_plus"] = "below_60"
    resident: bool = True
    audited_under_other_law: bool | None = None
    name: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=500)
    pan: str = Field(default="", max_length=10, pattern=r"^([A-Za-z]{5}\d{4}[A-Za-z])?$")
    gstin: str = Field(default="", max_length=15, pattern=r"^(\d{2}[A-Za-z]{5}\d{4}[A-Za-z][0-9A-Za-z][Zz][0-9A-Za-z])?$")
    nature: str = Field(default="", max_length=300)
    upload_ids: list[str] = Field(default_factory=list, max_length=10)
    assessment_year: AssessmentYear = "2026-27"


GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z])\b")
ENTITY_LINE = re.compile(r"gstin|gst no|gst registration|registration no", re.I)


def _audit(req: AuditIn, user: User, db: Session) -> dict:
    items: dict[str, dict] = {}
    dues: list[dict] = []
    ledgers: list[dict] = []
    documents: list[dict] = []
    gstins: dict[str, dict] = {}
    for uid in dict.fromkeys(req.upload_ids):
        try:
            up = service.get_upload(db, user.id, uid)
        except service.UploadError as e:
            raise HTTPException(400, str(e)) from e
        if up is None:
            raise HTTPException(404, "Upload not found.")
        a = up.analysis or {}
        used: list[str] = []
        notes: list[str] = [] if up.status == "processed" else [up.error or "The file could not be read."]
        lg = None
        n_dues = len(dues)
        if up.status == "processed" and up.extension in (".xlsx", ".xlsm", ".csv", ".tsv", ".txt"):
            data = service.original_bytes(db, up)
            if data:
                try:
                    lg = ledger.read_ledger(up.name, data)
                except Exception as e:  # corrupt workbook: report, never fail the whole draft
                    notes.append(f"Could not read it as a ledger ({type(e).__name__}).")
        if lg and lg["rows"]:
            chk = taxaudit.ledger_checks(lg["rows"], up.name)
            chk.update(sheet=lg["sheet"], columns=lg["columns"], skipped=lg["skipped"], mode_source=lg["mode_source"],
                       direction_rule=lg["direction_rule"])
            ledgers.append(chk)
            used.append(f"Ledger: {len(lg['rows'])} transactions")
            if lg["mode_source"] == "cash book":
                notes.append("No payment-mode column: every row was taken as cash because the file or sheet is called a cash book.")
            elif not lg["mode_source"]:
                notes.append("No payment-mode column, so cash transactions could not be identified.")
        else:
            mapped = suggest_statement_mapping(a.get("sheets", []), up.name, all_items=True)
            for m in mapped:
                if m["item"] not in items:
                    items[m["item"]] = m
            if mapped:
                used.append(f"Statement lines: {len(mapped)}")
            for sh in a.get("sheets", []):
                for s in sh.get("series", []):
                    lab = s.get("label") or ""
                    if s.get("orientation") != "row" or not taxaudit.STAT_DUE.search(lab) or not taxaudit.DUE_WORDS.search(lab) \
                            or taxaudit.NOT_43B.search(lab):
                        continue
                    pairs = [(v, r) for v, r in zip(s["values"], s["refs"]) if v is not None]
                    if pairs and pairs[-1][0]:
                        dues.append({"label": lab, "value": pairs[-1][0], "source": f"{up.name} › {sh['name']} › {pairs[-1][1]}"})
            for line in taxdocs.lines_of(a, up.name):
                if not ENTITY_LINE.search(line.text):
                    continue
                for g in GSTIN_RE.findall(line.text.upper()):
                    gstins.setdefault(g, {"raw": g, "masked": taxaudit.mask_gstin(g),
                                          "evidence": {"file": line.file, "where": line.where, "text": taxdocs.mask(GSTIN_RE.sub(lambda m: taxaudit.mask_gstin(m.group(1)), line.text.upper()))[:160]}})
        if len(dues) > n_dues:
            used.append(f"Statutory dues payable: {len(dues) - n_dues}")
        documents.append({"upload_id": up.id.hex, "file": up.name, "used_for": used or ["Nothing usable for the tax audit"], "notes": notes[:4]})

    d = req.model_dump(exclude={"name", "address", "pan", "gstin", "nature", "upload_ids", "assessment_year"})
    inputs: list[dict] = []
    rev = items.get("revenue")
    if rev and req.activity != "both":
        key = "professional_receipts" if req.activity == "profession" else "business_turnover"
        if d[key] is None and rev["value"] is not None and rev["value"] >= 0:
            d[key] = rev["value"]
            d["turnover_source"] = rev["source"]
            inputs.append({"field": key, "value": rev["value"], "source": rev["source"]})
    full = [lg for lg in ledgers if lg.get("cash_known")]
    if full:
        src = ", ".join(lg["file"] for lg in full)
        for k in ("cash_receipts", "cash_payments"):
            if d[k] is None:
                d[k] = sum(lg[k] for lg in full)
                inputs.append({"field": k, "value": d[k], "source": src})
        if all(lg["totals_complete"] for lg in full):
            for k in ("total_receipts", "total_payments"):
                if d[k] is None:
                    d[k] = sum(lg[k] for lg in full)
                    inputs.append({"field": k, "value": d[k], "source": src})
        d["cash_source"] = src
    profile = taxaudit.AuditProfile(**d)
    app = taxaudit.applicability(profile)

    pan = req.pan.upper()
    gl = list(gstins.values())
    if req.gstin:
        g = req.gstin.upper()
        gl.insert(0, {"raw": g, "masked": taxaudit.mask_gstin(g), "evidence": {"file": "You entered", "where": "Assessee details"}})
    if pan:  # keep only GSTINs that belong to this PAN
        gl = [x for x in gl if x["evidence"]["file"] == "You entered" or x["raw"][2:12] == pan]
    entity = {"name": req.name.strip(), "address": req.address.strip(), "pan_masked": taxdocs.mask(pan) if pan else "",
              "taxpayer_type": req.taxpayer_type, "nature": req.nature.strip(),
              "gstins": [{k: v for k, v in x.items() if k != "raw"} for x in gl[:5]]}
    clauses = taxaudit.clauses_3cd(entity, app, items, ledgers, dues, req.presumptive)
    counts: dict[str, int] = {}
    for c in clauses:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return clean({
        "year": taxaudit.YEAR, "ruleset": taxaudit.RULESET, "applicability": app, "due": taxaudit.due(dt.date.today()),
        "entity": {k: v for k, v in entity.items() if k != "gstins"} | {"gstins": [x["masked"] for x in gl[:5]]},
        "inputs_from_files": inputs, "documents": documents, "ledgers": ledgers,
        "report_3cb": taxaudit.draft_3cb(entity, app["form"]), "clauses": clauses, "counts": counts,
        "status_labels": taxaudit.SUMMARY, "sources": taxaudit.SOURCES,
        "notes": ["A draft for your chartered accountant: only a CA in practice can sign the report and upload it with a UDIN.",
                  "From tax year 2026-27 the Income-tax Act, 2025 moves the audit to section 63 (Form 26); this draft is for FY 2025-26."],
    })


@router.post("/audit")
def audit(req: AuditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tax audit check and Form 3CB / 3CD draft from the user's answers and uploaded books."""
    return _audit(req, user, db)


@router.post("/audit/draft.docx")
def audit_docx(req: AuditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    body = build_docx(_audit(req, user, db))
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="tax-audit-draft-AY2026-27.docx"'})


@router.get("/audit/ledger-template")
def ledger_template():
    return Response(ledger.TEMPLATE, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="cash-book-template.csv"'})


class IndividualIn(BaseModel):
    taxpayer_type: Literal["individual", "huf"] = "individual"
    age: Literal["below_60", "60_to_79", "80_plus"] = "below_60"
    resident: bool = True
    salary: float = Money
    house_property: float = Field(default=0.0, ge=-1e13, le=1e13)
    business: float = Money
    other_sources: float = Money
    dividends: float = Money
    stcg_111a: float = Money
    ltcg_112a: float = Money
    ltcg_112: float = Money
    winnings_115bb: float = Money
    deductions_old: dict[Literal["80C", "80CCC", "80CCD(1)", "80CCD(1B)", "80D", "80E", "80G", "80TTA", "80TTB", "other"],
                         float] = Field(default_factory=dict)
    employer_nps_80ccd2: float = Money
    tds_and_advance_tax: float = Money
    count_special_income_for_rebate: bool = True
    assessment_year: AssessmentYear = "2026-27"


@router.post("/individual")
def individual(req: IndividualIn):
    return clean(incometax.individual_tax(incometax.IndividualIncome(**req.model_dump(exclude={"assessment_year"}))))


class EntityIn(BaseModel):
    entity: Literal["company", "firm", "llp", "cooperative"] = "company"
    total_income: float = Money
    turnover_fy_2023_24: float | None = Field(default=None, ge=0, le=1e15)
    book_profit: float | None = Field(default=None, ge=0, le=1e15)
    total_income_115baa: float | None = Field(default=None, ge=0, le=1e15)
    manufacturing_115bab_eligible: bool = False
    adjusted_total_income_amt: float | None = Field(default=None, ge=0, le=1e15)
    assessment_year: AssessmentYear = "2026-27"


@router.post("/entity")
def entity(req: EntityIn):
    return clean(incometax.entity_tax(incometax.EntityIncome(**req.model_dump(exclude={"assessment_year"}))))


class DueIn(BaseModel):
    category: Literal["no_business", "business_no_audit", "audit", "transfer_pricing"] | None = None
    filing_date: dt.date | None = None
    total_income: float | None = Field(default=None, ge=0, le=1e15)
    tax_unpaid: float | None = Field(default=None, ge=0, le=1e15)
    regime: Literal["new", "old"] = "new"
    age: Literal["below_60", "60_to_79", "80_plus"] = "below_60"
    resident: bool = True


@router.post("/due-dates")
def due(req: DueIn):
    return incometax.due_dates(req.category, req.filing_date, req.total_income, req.tax_unpaid, req.regime, req.age, req.resident)


# ---------------------------------------------------------------- GST
@gst_router.get("/info")
def gst_info():
    return {"states": gst.STATES, "ruleset": gst.RULESET, "sources": gst.SOURCES, "filing_steps": gst.FILING_STEPS,
            "filing_note": "Filing through software needs a licensed GST Suvidha Provider and the taxpayer's API consent. "
                           "Use these figures on the GST portal, or the Returns Offline Tool for GSTR-1."}


class GSTProfileIn(BaseModel):
    registration: Literal["regular", "composition", "non_resident", "oidar", "isd", "tds_deductor", "tcs_operator", "uin",
                          "not_registered"] = "regular"
    state_code: str = Field(default="27", min_length=1, max_length=2)
    aggregate_turnover_prev_fy: float = Field(ge=0, le=1e15)  # required: it decides QRMP, GSTR-9/9C and thresholds
    aggregate_turnover_current_fy: float | None = Field(default=None, ge=0, le=1e15)
    supplies: Literal["goods", "services", "both"] = "goods"
    composition_kind: Literal["trader", "manufacturer", "restaurant", "services"] = "trader"
    qrmp: bool = False
    year: int = Field(default=2026, ge=2017, le=2100)
    month: int = Field(default=9, ge=1, le=12)


@gst_router.post("/returns")
def returns(p: GSTProfileIn):
    return gst.select_returns(gst.GSTProfile(**p.model_dump()))


class HeadsIn(BaseModel):
    igst: float = Money
    cgst: float = Money
    sgst: float = Money
    cess: float = Money


class GSTR3BIn(BaseModel):
    outward_tax: HeadsIn = HeadsIn()
    reverse_charge_tax: HeadsIn = HeadsIn()
    eco_9_5_tax: HeadsIn = HeadsIn()
    itc_available: HeadsIn = HeadsIn()
    itc_reversed: HeadsIn = HeadsIn()
    opening_credit: HeadsIn = HeadsIn()
    taxable_value_month: float | None = Field(default=None, ge=0, le=1e15)
    rule_86b_applies: bool = False
    rule_86b_exempt: bool = False
    filing_date: dt.date | None = None
    due_date: dt.date | None = None
    nil_return: bool = False
    aggregate_turnover: float | None = Field(default=None, ge=0, le=1e15)


@gst_router.post("/gstr3b")
def gstr3b(req: GSTR3BIn):
    d = req.model_dump()
    for k in ("outward_tax", "reverse_charge_tax", "eco_9_5_tax", "itc_available", "itc_reversed", "opening_credit"):
        d[k] = gst.Heads(**d[k])
    return clean(gst.gstr3b(gst.GSTR3BIn(**d)))


async def _register(f: UploadFile, settings: Settings, user: User) -> dict:
    if not limiter.hit(f"gst-file:{user.id}", 120, 3600):
        raise HTTPException(429, "Too many files in the last hour. Try again later.")
    data = await f.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File exceeds the {settings.fis_max_upload_mb} MB limit.")
    if not data:
        raise HTTPException(422, f"{f.filename or 'The file'} is empty.")
    try:
        return read_register(f.filename or "", data)
    except FinanceInputError:
        raise
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # corrupt or password-protected workbook
        raise HTTPException(422, f"The file could not be read ({type(e).__name__}). Save it as .xlsx or .csv and try again.") from e


def _invoice(r: dict) -> gst.Invoice:
    return gst.Invoice(number=r.get("number") or "", date=r.get("date"), gstin=r.get("gstin"), place_of_supply=r.get("place_of_supply"),
                       taxable_value=r.get("taxable_value"), rate=r.get("rate"), igst=r.get("igst"), cgst=r.get("cgst"),
                       sgst=r.get("sgst"), cess=r.get("cess") or 0.0, hsn=r.get("hsn"), doc_type=r.get("doc_type") or "invoice",
                       category=r.get("category") or "regular", invoice_value=r.get("invoice_value"), row=r.get("row"))


def _purchase(r: dict) -> gst.Purchase:
    return gst.Purchase(gstin=r.get("gstin") or "", number=r.get("number") or "", date=r.get("date"),
                        taxable_value=r.get("taxable_value") or 0.0, igst=r.get("igst") or 0.0, cgst=r.get("cgst") or 0.0,
                        sgst=r.get("sgst") or 0.0, cess=r.get("cess") or 0.0, row=r.get("row"))


@gst_router.post("/gstr1")
async def gstr1(file: UploadFile = File(...), supplier_gstin: str = Form(..., max_length=15),
                aggregate_turnover: float | None = Form(default=None, ge=0, le=1e15),
                period: str | None = Form(default=None, max_length=7),
                settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    reg = await _register(file, settings, user)
    out = gst.gstr1([_invoice(r) for r in reg["rows"]], supplier_gstin, aggregate_turnover, period or None)
    out["file"] = {"name": file.filename, "sheet": reg["sheet"], "columns": reg["columns"], "rows": len(reg["rows"]), "skipped": reg["skipped"]}
    return clean(out)


@gst_router.post("/reconcile")
async def reconcile(books: UploadFile = File(...), gstr2b: UploadFile = File(...),
                    tolerance: float = Form(default=1.0, ge=0, le=1000),
                    settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    b = await _register(books, settings, user)
    p = await _register(gstr2b, settings, user)
    out = gst.reconcile_2b([_purchase(r) for r in b["rows"]], [_purchase(r) for r in p["rows"]], tolerance)
    out["files"] = {"books": {"name": books.filename, "rows": len(b["rows"]), "columns": b["columns"]},
                    "gstr2b": {"name": gstr2b.filename, "rows": len(p["rows"]), "columns": p["columns"]}}
    return clean(out)


@gst_router.get("/template/{kind}")
def template(kind: Literal["sales", "purchases"]):
    body = SALES_TEMPLATE if kind == "sales" else PURCHASE_TEMPLATE
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{kind}-register-template.csv"'})
