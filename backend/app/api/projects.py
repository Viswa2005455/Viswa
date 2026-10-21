"""Projects, saved models (with version history) and activity history.

Access control: every query is filtered by the signed-in user's id. Requests for another
user's object return 404, so ids cannot be probed.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import current_user, log_activity
from ..config import Settings, get_settings
from ..db.models import Activity, Project, SavedItem, SavedVersion, Upload, User, utcnow
from ..db.session import get_db

router = APIRouter(prefix="/api", tags=["projects"])

Kind = Literal["dcf", "scenarios", "budget", "statements", "cash_budget", "variance", "ratios", "forecast", "investment", "costing",
               "accounting", "investments"]
MAX_SAVED_BYTES = 2 * 1024 * 1024


def own_project(db: Session, user: User, project_id: uuid.UUID | str | None) -> Project | None:
    if project_id in (None, ""):
        return None
    try:
        pid = uuid.UUID(str(project_id))
    except ValueError:
        raise HTTPException(404, "Project not found.")
    p = db.scalar(select(Project).where(Project.id == pid, Project.user_id == user.id))
    if not p:
        raise HTTPException(404, "Project not found.")
    return p


def project_out(p: Project, uploads: int = 0, saved: int = 0) -> dict:
    return {"id": str(p.id), "name": p.name, "description": p.description, "currency": p.currency, "units": p.units,
            "archived": p.archived, "created_at": p.created_at, "updated_at": p.updated_at, "uploads": uploads, "saved_items": saved}


# ---------------------------------------------------------------- projects

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    units: str = Field(default="lakhs", max_length=20)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    units: str | None = Field(default=None, max_length=20)
    archived: bool | None = None


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.archived, Project.updated_at.desc())).all()
    up = dict(db.execute(select(Upload.project_id, func.count()).where(Upload.user_id == user.id).group_by(Upload.project_id)).all())
    sv = dict(db.execute(select(SavedItem.project_id, func.count()).where(SavedItem.user_id == user.id).group_by(SavedItem.project_id)).all())
    return {"projects": [project_out(p, up.get(p.id, 0), sv.get(p.id, 0)) for p in projects],
            "unassigned": {"uploads": up.get(None, 0), "saved_items": sv.get(None, 0)}}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(Project).where(Project.user_id == user.id)) >= 200:
        raise HTTPException(422, "Project limit reached (200).")
    p = Project(user_id=user.id, name=body.name.strip(), description=body.description, currency=body.currency, units=body.units)
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already have a project with this name.")
    log_activity(db, user.id, "project.created", project_id=p.id, entity_type="project", entity_id=str(p.id), name=p.name)
    db.commit()
    return project_out(p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, user, project_id)
    uploads = db.scalars(select(Upload).where(Upload.user_id == user.id, Upload.project_id == p.id).order_by(Upload.uploaded_at.desc())).all()
    saved = db.scalars(select(SavedItem).where(SavedItem.user_id == user.id, SavedItem.project_id == p.id).order_by(SavedItem.updated_at.desc())).all()
    return {**project_out(p, len(uploads), len(saved)),
            "upload_list": [{"id": u.id.hex, "name": u.name, "label": u.label, "size": u.size, "uploaded_at": u.uploaded_at,
                             "expires_at": u.expires_at, "status": u.status, "summary": u.summary} for u in uploads],
            "saved_list": [saved_out(s) for s in saved]}


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, user, project_id)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(p, k, v.strip() if isinstance(v, str) and k == "name" else v)
    p.updated_at = utcnow()
    try:
        log_activity(db, user.id, "project.updated", project_id=p.id, entity_type="project", entity_id=str(p.id), fields=sorted(changes))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already have a project with this name.")
    return project_out(p)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Deletes the project, its saved models and its uploaded files."""
    p = own_project(db, user, project_id)
    ids = db.scalars(select(Upload.id).where(Upload.user_id == user.id, Upload.project_id == p.id)).all()
    db.execute(delete(Upload).where(Upload.user_id == user.id, Upload.project_id == p.id))
    name = p.name
    db.delete(p)
    log_activity(db, user.id, "project.deleted", entity_type="project", entity_id=str(project_id), name=name, uploads=len(ids))
    db.commit()
    return {"deleted": True, "uploads_deleted": len(ids)}


def export_payload(db: Session, user_id: uuid.UUID, project_id: uuid.UUID | None) -> dict:
    def scope(model):
        q = select(model).where(model.user_id == user_id)
        return q.where(model.project_id == project_id) if project_id else q

    projects = [db.get(Project, project_id)] if project_id else db.scalars(select(Project).where(Project.user_id == user_id)).all()
    items = db.scalars(scope(SavedItem)).all()
    return {
        "format": "finance-intelligence-studio-export",
        "version": 1,
        "exported_at": utcnow(),
        "note": "Uploaded file contents are not included; download originals separately if needed.",
        "projects": [project_out(p) for p in projects],
        "saved_items": [{**saved_out(s), "versions": [{"version": v.version, "note": v.note, "created_at": v.created_at, "data": v.data}
                                                      for v in s.versions]} for s in items],
        "uploads": [{"id": u.id.hex, "project_id": str(u.project_id) if u.project_id else None, "name": u.name, "label": u.label,
                     "size": u.size, "sha256": u.sha256, "uploaded_at": u.uploaded_at, "expires_at": u.expires_at,
                     "summary": u.summary, "recommendations": u.recommendations} for u in db.scalars(scope(Upload)).all()],
        "activity": [{"action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "detail": a.detail,
                      "created_at": a.created_at} for a in db.scalars(scope(Activity).order_by(Activity.created_at)).all()],
    }


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, user, project_id)
    payload = export_payload(db, user.id, p.id)
    log_activity(db, user.id, "project.exported", project_id=p.id, entity_type="project", entity_id=str(p.id))
    db.commit()
    return payload


# ---------------------------------------------------------------- saved models

def saved_out(s: SavedItem) -> dict:
    return {"id": str(s.id), "kind": s.kind, "name": s.name, "project_id": str(s.project_id) if s.project_id else None,
            "latest_version": s.latest_version, "created_at": s.created_at, "updated_at": s.updated_at}


def own_saved(db: Session, user: User, item_id: str) -> SavedItem:
    try:
        iid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(404, "Saved item not found.")
    s = db.scalar(select(SavedItem).where(SavedItem.id == iid, SavedItem.user_id == user.id))
    if not s:
        raise HTTPException(404, "Saved item not found.")
    return s


def _size(data: dict) -> int:
    n = len(json.dumps(data, default=str))
    if n > MAX_SAVED_BYTES:
        raise HTTPException(413, "Saved data is larger than 2 MB.")
    return n


class SaveIn(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    data: dict
    note: str = Field(default="", max_length=200)


class VersionIn(BaseModel):
    data: dict
    note: str = Field(default="", max_length=200)


@router.get("/saved")
def list_saved(kind: Kind | None = None, project_id: str | None = Query(default=None), user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    q = select(SavedItem).where(SavedItem.user_id == user.id)
    if kind:
        q = q.where(SavedItem.kind == kind)
    if project_id:
        q = q.where(SavedItem.project_id == own_project(db, user, project_id).id)
    return {"items": [saved_out(s) for s in db.scalars(q.order_by(SavedItem.updated_at.desc())).all()]}


@router.post("/saved", status_code=201)
def create_saved(body: SaveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, user, body.project_id)
    s = SavedItem(user_id=user.id, project_id=p.id if p else None, kind=body.kind, name=body.name.strip(), latest_version=1)
    s.versions.append(SavedVersion(version=1, note=body.note, data=body.data, size=_size(body.data)))
    db.add(s)
    db.flush()
    log_activity(db, user.id, "model.saved", project_id=s.project_id, entity_type=body.kind, entity_id=str(s.id), name=s.name, version=1)
    db.commit()
    return {**saved_out(s), "data": body.data}


@router.get("/saved/{item_id}")
def get_saved(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = own_saved(db, user, item_id)
    latest = s.versions[-1]
    return {**saved_out(s), "data": latest.data,
            "versions": [{"version": v.version, "note": v.note, "created_at": v.created_at, "size": v.size} for v in reversed(s.versions)]}


@router.get("/saved/{item_id}/versions/{version}")
def get_version(item_id: str, version: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = own_saved(db, user, item_id)
    v = next((v for v in s.versions if v.version == version), None)
    if not v:
        raise HTTPException(404, "Version not found.")
    return {**saved_out(s), "version": v.version, "note": v.note, "created_at": v.created_at, "data": v.data}


@router.put("/saved/{item_id}")
def add_version(item_id: str, body: VersionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = own_saved(db, user, item_id)
    if len(s.versions) >= 200:
        raise HTTPException(422, "Version limit reached (200). Save as a new item instead.")
    s.latest_version += 1
    s.versions.append(SavedVersion(version=s.latest_version, note=body.note, data=body.data, size=_size(body.data)))
    s.updated_at = utcnow()
    log_activity(db, user.id, "model.saved", project_id=s.project_id, entity_type=s.kind, entity_id=str(s.id), name=s.name, version=s.latest_version)
    db.commit()
    return saved_out(s)


class SavedPatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.patch("/saved/{item_id}")
def rename_saved(item_id: str, body: SavedPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = own_saved(db, user, item_id)
    s.name = body.name.strip()
    db.commit()
    return saved_out(s)


@router.delete("/saved/{item_id}")
def delete_saved(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = own_saved(db, user, item_id)
    log_activity(db, user.id, "model.deleted", project_id=s.project_id, entity_type=s.kind, entity_id=str(s.id), name=s.name)
    db.delete(s)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------- history

LABELS = {
    "account.created": "Account created", "account.signed_in": "Signed in", "account.password_changed": "Password changed",
    "account.sessions_revoked": "Signed out other devices", "account.exported": "Exported all data", "account.data_deleted": "Deleted all data",
    "project.created": "Project created", "project.updated": "Project updated", "project.deleted": "Project deleted",
    "project.exported": "Project exported", "upload.created": "File uploaded", "upload.deleted": "File deleted",
    "upload.expired": "File removed by retention policy", "upload.moved": "File moved", "model.saved": "Model saved", "model.deleted": "Saved model deleted",
}


@router.get("/activity")
def activity(project_id: str | None = None, limit: int = Query(default=100, ge=1, le=500), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    q = select(Activity).where(Activity.user_id == user.id)
    if project_id:
        q = q.where(Activity.project_id == own_project(db, user, project_id).id)
    rows = db.scalars(q.order_by(Activity.created_at.desc(), Activity.id.desc()).limit(limit)).all()
    return {"activity": [{"action": a.action, "label": LABELS.get(a.action, a.action), "entity_type": a.entity_type, "entity_id": a.entity_id,
                          "project_id": str(a.project_id) if a.project_id else None, "detail": a.detail, "created_at": a.created_at} for a in rows]}
