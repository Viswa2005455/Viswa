"""Upload & Analyse endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..config import Settings, get_settings
from ..files import service
from ..files.detect import EXTENSIONS

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.get("/formats")
def formats(settings: Settings = Depends(get_settings)):
    return {"extensions": {k: {"category": c, "label": l} for k, (c, l) in EXTENSIONS.items()},
            "max_upload_mb": settings.fis_max_upload_mb, "max_files_per_request": settings.fis_max_files_per_request}


@router.post("")
async def upload(files: list[UploadFile] = File(...), settings: Settings = Depends(get_settings)):
    if len(files) > settings.fis_max_files_per_request:
        raise HTTPException(413, f"At most {settings.fis_max_files_per_request} files per upload.")
    results = []
    for f in files:
        # Read at most limit + 1 bytes so oversized files are rejected without buffering them fully.
        data = await f.read(settings.max_upload_bytes + 1)
        try:
            rec = service.save_upload(f.filename or "unnamed", data, settings)
            results.append({"ok": True, "upload": {k: v for k, v in rec.items() if k != "analysis"}})
        except service.UploadError as e:
            results.append({"ok": False, "name": f.filename, "error": str(e)})
    return {"results": results}


@router.get("")
def list_all(settings: Settings = Depends(get_settings)):
    return {"uploads": service.list_uploads(settings)}


@router.get("/series")
def series(settings: Settings = Depends(get_settings)):
    return {"series": service.all_series(settings)}


@router.get("/{upload_id}")
def get_one(upload_id: str, settings: Settings = Depends(get_settings)):
    try:
        rec = service.get_upload(upload_id, settings)
    except service.UploadError as e:
        raise HTTPException(400, str(e))
    if not rec:
        raise HTTPException(404, "Upload not found.")
    return rec


@router.delete("/{upload_id}")
def delete(upload_id: str, settings: Settings = Depends(get_settings)):
    try:
        if not service.delete_upload(upload_id, settings):
            raise HTTPException(404, "Upload not found.")
    except service.UploadError as e:
        raise HTTPException(400, str(e))
    return {"deleted": upload_id}
