"""Finance Intelligence Studio API.

Run locally:  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai.provider import get_provider
from .api import dashboard, finance, uploads
from .config import get_settings
from .finance import FinanceInputError

VERSION = "0.4.0"
log = logging.getLogger("fis")

settings = get_settings()
app = FastAPI(title="Finance Intelligence Studio API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(FinanceInputError)
async def finance_error(_: Request, exc: FinanceInputError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "type": "finance_input"})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    msg = "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors[:5])
    return JSONResponse(status_code=422, content={"detail": msg, "errors": errors, "type": "validation"})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    # Never leak stack traces or file paths to the client.
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal error. Check the server log.", "type": "server"})


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION, "environment": settings.fis_env}


@app.get("/api/ai/status")
def ai_status():
    return asdict(get_provider(settings).status())


app.include_router(finance.router)
app.include_router(uploads.router)
app.include_router(dashboard.router)
