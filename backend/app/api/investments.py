"""Investment analytics endpoints (fixed income, equity, portfolio, derivatives)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..finance import FinanceInputError
from ..finance import investments as inv
from .finance import clean

router = APIRouter(prefix="/api/investments", tags=["investments"])


class BondReq(BaseModel):
    face: float = Field(default=100, gt=0)
    coupon_rate: float = Field(ge=0, le=1)
    years: float = Field(gt=0, le=100)
    freq: Literal[1, 2, 4, 12] = 2
    ytm: float | None = Field(default=None, gt=-1, le=2)
    price: float | None = Field(default=None, gt=0)
    shock_bp: float = Field(default=100, gt=0, le=1000)


@router.post("/bond")
def bond(req: BondReq):
    return clean(inv.bond_analytics(**req.model_dump()))


class EquityReq(BaseModel):
    model: Literal["gordon", "two_stage", "fcfe", "residual_income"]
    d0: float | None = None
    d1: float | None = None
    g: float | None = None
    r: float
    g1: float | None = None
    n: int | None = Field(default=None, ge=1, le=50)
    g2: float | None = None
    fcfe0: float | None = None
    shares: float | None = Field(default=None, gt=0)
    book_value: float | None = None
    roe: float | None = None
    payout: float | None = None
    years: int | None = Field(default=None, ge=1, le=50)
    terminal_growth: float | None = None


def _need(req: EquityReq, *names: str):
    missing = [n for n in names if getattr(req, n) is None]
    if missing:
        raise FinanceInputError(f"Missing input(s): {', '.join(missing)}.")


@router.post("/equity")
def equity(req: EquityReq):
    if req.model == "gordon":
        _need(req, "g")
        return clean(inv.gordon(req.d0, req.d1, req.g, req.r))
    if req.model == "two_stage":
        _need(req, "d0", "g1", "n", "g2")
        return clean(inv.two_stage_ddm(req.d0, req.g1, req.n, req.g2, req.r))
    if req.model == "fcfe":
        _need(req, "fcfe0", "g")
        return clean(inv.fcfe_value(req.fcfe0, req.g, req.r, req.shares))
    _need(req, "book_value", "roe", "payout", "years")
    return clean(inv.residual_income(req.book_value, req.roe, req.payout, req.r, req.years, req.terminal_growth, req.shares))


class PortfolioReq(BaseModel):
    weights: list[float] = Field(min_length=1, max_length=20)
    returns: list[float] = Field(min_length=1, max_length=20)
    vols: list[float] = Field(min_length=1, max_length=20)
    corr: list[list[float]] = Field(min_length=1, max_length=20)
    risk_free: float | None = None


@router.post("/portfolio")
def portfolio(req: PortfolioReq):
    return clean(inv.portfolio_stats(req.weights, req.returns, req.vols, req.corr, req.risk_free))


class PerformanceReq(BaseModel):
    portfolio: list[float] = Field(min_length=3, max_length=1000)
    benchmark: list[float] = Field(min_length=3, max_length=1000)
    risk_free: float = 0.0
    periods_per_year: Literal[1, 4, 12, 52, 252] = 12


@router.post("/performance")
def performance(req: PerformanceReq):
    return clean(inv.performance(req.portfolio, req.benchmark, req.risk_free, req.periods_per_year))


class OptionsReq(BaseModel):
    s: float = Field(gt=0)
    k: float = Field(gt=0)
    t: float = Field(gt=0, le=50)
    r: float = Field(gt=-1, le=1)
    sigma: float = Field(gt=0, le=5)
    q: float = Field(default=0, ge=0, le=1)
    steps: int = Field(default=200, ge=1, le=2000)
    market_call: float | None = Field(default=None, ge=0)
    market_put: float | None = Field(default=None, ge=0)


@router.post("/options")
def options(req: OptionsReq):
    args = (req.s, req.k, req.t, req.r, req.sigma)
    out = {"black_scholes": inv.black_scholes(*args, q=req.q),
           "binomial": {f"{style}_{kind}": inv.binomial(*args, steps=req.steps, q=req.q, kind=kind, american=style == "american")["value"]
                        for style in ("american", "european") for kind in ("call", "put")}}
    if req.market_call is not None and req.market_put is not None:
        out["parity"] = inv.put_call_parity(req.market_call, req.market_put, req.s, req.k, req.r, req.t, req.q)
    return clean(out)


class LegIn(BaseModel):
    type: Literal["call", "put", "stock"]
    position: Literal["long", "short"]
    strike: float | None = Field(default=None, ge=0)
    premium: float = Field(default=0, ge=0)
    quantity: float = Field(default=1, gt=0)


class StrategyReq(BaseModel):
    legs: list[LegIn] = Field(min_length=1, max_length=8)
    spot_low: float | None = Field(default=None, ge=0)
    spot_high: float | None = Field(default=None, gt=0)


@router.post("/strategy")
def strategy(req: StrategyReq):
    rng = (req.spot_low, req.spot_high) if req.spot_low is not None and req.spot_high is not None else None
    return clean(inv.strategy_payoff([l.model_dump() for l in req.legs], rng))
