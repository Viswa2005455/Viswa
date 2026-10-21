"""Financial accounting and audit schedule endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..finance import accounting as acc
from .finance import clean

router = APIRouter(prefix="/api/accounting", tags=["accounting"])


class BondReq(BaseModel):
    face: float = Field(gt=0)
    coupon_rate: float = Field(ge=0, le=1)
    market_rate: float = Field(gt=-1, le=1)
    years: float = Field(gt=0, le=100)
    payments_per_year: Literal[1, 2, 4, 12] = 2
    perspective: Literal["issuer", "investor"] = "issuer"


@router.post("/bond")
def bond(req: BondReq):
    return clean(acc.bond_schedule(**req.model_dump()))


class LeaseReq(BaseModel):
    payment: float = Field(gt=0)
    periods: int = Field(gt=0, le=600)
    annual_rate: float = Field(gt=-1, le=1)
    periods_per_year: Literal[1, 2, 4, 12] = 1
    timing: Literal["advance", "arrears"] = "advance"
    initial_direct_costs: float = Field(default=0, ge=0)
    incentives: float = Field(default=0, ge=0)
    prepaid: float = Field(default=0, ge=0)
    classification: Literal["finance", "operating"] = "finance"


@router.post("/lease")
def lease(req: LeaseReq):
    return clean(acc.lease_schedule(**req.model_dump()))


class DepReq(BaseModel):
    cost: float
    salvage: float = 0
    life: int = Field(gt=0, le=100)
    method: Literal["straight_line", "ddb", "syd", "units"] = "straight_line"
    units: list[float] | None = Field(default=None, max_length=100)
    ddb_factor: float = Field(default=2.0, gt=0, le=4)
    switch_to_sl: bool = True


@router.post("/depreciation")
def depreciation(req: DepReq):
    return clean(acc.depreciation_schedule(**req.model_dump()))


class SecurityIn(BaseModel):
    kind: Literal["options", "convertible_preferred", "convertible_debt"]
    name: str = Field(min_length=1, max_length=60)
    shares: float = Field(ge=0)
    exercise_price: float | None = None
    preferred_dividends: float | None = None
    interest_after_tax: float | None = None


class EPSReq(BaseModel):
    net_income: float
    preferred_dividends: float = 0
    weighted_shares: float = Field(gt=0)
    average_price: float | None = None
    securities: list[SecurityIn] = Field(default_factory=list, max_length=20)


@router.post("/eps")
def eps(req: EPSReq):
    return clean(acc.eps(req.net_income, req.preferred_dividends, req.weighted_shares, req.average_price,
                         [acc.Dilutive(**s.model_dump()) for s in req.securities]))


class TempDiffIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["asset", "liability"]
    carrying_amount: float
    tax_base: float


class DeferredReq(BaseModel):
    items: list[TempDiffIn] = Field(min_length=1, max_length=50)
    tax_rate: float = Field(ge=0, lt=1)
    current_tax: float | None = None
    opening_net_dtl: float = 0


@router.post("/deferred-tax")
def deferred(req: DeferredReq):
    return clean(acc.deferred_tax([acc.TempDiff(**i.model_dump()) for i in req.items], req.tax_rate, req.current_tax, req.opening_net_dtl))


class MaterialityReq(BaseModel):
    values: dict[str, float | None]
    selected: str
    pct: float
    performance_pct: float = 0.75
    trivial_pct: float = 0.05


@router.post("/materiality")
def materiality(req: MaterialityReq):
    return clean(acc.materiality({k: v for k, v in req.values.items() if v is not None}, req.selected, req.pct,
                                 req.performance_pct, req.trivial_pct))
