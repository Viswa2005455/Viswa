"""Live share prices and the market-risk check. Calls go to the configured provider from the server."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from ..auth.deps import current_user
from ..auth.security import limiter
from ..config import Settings, get_settings
from ..db.models import User
from ..files.registers import read_prices
from ..finance import stock_risk
from ..market.providers import MarketError, get_market_provider
from .finance import clean

router = APIRouter(prefix="/api/market", tags=["market"])
SYMBOL = re.compile(r"^[A-Za-z0-9&^=_\-]{1,24}(\.[A-Za-z0-9]{1,10})?$")
# Benchmarks offered by default (EODHD index codes).
BENCHMARKS = {"NSE": "NSEI.INDX", "BSE": "BSESN.INDX", "US": "GSPC.INDX", "LSE": "FTSE.INDX"}
LICENCE = ("Free and personal provider plans are for the key holder's own use. If other people use a hosted copy of this app, "
           "the provider's commercial licence is needed before they see the data.")
Profile = Literal["conservative", "balanced", "aggressive"]


def _provider(settings: Settings, user: User):
    p = get_market_provider(settings)
    if p is None:
        raise HTTPException(503, "Live prices are not set up. Add FIS_MARKET_PROVIDER and FIS_MARKET_API_KEY to backend/.env, "
                                 "or upload a price file instead.")
    if not limiter.hit(f"market:{user.id}", 300, 3600):
        raise HTTPException(429, "Too many market requests in the last hour. Try again later.")
    return p


def _sym(s: str) -> str:
    s = s.strip().upper()
    if not SYMBOL.match(s):
        raise HTTPException(422, "Symbols look like RELIANCE.NSE, 500325.BSE, AAPL.US or BP.LSE.")
    return s


def _call(fn, *a):
    try:
        return fn(*a)
    except MarketError as e:
        raise HTTPException(e.status, str(e)) from e


@router.get("/status")
def status(settings: Settings = Depends(get_settings)):
    p = get_market_provider(settings)
    return {"configured": p is not None, "provider": p.name if p else None, "label": p.label if p else None,
            "attribution": p.attribution if p else None, "licence": LICENCE, "benchmarks": BENCHMARKS,
            "demo": bool(p and p.key == "demo")}


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=40), settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    p = _provider(settings, user)
    return {"results": _call(p.search, q.strip())}


@router.get("/quote")
def quote(symbol: str = Query(max_length=40), settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    p = _provider(settings, user)
    return clean({**asdict(_call(p.quote, _sym(symbol))), "attribution": p.attribution})


def _history(p, symbol: str, years: int) -> dict:
    end = dt.date.today()
    return _call(p.history, symbol, end - dt.timedelta(days=int(365.25 * years)), end)


@router.get("/history")
def history(symbol: str = Query(max_length=40), years: int = Query(default=5, ge=1, le=30),
            settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    p = _provider(settings, user)
    return clean({"symbol": _sym(symbol), **_history(p, _sym(symbol), years), "attribution": p.attribution})


@router.get("/risk")
def risk(symbol: str = Query(max_length=40), benchmark: str | None = Query(default=None, max_length=40),
         years: int = Query(default=5, ge=1, le=30), profile: Profile = "balanced",
         risk_free: float = Query(default=0.065, ge=0, lt=1), horizon_years: float = Query(default=5, gt=0, le=50),
         settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    p = _provider(settings, user)
    sym = _sym(symbol)
    h = _history(p, sym, years)
    b = None
    if benchmark:
        b = _history(p, _sym(benchmark), years)
    out = stock_risk.analyse(h["dates"], h["closes"], b["dates"] if b else None, b["closes"] if b else None,
                             risk_free, profile, horizon_years)
    out["prices"] = {"dates": h["dates"], "closes": h["closes"]}
    out["symbol"], out["benchmark"], out["source"] = sym, benchmark, p.attribution
    if h.get("warning"):
        out["warnings"].append(f"Provider: {h['warning']}")
    return clean(out)


@router.post("/risk-from-file")
async def risk_from_file(file: UploadFile = File(...), benchmark_file: UploadFile | None = File(default=None),
                         profile: Profile = Form(default="balanced"), risk_free: float = Form(default=0.065, ge=0, lt=1),
                         horizon_years: float = Form(default=5, gt=0, le=50),
                         settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    if not limiter.hit(f"market-file:{user.id}", 120, 3600):
        raise HTTPException(429, "Too many files in the last hour. Try again later.")

    async def load(f: UploadFile) -> dict:
        data = await f.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(413, f"File exceeds the {settings.fis_max_upload_mb} MB limit.")
        try:
            return read_prices(f.filename or "", data)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except Exception as e:
            raise HTTPException(422, f"The file could not be read ({type(e).__name__}).") from e

    a = await load(file)
    b = await load(benchmark_file) if benchmark_file is not None and benchmark_file.filename else None
    out = stock_risk.analyse(a["dates"], a["closes"], b["dates"] if b else None, b["closes"] if b else None,
                             risk_free, profile, horizon_years)
    out["prices"] = {"dates": a["dates"], "closes": a["closes"]}
    out["source"] = f"Uploaded file {file.filename} ({a['date_column']} / {a['price_column']})"
    if a["unreadable_rows"]:
        out["warnings"].append(f"{a['unreadable_rows']} rows had a date that could not be read and were skipped.")
    return clean(out)
