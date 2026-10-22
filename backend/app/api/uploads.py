"""Upload & Analyse endpoints. All operations are scoped to the signed-in user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth.deps import current_user, log_activity
from ..auth.security import limiter
from ..config import Settings, get_settings
from ..db.models import User
from ..db.session import get_db
from ..files import service
from ..files.detect import EXTENSIONS
from .base import BaseModel
from .projects import own_project

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.get("/formats")
def formats(settings: Settings = Depends(get_settings), _: User = Depends(current_user)):
    return {"extensions": {k: {"category": c, "label": l} for k, (c, l) in EXTENSIONS.items()},
            "max_upload_mb": settings.fis_max_upload_mb, "max_files_per_request": settings.fis_max_files_per_request,
            "retention_days": settings.fis_upload_retention_days}


@router.post("")
async def upload(files: list[UploadFile] = File(...), project_id: str | None = Form(default=None),
                 settings: Settings = Depends(get_settings), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(files) > settings.fis_max_files_per_request:
        raise HTTPException(413, f"At most {settings.fis_max_files_per_request} files per upload.")
    project = own_project(db, user, project_id)
    results = []
    for f in files:
        if not limiter.hit(f"upload:{user.id}", 120, 3600):
            results.append({"ok": False, "name": f.filename, "error": "Upload limit reached (120 files per hour). Try again later."})
            continue
        # Read at most limit + 1 bytes so oversized files are rejected without buffering them fully.
        data = await f.read(settings.max_upload_bytes + 1)
        try:
            u = service.save_upload(db, user.id, project.id if project else None, f.filename or "unnamed", data, settings)
            log_activity(db, user.id, "upload.created", project_id=u.project_id, entity_type="upload", entity_id=u.id.hex,
                         name=u.name, status=u.status)
            db.commit()
            results.append({"ok": True, "upload": {k: v for k, v in service.full_out(u).items() if k != "analysis"}})
        except service.UploadError as e:
            db.rollback()
            results.append({"ok": False, "name": f.filename, "error": str(e)})
    return {"results": results}


@router.get("")
def list_all(project_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id)
    return {"uploads": [service.summary_out(u) for u in service.list_uploads(db, user.id, project.id if project else None)]}


@router.get("/series")
def series(project_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id)
    return {"series": service.all_series(db, user.id, project.id if project else None)}


@router.get("/{upload_id}")
def get_one(upload_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        rec = service.get_upload(db, user.id, upload_id)
    except service.UploadError as e:
        raise HTTPException(400, str(e))
    if not rec:
        raise HTTPException(404, "Upload not found.")
    return service.full_out(rec)


@router.delete("/{upload_id}")
def delete(upload_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        rec = service.get_upload(db, user.id, upload_id)
        if not rec:
            raise HTTPException(404, "Upload not found.")
        name, project_id = rec.name, rec.project_id
        service.delete_upload(db, user.id, upload_id)
    except service.UploadError as e:
        raise HTTPException(400, str(e))
    log_activity(db, user.id, "upload.deleted", project_id=project_id, entity_type="upload", entity_id=upload_id, name=name)
    db.commit()
    return {"deleted": upload_id}


class MoveIn(BaseModel):
    project_id: str | None = None


@router.patch("/{upload_id}")
def move(upload_id: str, body: MoveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Move an upload into another project (or out of any project with an empty project_id)."""
    try:
        rec = service.get_upload(db, user.id, upload_id)
    except service.UploadError as e:
        raise HTTPException(400, str(e))
    if not rec:
        raise HTTPException(404, "Upload not found.")
    project = own_project(db, user, body.project_id)
    rec.project_id = project.id if project else None
    log_activity(db, user.id, "upload.moved", project_id=rec.project_id, entity_type="upload", entity_id=upload_id, name=rec.name)
    db.commit()
    return service.summary_out(rec)
