"""Upload orchestration: validate, parse, recommend, store.

Storage:
  PostgreSQL `uploads` table   metadata + parsed analysis, owned by one user (user_id)
  storage/uploads/<uuid>.bin   original bytes, named only by the server-generated id

Every read, list and delete is filtered by user_id. Uploads expire after the configured
retention period (FIS_UPLOAD_RETENTION_DAYS) and are purged with their files.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db.models import Activity, AuthSession, Upload, utcnow
from . import archive, documents, tabular
from .detect import EXTENSIONS, detect, safe_display_name
from .routing import recommend, suggest_statement_mapping, suggest_statements, suggest_variance_lines

ID_LEN = 32


class UploadError(ValueError):
    pass


def _parse(name: str, ext: str, category: str, label: str, data: bytes, settings: Settings) -> dict:
    max_unc = settings.fis_zip_max_uncompressed_mb * 1024 * 1024
    if ext in (".xlsx", ".xlsm", ".docx"):
        archive.check_zip_container(data, 10_000, max_unc)
    if category == "spreadsheet":
        return tabular.parse_xls(data) if ext == ".xls" else tabular.parse_xlsx(data)
    if category == "table":
        return tabular.parse_delimited(data, "\t" if ext == ".tsv" else None)
    if category == "pdf":
        return documents.parse_pdf(data)
    if category == "word":
        return documents.parse_docx(data)
    if category == "word_legacy":
        return {"kind": "document", "text": "", "warnings": [
            "Legacy .doc files cannot be read directly. Open the file in Word or LibreOffice and save it as .docx, then upload again."]}
    if category == "text":
        return documents.parse_text(data, label)
    if category == "data":
        return documents.parse_structured(data, ext, label)
    if category == "notebook":
        return documents.parse_notebook(data)
    if category == "code":
        return documents.parse_code(data, ext, label)
    if category == "binary_data":
        return {"kind": "binary", "warnings": [f"{label} files are binary; previews are not supported yet."]}
    if category == "archive":
        return _parse_zip(data, settings)
    raise UploadError(f"No parser for {label}.")


def _parse_zip(data: bytes, settings: Settings) -> dict:
    zf = archive.check_zip_container(data, settings.fis_zip_max_entries, settings.fis_zip_max_uncompressed_mb * 1024 * 1024)
    members = archive.list_members(zf)
    children = []
    for m in members:
        if m["is_dir"] or m["blocked"]:
            continue
        name = safe_display_name(m["name"])
        ext = Path(name.lower()).suffix
        if ext == ".zip":
            m["note"] = "Nested archives are listed but not opened."
            continue
        if ext not in EXTENSIONS or len(children) >= 25:
            continue
        content = zf.read(m["name"])
        det = detect(name, content[:8192])
        if det.error:
            m["note"] = det.error
            continue
        try:
            parsed = _parse(name, det.extension, det.category, det.label, content, settings)
            children.append({"path": m["name"], "label": det.label, "category": det.category,
                             "summary": _summary(parsed), "parsed": parsed})
        except Exception as e:  # one bad member should not fail the archive
            m["note"] = f"Could not parse: {type(e).__name__}"
    warnings = [f"Blocked '{m['name']}' ({m['blocked']})." for m in members if m["blocked"]]
    return {"kind": "archive", "members": members, "children": children, "warnings": warnings}


def _summary(parsed: dict) -> str:
    k = parsed.get("kind")
    if k == "tabular" or parsed.get("sheets"):
        sheets = parsed.get("sheets", [])
        rows = sum(s["n_rows"] for s in sheets)
        base = f"{len(sheets)} table(s), {rows:,} rows"
        if k == "document":
            return f"{parsed.get('page_count', parsed.get('paragraph_count', 0))} page(s)/paragraph(s), " + base
        return base
    if k == "document":
        if "paragraph_count" in parsed:
            return f"{parsed['paragraph_count']} paragraph(s)"
        if "page_count" in parsed:
            return f"{parsed['page_count']} page(s)"
        return f"{parsed.get('line_count', 0):,} lines"
    if k == "code":
        return f"{parsed.get('language')}, {parsed.get('line_count', len(parsed.get('cells', [])))} lines/cells"
    if k == "data":
        return f"{parsed.get('format')} ({'valid' if parsed.get('valid') else 'invalid'})"
    if k == "archive":
        return f"{len(parsed.get('members', []))} entries, {len(parsed.get('children', []))} analysed"
    return "Stored"


def file_path(settings: Settings, upload_id: uuid.UUID) -> Path:
    return settings.upload_dir / f"{upload_id.hex}.bin"


def parse_upload_id(upload_id: str) -> uuid.UUID:
    # ids are server-generated hex; reject anything else so an id can never form a path
    if len(upload_id) != ID_LEN or any(c not in "0123456789abcdef" for c in upload_id):
        raise UploadError("Invalid upload id.")
    return uuid.UUID(hex=upload_id)


def summary_out(u: Upload) -> dict:
    return {"id": u.id.hex, "name": u.name, "extension": u.extension, "category": u.category, "label": u.label, "size": u.size,
            "uploaded_at": u.uploaded_at, "expires_at": u.expires_at, "status": u.status, "error": u.error, "summary": u.summary,
            "recommendations": u.recommendations, "project_id": str(u.project_id) if u.project_id else None}


def full_out(u: Upload) -> dict:
    return {**summary_out(u), "sha256": u.sha256, "statement_mapping": u.statement_mapping, "variance_lines": u.variance_lines,
            "statements": u.statements, "analysis": u.analysis}


def save_upload(db: Session, user_id: uuid.UUID, project_id: uuid.UUID | None, filename: str, data: bytes, settings: Settings) -> Upload:
    if len(data) > settings.max_upload_bytes:
        raise UploadError(f"File exceeds the {settings.fis_max_upload_mb} MB limit.")
    if not data:
        raise UploadError("File is empty.")
    name = safe_display_name(filename)
    det = detect(name, data[:8192])
    if det.error:
        raise UploadError(det.error)

    status, error = "processed", None
    try:
        parsed = _parse(name, det.extension, det.category, det.label, data, settings)
    except archive.UnsafeArchive as e:
        raise UploadError(str(e)) from e
    except Exception as e:
        parsed = {"kind": "error", "warnings": []}
        status = "failed"
        error = f"The file could not be parsed ({type(e).__name__}). It may be corrupt, password-protected or in an unexpected format."

    sheets = parsed.get("sheets", []) or []
    now = utcnow()
    u = Upload(
        id=uuid.uuid4(), user_id=user_id, project_id=project_id, name=name, extension=det.extension, category=det.category,
        label=det.label, size=len(data), sha256=hashlib.sha256(data).hexdigest(), status=status, error=error,
        summary=_summary(parsed) if status == "processed" else error,
        recommendations=recommend(det.category, parsed) if status == "processed" else [],
        statement_mapping=suggest_statement_mapping(sheets, name), variance_lines=suggest_variance_lines(sheets, name),
        statements=suggest_statements(sheets, name), analysis=_json_safe(parsed), uploaded_at=now,
        expires_at=now + dt.timedelta(days=settings.fis_upload_retention_days),
    )
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    file_path(settings, u.id).write_bytes(data)
    db.add(u)
    return u


def _json_safe(obj):
    """Analysis must be JSON-serialisable for the database (dates -> ISO strings, NaN -> None)."""
    import json
    import math

    def default(o):
        if isinstance(o, (dt.date, dt.datetime, dt.time)):
            return o.isoformat()
        return str(o)

    def clean(o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return o

    return json.loads(json.dumps(clean(obj), default=default))


def get_upload(db: Session, user_id: uuid.UUID, upload_id: str) -> Upload | None:
    uid = parse_upload_id(upload_id)
    return db.scalar(select(Upload).where(Upload.id == uid, Upload.user_id == user_id))


def list_uploads(db: Session, user_id: uuid.UUID, project_id: uuid.UUID | None = None, unassigned: bool = False) -> list[Upload]:
    q = select(Upload).where(Upload.user_id == user_id)
    if project_id:
        q = q.where(Upload.project_id == project_id)
    elif unassigned:
        q = q.where(Upload.project_id.is_(None))
    return list(db.scalars(q.order_by(Upload.uploaded_at.desc())).all())


def delete_upload(db: Session, user_id: uuid.UUID, upload_id: str, settings: Settings) -> bool:
    u = get_upload(db, user_id, upload_id)
    if not u:
        return False
    db.delete(u)
    file_path(settings, u.id).unlink(missing_ok=True)
    return True


def all_series(db: Session, user_id: uuid.UUID, project_id: uuid.UUID | None = None) -> list[dict]:
    """Every numeric series across the user's uploads, with source references, for analysis pickers."""
    out = []
    for rec in list_uploads(db, user_id, project_id):
        for sheet in (rec.analysis or {}).get("sheets", []) or []:
            for s in sheet.get("series", []):
                if len(s["values"]) < 3:
                    continue
                first, last = s["refs"][0], s["refs"][-1]
                out.append({"upload_id": rec.id.hex, "file": rec.name, "sheet": sheet["name"], "series_id": s["id"],
                            "label": s["label"], "orientation": s["orientation"], "values": s["values"],
                            "period_labels": s["period_labels"], "refs": s["refs"],
                            "source": f"{rec.name} › {sheet['name']} › {first}–{last}"})
    return out


def purge_expired(db: Session, settings: Settings) -> dict:
    """Retention: delete uploads past their expiry (and their files) and expired sessions."""
    now = utcnow()
    expired = db.scalars(select(Upload).where(Upload.expires_at <= now)).all()
    for u in expired:
        db.add(Activity(user_id=u.user_id, project_id=u.project_id, action="upload.expired", entity_type="upload",
                        entity_id=u.id.hex, detail={"name": u.name}))
        db.delete(u)
    sessions = db.execute(delete(AuthSession).where(AuthSession.expires_at <= now)).rowcount
    db.commit()
    for u in expired:
        file_path(settings, u.id).unlink(missing_ok=True)
    return {"uploads_deleted": len(expired), "sessions_deleted": sessions or 0}
