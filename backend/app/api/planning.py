"""Phase 3 endpoints: budgeting, financial statement analysis, cash flow & working capital."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from ..finance import budgeting, cashflow, statements
from .base import BaseModel
from .finance import clean

router = APIRouter(prefix="/api/finance", tags=["planning"])


def jsonable(obj):
    """Dataclass output -> JSON-safe dict; Decimal -> float only at the API boundary."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


# ---------------------------------------------------------------- Budgeting

class BudgetLine(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["revenue", "expense", "capex"]
    method: Literal["monthly", "annual", "incremental", "driver"]
    department: str = Field(default="General", max_length=60)
    product: str | None = Field(default=None, max_length=60)
    monthly: list[float | None] | None = Field(default=None, max_length=12)
    annual: float | None = None
    prior_actual: float | None = None
    change_pct: float | None = Field(default=None, ge=-100, le=10000)
    quantity: list[float | None] | None = Field(default=None, max_length=12)
    rate: float | None = None
    weights: list[float | None] | None = Field(default=None, max_length=12)
    justification: str | None = Field(default=None, max_length=500)


class BudgetRequest(BaseModel):
    lines: list[BudgetLine] = Field(min_length=1, max_length=500)
    start_month: int = Field(default=4, ge=1, le=12)
    start_year: int = Field(default=2026, ge=1990, le=2100)
    zero_based: bool = False


@router.post("/budget")
def budget(req: BudgetRequest):
    r = budgeting.build_budget([budgeting.BudgetLineIn(**l.model_dump()) for l in req.lines],
                               req.start_month, req.start_year, req.zero_based)
    return jsonable(asdict(r))


class VersionLine(BaseModel):
    name: str
    kind: str
    annual: float


class CompareRequest(BaseModel):
    a: list[VersionLine] = Field(max_length=500)
    b: list[VersionLine] = Field(max_length=500)


@router.post("/budget/compare")
def budget_compare(req: CompareRequest):
    diffs = budgeting.compare_versions([(l.name, l.kind, Decimal(str(l.annual))) for l in req.a],
                                       [(l.name, l.kind, Decimal(str(l.annual))) for l in req.b])
    return {"lines": jsonable([asdict(d) for d in diffs])}


class FlexRequest(BaseModel):
    fixed_cost: float = Field(ge=0)
    variable_cost_per_unit: float = Field(ge=0)
    activity_levels: list[float] = Field(min_length=1, max_length=20)


@router.post("/budget/flexible")
def budget_flexible(req: FlexRequest):
    return {"levels": jsonable([asdict(x) for x in budgeting.flexible_budget(req.fixed_cost, req.variable_cost_per_unit, req.activity_levels)])}


# ---------------------------------------------------------------- Financial statements

class StatementLineIn(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    statement: Literal["income", "balance", "cashflow"]
    values: list[float | None] = Field(max_length=20)
    key: str | None = None
    source: str | None = Field(default=None, max_length=400)


class StatementsRequest(BaseModel):
    periods: list[str] = Field(min_length=1, max_length=20)
    lines: list[StatementLineIn] = Field(min_length=1, max_length=400)


@router.get("/statements/items")
def statement_items():
    return {"items": {k: {"statement": s, "label": l} for k, (s, l) in statements.STANDARD_ITEMS.items()}}


@router.post("/statements")
def statements_endpoint(req: StatementsRequest):
    r = statements.analyse(req.periods, [statements.StatementLine(l.label, l.statement, l.values, l.key or None, l.source) for l in req.lines])
    return clean(asdict(r))


# ---------------------------------------------------------------- Cash flow & working capital

class CashLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    values: list[float | None] = Field(max_length=60)


class CashBudgetRequest(BaseModel):
    periods: list[str] = Field(min_length=1, max_length=60)
    opening_cash: float
    receipts: list[CashLineIn] = Field(default_factory=list, max_length=100)
    payments: list[CashLineIn] = Field(default_factory=list, max_length=100)
    minimum_cash: float = Field(default=0, ge=0)


@router.post("/cash-budget")
def cash_budget(req: CashBudgetRequest):
    r = cashflow.cash_budget(req.periods, req.opening_cash,
                             [cashflow.CashLine(l.name, l.values) for l in req.receipts],
                             [cashflow.CashLine(l.name, l.values) for l in req.payments], req.minimum_cash)
    burn = cashflow.runway(req.opening_cash, [p.net_flow for p in r.periods]) if req.opening_cash >= 0 else None
    out = asdict(r)
    out["runway"] = asdict(burn) if burn else None
    return clean(out)


class RunwayRequest(BaseModel):
    cash: float = Field(ge=0)
    monthly_net_flows: list[float] = Field(min_length=1, max_length=60)


@router.post("/runway")
def runway(req: RunwayRequest):
    return clean(asdict(cashflow.runway(req.cash, req.monthly_net_flows)))


class WCRequest(BaseModel):
    revenue: float
    cogs: float
    receivables: float
    inventory: float
    payables: float
    target_dso: float
    target_dio: float
    target_dpo: float
    days: int = Field(default=365, ge=1, le=366)


@router.post("/working-capital")
def working_capital(req: WCRequest):
    return clean(asdict(cashflow.working_capital(**req.model_dump())))
