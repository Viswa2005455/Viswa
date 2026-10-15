"""Upload orchestration: validate, store under a server-generated id, parse, recommend.

Storage layout (local development; Phase 7 moves metadata to PostgreSQL):
  storage/uploads/<id>.bin   original bytes (never named after the client filename)
  storage/uploads/<id>.json  metadata + parsed analysis
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import uuid
from pathlib import Path

from ..config import Settings
from . import archive, documents, tabular
from .detect import EXTENSIONS, detect, safe_display_name
from .routing import recommend, suggest_statement_mapping, suggest_statements, suggest_variance_lines

_lock = threading.Lock()
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


def save_upload(filename: str, data: bytes, settings: Settings) -> dict:
    if len(data) > settings.max_upload_bytes:
        raise UploadError(f"File exceeds the {settings.fis_max_upload_mb} MB limit.")
    if not data:
        raise UploadError("File is empty.")
    name = safe_display_name(filename)
    det = detect(name, data[:8192])
    if det.error:
        raise UploadError(det.error)

    upload_id = uuid.uuid4().hex
    record = {
        "id": upload_id,
        "name": name,
        "extension": det.extension,
        "category": det.category,
        "label": det.label,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "processed",
        "error": None,
    }
    try:
        parsed = _parse(name, det.extension, det.category, det.label, data, settings)
    except archive.UnsafeArchive as e:
        raise UploadError(str(e)) from e
    except Exception as e:
        parsed = {"kind": "error", "warnings": []}
        record["status"] = "failed"
        record["error"] = f"The file could not be parsed ({type(e).__name__}). It may be corrupt, password-protected or in an unexpected format."

    record["summary"] = _summary(parsed) if record["status"] == "processed" else record["error"]
    record["recommendations"] = recommend(det.category, parsed) if record["status"] == "processed" else []
    record["statement_mapping"] = suggest_statement_mapping(parsed.get("sheets", []), name)
    record["variance_lines"] = suggest_variance_lines(parsed.get("sheets", []), name)
    record["statements"] = suggest_statements(parsed.get("sheets", []), name)
    record["analysis"] = parsed

    d = settings.upload_dir
    with _lock:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{upload_id}.bin").write_bytes(data)
        (d / f"{upload_id}.json").write_text(json.dumps(record, default=str))
    return record


def _path(upload_id: str, settings: Settings, suffix: str) -> Path:
    # ids are server-generated hex; reject anything else so ids can never form a path
    if len(upload_id) != ID_LEN or any(c not in "0123456789abcdef" for c in upload_id):
        raise UploadError("Invalid upload id.")
    return settings.upload_dir / f"{upload_id}{suffix}"


def get_upload(upload_id: str, settings: Settings) -> dict | None:
    p = _path(upload_id, settings, ".json")
    return json.loads(p.read_text()) if p.exists() else None


def list_uploads(settings: Settings) -> list[dict]:
    d = settings.upload_dir
    if not d.exists():
        return []
    items = []
    for p in d.glob("*.json"):
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        items.append({k: r.get(k) for k in ("id", "name", "extension", "category", "label", "size", "uploaded_at",
                                            "status", "error", "summary", "recommendations")})
    return sorted(items, key=lambda r: r["uploaded_at"], reverse=True)


def delete_upload(upload_id: str, settings: Settings) -> bool:
    removed = False
    with _lock:
        for suffix in (".json", ".bin"):
            p = _path(upload_id, settings, suffix)
            if p.exists():
                p.unlink()
                removed = True
    return removed


def all_series(settings: Settings) -> list[dict]:
    """Every numeric series across uploads, with source references, for analysis pickers."""
    out = []
    for item in list_uploads(settings):
        rec = get_upload(item["id"], settings)
        if not rec:
            continue
        for sheet in rec.get("analysis", {}).get("sheets", []) or []:
            for s in sheet.get("series", []):
                if len(s["values"]) < 3:
                    continue
                first, last = s["refs"][0], s["refs"][-1]
                out.append({"upload_id": rec["id"], "file": rec["name"], "sheet": sheet["name"], "series_id": s["id"],
                            "label": s["label"], "orientation": s["orientation"], "values": s["values"],
                            "period_labels": s["period_labels"], "refs": s["refs"],
                            "source": f"{rec['name']} › {sheet['name']} › {first}–{last}"})
    return out
