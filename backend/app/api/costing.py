"""Cost & management accounting endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..finance import costing
from .finance import clean

router = APIRouter(prefix="/api/costing", tags=["costing"])


class MaterialIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    std_qty: float
    std_price: float
    actual_qty: float
    actual_price: float


class MaterialsReq(BaseModel):
    materials: list[MaterialIn] = Field(min_length=1, max_length=20)


@router.post("/materials")
def materials(req: MaterialsReq):
    return clean(_ser(costing.material_variances([costing.MaterialIn(**m.model_dump()) for m in req.materials])))


class LabourReq(BaseModel):
    std_hours: float
    std_rate: float
    hours_paid: float
    hours_worked: float
    actual_rate: float


@router.post("/labour")
def labour(req: LabourReq):
    return clean(_ser(costing.labour_variances(**req.model_dump())))


class VOHReq(BaseModel):
    std_hours: float
    std_rate: float
    hours_worked: float
    actual_cost: float


@router.post("/variable-overhead")
def variable_overhead(req: VOHReq):
    return clean(_ser(costing.variable_overhead_variances(**req.model_dump())))


class FOHReq(BaseModel):
    budgeted_cost: float
    actual_cost: float
    budgeted_hours: float
    std_hours: float
    hours_worked: float


@router.post("/fixed-overhead")
def fixed_overhead(req: FOHReq):
    return clean(_ser(costing.fixed_overhead_variances(**req.model_dump())))


class SalesReq(BaseModel):
    budget_qty: float
    budget_price: float
    actual_qty: float
    actual_price: float
    std_margin: float
    margin_basis: str = Field(default="contribution", pattern="^(contribution|profit)$")


@router.post("/sales")
def sales(req: SalesReq):
    return clean(_ser(costing.sales_variances(**req.model_dump())))


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price: float = Field(ge=0)
    variable_cost: float = Field(ge=0)
    mix: float = Field(default=1, ge=0)


class CVPReq(BaseModel):
    products: list[ProductIn] = Field(min_length=1, max_length=20)
    fixed_costs: float
    target_profit: float | None = None
    tax_rate: float = Field(default=0, ge=0, lt=1)
    expected_units: float | None = Field(default=None, ge=0)


@router.post("/cvp")
def cvp(req: CVPReq):
    return clean(costing.cvp([costing.ProductCVP(**p.model_dump()) for p in req.products], req.fixed_costs,
                             req.target_profit, req.tax_rate, req.expected_units))


class AbsorptionReq(BaseModel):
    price: float
    variable_prod_cost: float
    variable_selling_cost: float = 0
    fixed_prod_overhead: float
    normal_units: float
    produced_units: float
    sold_units: float
    opening_units: float = 0
    fixed_selling_admin: float = 0


@router.post("/absorption-vs-marginal")
def absorption(req: AbsorptionReq):
    return clean(costing.absorption_vs_marginal(**req.model_dump()))


class LFIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    contribution_per_unit: float
    resource_per_unit: float
    max_demand: float = Field(ge=0)


class LFReq(BaseModel):
    products: list[LFIn] = Field(min_length=1, max_length=30)
    resource_available: float
    resource_name: str = Field(default="machine hours", max_length=40)
    fixed_costs: float | None = None


@router.post("/limiting-factor")
def lf(req: LFReq):
    return clean(costing.limiting_factor([costing.LFProduct(**p.model_dump()) for p in req.products], req.resource_available,
                                         req.resource_name, req.fixed_costs))


def _ser(r: dict) -> dict:
    return {**r, "variances": [asdict(v) for v in r["variances"]]}
