"""Finance Intelligence Studio API.

Run locally:  uv run alembic upgrade head   (first time and after updates)
              uv run uvicorn app.main:app --reload --port 8000

When frontend/dist exists (npm run build), the same process also serves the website, so a hosted
copy is one service on one address (see Dockerfile and render.yaml).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from .ai.provider import get_provider
from .api import accounting, ai, analysis, auth, costing, dashboard, finance, investments, market, planning, projects, reports, tax, uploads
from .auth.deps import current_user
from .config import get_settings
from .db.session import session_factory
from .files.service import purge_expired
from .finance import FinanceInputError

VERSION = "0.11.0"
log = logging.getLogger("fis")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# The built website has no inline scripts; inline styles are needed by the chart library.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


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
# The interactive API docs are for development; a hosted copy does not publish its API schema.
_docs = not settings.is_production
app = FastAPI(title="Finance Intelligence Studio API", version=VERSION, lifespan=lifespan,
              docs_url="/docs" if _docs else None, redoc_url=None, openapi_url="/openapi.json" if _docs else None)

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
    path = request.url.path
    if path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # file names carry a content hash
    else:
        response.headers["Cache-Control"] = "no-store"
    if not path.startswith("/api/"):
        response.headers["Content-Security-Policy"] = CSP
    if get_settings().is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


class BodyLimit:
    """Rejects request bodies over FIS_MAX_REQUEST_MB with 413 before the app reads them: by the
    Content-Length header, or for chunked bodies (no length) by reading at most the limit first."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = get_settings().max_request_bytes
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            if not declared.isdigit() or int(declared) > limit:
                return await self._reject(send, limit)
            return await self.app(scope, receive, send)
        if b"chunked" not in headers.get(b"transfer-encoding", b"").lower():
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # client went away
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await self._reject(send, limit)
            if not message.get("more_body"):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send, limit: int):
        response = JSONResponse(status_code=413, content={"detail": f"Request is larger than {limit // (1024 * 1024)} MB.",
                                                          "type": "too_large"})
        await response({"type": "http"}, None, send)


app.add_middleware(BodyLimit)


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
app.include_router(tax.router, dependencies=protected)
app.include_router(tax.gst_router, dependencies=protected)
app.include_router(market.router, dependencies=protected)
app.include_router(reports.router)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def not_found(rest: str):
    raise HTTPException(404, "Not found.")


# ---------------------------------------------------------------- the website (production build)
def _frontend_dir() -> Path | None:
    d = Path(get_settings().fis_frontend_dir).resolve()
    return d if (d / "index.html").is_file() else None


@app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def website(path: str):
    """Files of the built website; any other path returns index.html so client-side routes such as
    /red-flags load directly. Paths are resolved and must stay inside the build folder."""
    root = _frontend_dir()
    if root is None:
        raise HTTPException(404, "Website not built. In development open http://localhost:5173 (npm run dev).")
    if path:
        target = (root / path).resolve()
        if target.is_relative_to(root) and target.is_file():
            return FileResponse(target)
        if path.startswith("assets/"):
            raise HTTPException(404, "Not found.")  # a missing hashed file must not come back as HTML
    return FileResponse(root / "index.html")
