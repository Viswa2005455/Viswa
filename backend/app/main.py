"""Finance Intelligence Studio API.

Run locally:  uv run alembic upgrade head   (first time and after updates)
              uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import asdict
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .ai.provider import get_provider
from .api import accounting, ai, analysis, auth, costing, dashboard, finance, investments, planning, projects, reports, uploads
from .auth.deps import current_user
from .config import get_settings
from .db.session import session_factory
from .files.service import purge_expired
from .finance import FinanceInputError

VERSION = "0.9.0"
log = logging.getLogger("fis")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def run_purge() -> None:
    try:
        with session_factory()() as db:
            result = purge_expired(db, get_settings())
            if any(result.values()):
                log.info("Retention purge: %s", result)
    except Exception:  # never crash the server because of housekeeping
        log.exception("Retention purge failed")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.is_production and "fis_dev_password" in s.database_url:
        raise RuntimeError("Refusing to start in production with the development database password. Set DATABASE_URL.")
    if s.is_production and s.is_sqlite:
        raise RuntimeError("SQLite is for local single-user use only. Use PostgreSQL (DATABASE_URL) in production.")

    async def periodic():
        while True:
            await asyncio.to_thread(run_purge)
            await asyncio.sleep(3600)

    task = asyncio.create_task(periodic())
    try:
        yield
    finally:
        task.cancel()


settings = get_settings()
app = FastAPI(title="Finance Intelligence Studio API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def origin_check(request: Request, call_next):
    """CSRF defence in depth (cookies are also SameSite=Lax): browsers send an Origin header on
    cross-site state-changing requests; reject any that is not this site or an allowed origin."""
    if request.method in UNSAFE_METHODS:
        origin = request.headers.get("origin")
        if origin:
            same_host = urlsplit(origin).netloc == request.headers.get("host", "")
            if not same_host and not get_settings().origin_allowed(origin):
                return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked.", "type": "csrf"})
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if get_settings().is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
    db_ok = True
    try:
        with session_factory()() as db:
            db.execute(text("select 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "version": VERSION, "environment": get_settings().fis_env,
            "database": "ok" if db_ok else "unreachable", "database_engine": "sqlite" if get_settings().is_sqlite else "postgresql"}


@app.get("/api/ai/status", dependencies=[Depends(current_user)])
def ai_status():
    return asdict(get_provider(get_settings()).status())


# Public: sign-up and sign-in. Everything else requires a valid session.
app.include_router(auth.router)
app.include_router(auth.account)
app.include_router(projects.router)
app.include_router(uploads.router)
protected = [Depends(current_user)]
app.include_router(finance.router, dependencies=protected)
app.include_router(planning.router, dependencies=protected)
app.include_router(dashboard.router, dependencies=protected)
app.include_router(analysis.router, dependencies=protected)
app.include_router(ai.router, dependencies=protected)
app.include_router(costing.router, dependencies=protected)
app.include_router(accounting.router, dependencies=protected)
app.include_router(investments.router, dependencies=protected)
app.include_router(reports.router)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def not_found(rest: str):
    raise HTTPException(404, "Not found.")
