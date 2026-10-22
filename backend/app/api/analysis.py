"""Company analysis endpoints: red-flag screens and peer comparison."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..config import Settings, get_settings
from ..db.models import User
from ..db.session import get_db
from ..files import archive, service
from ..files.model_check import check_workbook
from ..files.screener import NotScreener, parse_screener
from ..finance import forensic, peers, profile
from .base import BaseModel
from .finance import clean

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class CompanyData(BaseModel):
    periods: list[str] = Field(min_length=1, max_length=20)
    items: dict[str, list[float | None]] = Field(description="Standard item key -> one value per period (oldest first)")


@router.get("/forensic/items")
def forensic_items():
    return {"items": forensic.LABELS}


@router.post("/forensic")
def forensic_endpoint(req: CompanyData):
    return clean(asdict(forensic.analyse(req.periods, req.items)))


def _excel_bytes(upload_id: str, user: User, db: Session, settings: Settings, purpose: str):
    try:
        up = service.get_upload(db, user.id, upload_id)
    except service.UploadError as e:
        raise HTTPException(400, str(e)) from e
    if up is None:
        raise HTTPException(404, "Upload not found.")
    if not up.name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, f"The {purpose} reads Excel .xlsx or .xlsm files. Save .xls or .csv files as .xlsx first.")
    data = service.original_bytes(db, up)
    if data is None:
        raise HTTPException(404, "The original file is no longer stored.")
    try:
        archive.check_zip_container(data, 10_000, settings.fis_zip_max_uncompressed_mb * 1024 * 1024)
    except Exception as e:
        raise HTTPException(422, f"The workbook could not be opened ({type(e).__name__}).") from e
    return up, data


@router.post("/screener/{upload_id}")
def screener_import(upload_id: str, user: User = Depends(current_user), db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    up, data = _excel_bytes(upload_id, user, db, settings, "Screener import")
    try:
        result = parse_screener(data)
    except NotScreener as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(422, f"The Screener workbook could not be read ({type(e).__name__}).") from e
    return clean({"upload_id": up.id.hex, "file": up.name, **result})


@router.post("/model-check/{upload_id}")
def model_check(upload_id: str, user: User = Depends(current_user), db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)):
    up, data = _excel_bytes(upload_id, user, db, settings, "model checker")
    try:
        report = check_workbook(data)
    except Exception as e:  # malformed workbook: report, never crash
        raise HTTPException(422, f"The workbook could not be checked ({type(e).__name__}).") from e
    return clean({"upload_id": up.id.hex, "name": up.name, **report})


class PeerCompany(CompanyData):
    name: str = Field(min_length=1, max_length=80)


class PeersRequest(BaseModel):
    companies: list[PeerCompany] = Field(min_length=2, max_length=12)


@router.post("/peers")
def peers_endpoint(req: PeersRequest):
    r = peers.compare([peers.CompanyIn(c.name, c.periods, c.items) for c in req.companies])
    return clean(asdict(r))


@router.post("/profile")
def profile_endpoint(req: CompanyData):
    return clean(asdict(profile.build(req.periods, req.items)))
