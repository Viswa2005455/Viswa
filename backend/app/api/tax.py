"""Income tax (AY 2026-27) and GST endpoints. The app prepares computations; it does not file returns."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field

from ..auth.deps import current_user
from ..auth.security import limiter
from ..config import Settings, get_settings
from ..db.models import User
from ..files.registers import PURCHASE_TEMPLATE, SALES_TEMPLATE, read_register
from ..finance import FinanceInputError, gst, incometax
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
