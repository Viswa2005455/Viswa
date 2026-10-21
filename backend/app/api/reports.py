"""Report exports: Excel analysis pack (live formulas) and Word report."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.deps import current_user, log_activity
from ..db.models import User
from ..db.session import get_db
from ..reports import builder
from .finance import DCFRequest

router = APIRouter(prefix="/api/reports", tags=["reports"])


class LineIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    statement: Literal["income", "balance", "cashflow"]
    key: str | None = None
    values: list[float | None] = Field(max_length=20)
    source: str | None = Field(default=None, max_length=400)


class ReportReq(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    periods: list[str] = Field(min_length=1, max_length=20)
    lines: list[LineIn] = Field(min_length=1, max_length=400)
    units: str = Field(default="units", max_length=20)
    currency: str = Field(default="INR", max_length=5)
    market: dict[str, list[float | None]] = Field(default_factory=dict)
    dcf: DCFRequest | None = None
    memo: str | None = Field(default=None, max_length=60_000)
    prepared_by: str = Field(default="", max_length=120)
    sections: list[Literal["statements", "ratios", "red_flags", "valuation", "memo"]] = Field(
        default_factory=lambda: ["statements", "ratios", "red_flags", "valuation", "memo"])


def _input(req: ReportReq) -> builder.ReportInput:
    return builder.ReportInput(
        company=req.company, periods=req.periods, units=req.units, currency=req.currency, market=req.market,
        lines=[builder.Line(l.label, l.statement, l.key, l.values, l.source) for l in req.lines],
        dcf=req.dcf.model_dump() if req.dcf else None, memo=req.memo, prepared_by=req.prepared_by, sections=req.sections)


def _filename(company: str, ext: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "-", company).strip("-")[:60] or "company"
    return f"{safe}-analysis.{ext}"


@router.post("/excel")
def excel(req: ReportReq, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = builder.build_excel(_input(req))
    log_activity(db, user.id, "report.exported", format="xlsx", company=req.company)
    db.commit()
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(req.company, "xlsx")}"'})


@router.post("/word")
def word(req: ReportReq, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = builder.build_word(_input(req))
    log_activity(db, user.id, "report.exported", format="docx", company=req.company)
    db.commit()
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(req.company, "docx")}"'})
