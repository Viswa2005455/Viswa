"""Finance calculation endpoints. All rates are decimals (0.10 = 10%)."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import Field, model_validator

from ..finance import FinanceInputError, forecasting, ratios, sensitivity, tvm, valuation_range, variance
from ..finance.cost_of_capital import capm, wacc
from ..finance.dcf import OUTPUTS, SENSITIVITY_VARIABLES, DCFInputs, run_dcf
from .base import BaseModel

router = APIRouter(prefix="/api/finance", tags=["finance"])

# Rates are decimals (0.10 = 10%). Above 100% is refused so a percentage typed as 10 is not read as 1000%.
Rate = Field(ge=-0.99, le=1)


def clean(obj):
    """Make results JSON-safe: NaN/inf -> None (never silently zero)."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


# ---------------------------------------------------------------- Investment appraisal

class AppraisalRequest(BaseModel):
    cash_flows: list[float] = Field(min_length=2, max_length=101, description="CF0 (t=0, usually negative) then CF1..CFn")
    discount_rate: float = Rate
    finance_rate: float | None = Field(default=None, ge=-0.99, le=1)
    reinvest_rate: float | None = Field(default=None, ge=-0.99, le=1)


@router.post("/appraisal")
def appraisal(req: AppraisalRequest):
    cf, r = req.cash_flows, req.discount_rate
    irr_res = tvm.irr(cf)
    finance = req.finance_rate if req.finance_rate is not None else r
    reinvest = req.reinvest_rate if req.reinvest_rate is not None else r
    try:
        mirr_val, mirr_err = tvm.mirr(cf, finance, reinvest), None
    except FinanceInputError as e:
        mirr_val, mirr_err = None, str(e)
    try:
        pi, pi_err = tvm.profitability_index(r, cf), None
    except FinanceInputError as e:
        pi, pi_err = None, str(e)
    pb, dpb = tvm.payback_period(cf), tvm.discounted_payback_period(r, cf)

    timeline, cum, cum_d = [], 0.0, 0.0
    for t, c in enumerate(cf):
        df = tvm.discount_factor(r, t)
        cum += c
        cum_d += c * df
        timeline.append({"t": t, "cash_flow": c, "discount_factor": df, "present_value": c * df,
                         "cumulative": cum, "cumulative_discounted": cum_d})

    # NPV profile over a rate range that brackets the IRR(s) and the chosen rate.
    hi = max([0.3, r * 2] + [x * 1.5 for x in irr_res.irrs if x > 0])
    hi = min(hi, 3.0)
    profile = [{"rate": x, "npv": tvm.npv(x, cf)} for x in (i * hi / 60 for i in range(0, 61))]

    value = tvm.npv(r, cf)
    return clean({
        "inputs": req.model_dump(),
        "convention": "CF0 occurs today (t = 0) and is not discounted "
                      "(Excel's NPV() discounts its first argument; use =CF0 + NPV(r, CF1:CFn) to match).",
        "npv": value,
        "decision": "Accept: NPV > 0 adds value at this discount rate." if value > 0 else
                    "Reject: NPV < 0 destroys value at this discount rate." if value < 0 else "Indifferent: NPV = 0.",
        "irr": {"status": irr_res.status, "values": irr_res.irrs, "sign_changes": irr_res.sign_changes, "message": irr_res.message},
        "mirr": {"value": mirr_val, "finance_rate": finance, "reinvest_rate": reinvest, "error": mirr_err},
        "payback": {"period": pb.period, "message": pb.message},
        "discounted_payback": {"period": dpb.period, "message": dpb.message},
        "profitability_index": {"value": pi, "error": pi_err},
        "eaa": tvm.equivalent_annual_annuity(r, cf),
        "timeline": timeline,
        "npv_profile": profile,
    })


# ---------------------------------------------------------------- Cost of capital

class CAPMRequest(BaseModel):
    risk_free: float = Rate
    beta: float = Field(ge=-5, le=10)
    market_return: float = Rate


@router.post("/capm")
def capm_endpoint(req: CAPMRequest):
    re_ = capm(req.risk_free, req.beta, req.market_return)
    return {"cost_of_equity": re_, "market_risk_premium": req.market_return - req.risk_free,
            "steps": f"{req.risk_free:.4f} + {req.beta:.3f} × ({req.market_return:.4f} − {req.risk_free:.4f}) = {re_:.4f}"}


class WACCRequest(BaseModel):
    equity_value: float = Field(ge=0)
    debt_value: float = Field(ge=0)
    cost_of_equity: float = Rate
    pre_tax_cost_of_debt: float = Rate
    tax_rate: float = Field(ge=0, lt=1)


@router.post("/wacc")
def wacc_endpoint(req: WACCRequest):
    return clean(asdict(wacc(req.equity_value, req.debt_value, req.cost_of_equity, req.pre_tax_cost_of_debt, req.tax_rate)))


# ---------------------------------------------------------------- DCF

class DCFRequest(BaseModel):
    base_revenue: float = Field(gt=0)
    revenue_growth: list[Annotated[float, Field(gt=-1, le=5)]] = Field(min_length=1, max_length=30)
    ebit_margin: list[Annotated[float, Field(ge=-5, le=1)]] = Field(min_length=1, max_length=30)
    tax_rate: float = Field(ge=0, lt=1)
    da_pct_revenue: float = Field(ge=0, le=1)
    capex_pct_revenue: float = Field(ge=0, le=2)
    nwc_pct_revenue: float = Field(ge=-1, le=2)
    wacc: float = Field(gt=-0.99, le=1)
    terminal_growth: float = Field(default=0.02, ge=-0.5, le=0.5)
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    exit_multiple: float | None = Field(default=None, gt=0, le=200)
    debt: float = Field(default=0, ge=0)
    cash: float = Field(default=0, ge=0)
    shares_outstanding: float | None = Field(default=None, gt=0)
    mid_year: bool = False

    def to_inputs(self) -> DCFInputs:
        return DCFInputs(**self.model_dump())


@router.post("/dcf")
def dcf_endpoint(req: DCFRequest):
    return clean(asdict(run_dcf(req.to_inputs())))


class SensitivityRequest(BaseModel):
    model: DCFRequest
    x_variable: str
    x_values: list[float] = Field(min_length=1, max_length=20)
    y_variable: str
    y_values: list[float] = Field(min_length=1, max_length=20)
    output: str = "enterprise_value"

    @model_validator(mode="after")
    def check(self):
        for v in (self.x_variable, self.y_variable):
            if v not in SENSITIVITY_VARIABLES:
                raise ValueError(f"Unknown variable '{v}'.")
        if self.output not in OUTPUTS:
            raise ValueError(f"Unknown output '{self.output}'.")
        return self


@router.get("/dcf/variables")
def dcf_variables():
    return {"variables": SENSITIVITY_VARIABLES, "outputs": list(OUTPUTS)}


@router.post("/dcf/sensitivity")
def dcf_sensitivity(req: SensitivityRequest):
    base = req.model.to_inputs()
    grid = sensitivity.two_way(base, req.x_variable, req.x_values, req.y_variable, req.y_values, req.output)
    base_out = OUTPUTS[req.output](run_dcf(base))
    return clean({"x_variable": req.x_variable, "x_values": req.x_values, "y_variable": req.y_variable,
                  "y_values": req.y_values, "output": req.output, "base_output": base_out,
                  "base_x": sensitivity.get_variable(base, req.x_variable),
                  "base_y": sensitivity.get_variable(base, req.y_variable),
                  "grid": [[asdict(c) for c in row] for row in grid]})


class TornadoRequest(BaseModel):
    model: DCFRequest
    ranges: dict[str, tuple[float, float]]
    output: str = "enterprise_value"


@router.post("/dcf/tornado")
def dcf_tornado(req: TornadoRequest):
    for v in req.ranges:
        if v not in SENSITIVITY_VARIABLES:
            raise FinanceInputError(f"Unknown variable '{v}'.")
    base_out, bars = sensitivity.tornado(req.model.to_inputs(), req.ranges, req.output)
    return clean({"base_output": base_out, "output": req.output, "bars": [asdict(b) for b in bars]})


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    revenue_growth_shift: float = Field(default=0, ge=-1, le=1)
    ebit_margin_shift: float = Field(default=0, ge=-1, le=1)
    overrides: dict[str, float] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    model: DCFRequest
    scenarios: list[ScenarioIn] = Field(min_length=1, max_length=60)


@router.post("/dcf/scenarios")
def dcf_scenarios(req: ScenarioRequest):
    base = req.model.to_inputs()
    results = []
    for s in req.scenarios:
        try:
            inp = sensitivity.apply_scenario(base, sensitivity.ScenarioDef(s.name, s.revenue_growth_shift, s.ebit_margin_shift, s.overrides))
            r = run_dcf(inp)
            last = r.years[-1]
            results.append({"name": s.name, "error": None, "inputs": asdict(inp), "enterprise_value": r.enterprise_value,
                            "equity_value": r.equity_value, "value_per_share": r.value_per_share,
                            "final_revenue": last.revenue, "final_ebitda": last.ebitda, "final_ebit": last.ebit,
                            "final_nopat": last.nopat, "final_fcff": last.fcff,
                            "cumulative_fcff": sum(y.fcff for y in r.years), "terminal_share": r.terminal_value_share_of_ev,
                            "years": [asdict(y) for y in r.years], "warnings": r.warnings})
        except FinanceInputError as e:
            results.append({"name": s.name, "error": str(e)})
    return clean({"scenarios": results})


# ---------------------------------------------------------------- Variance

class VarianceLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["revenue", "expense"]
    budget: float
    actual: float
    group: str | None = None
    source: str | None = None


class VarianceRequest(BaseModel):
    lines: list[VarianceLineIn] = Field(min_length=1, max_length=2000)
    materiality_pct: float | None = Field(default=10, ge=0)
    materiality_abs: float | None = Field(default=None, ge=0)


@router.post("/variance")
def variance_endpoint(req: VarianceRequest):
    rep = variance.analyse([l.model_dump() for l in req.lines], req.materiality_pct, req.materiality_abs)
    sources = {l.name: l.source for l in req.lines}

    def ser(l):
        d = asdict(l)
        for k in ("budget", "actual", "variance", "variance_pct", "profit_impact"):
            d[k] = float(d[k]) if d[k] is not None else None
        d["source"] = sources.get(l.name)
        return d

    return {"policy": {
                "absolute": "Actual − Budget",
                "percentage": "(Actual − Budget) / |Budget| × 100; not shown when the budget is zero.",
                "favourable": "Revenue above budget or expense below budget."},
            "lines": [ser(l) for l in rep.lines],
            "totals": {k: ser(v) for k, v in rep.totals.items()},
            "largest_contributors": [ser(l) for l in rep.largest_contributors]}


class PriceVolumeRequest(BaseModel):
    budget_price: float
    budget_quantity: float = Field(ge=0)
    actual_price: float
    actual_quantity: float = Field(ge=0)


@router.post("/variance/price-volume")
def price_volume(req: PriceVolumeRequest):
    r = variance.sales_price_volume(req.budget_price, req.budget_quantity, req.actual_price, req.actual_quantity)
    return {k: float(v) for k, v in asdict(r).items()}


# ---------------------------------------------------------------- Ratios

class RatioRequest(BaseModel):
    data: dict[str, float | None]
    period_days: int = Field(default=365, ge=1, le=366)


@router.get("/ratios/items")
def ratio_items():
    return {"items": ratios.ITEMS, "averageable": sorted(ratios.AVERAGEABLE)}


@router.post("/ratios")
def ratios_endpoint(req: RatioRequest):
    unknown = [k for k in req.data if k.removesuffix("_prior") not in ratios.ITEMS]
    if unknown:
        raise FinanceInputError(f"Unknown statement items: {', '.join(unknown)}")
    return clean({"ratios": [asdict(r) for r in ratios.compute_ratios(req.data, req.period_days)]})


# ---------------------------------------------------------------- Forecasting

class ForecastRequest(BaseModel):
    series: list[float | None] = Field(min_length=2, max_length=600)
    method: Literal["linear", "moving_average", "ses", "cagr"] = "linear"
    horizon: int = Field(default=6, ge=1, le=60)
    confidence: float = Field(default=0.95, ge=0.5, lt=1)
    window: int = Field(default=3, ge=1, le=60)
    alpha: float | None = Field(default=None, gt=0, le=1)
    holdout: int | None = Field(default=None, ge=1, le=60)


@router.post("/forecast")
def forecast_endpoint(req: ForecastRequest):
    r = forecasting.forecast(req.series, req.method, req.horizon, confidence=req.confidence,
                             window=req.window, alpha=req.alpha, holdout=req.holdout)
    return clean(asdict(r))


class BreakEvenRequest(BaseModel):
    model: DCFRequest
    variable: str
    output: str = "enterprise_value"
    target: float
    low: float
    high: float

    @model_validator(mode="after")
    def check(self):
        if self.variable not in SENSITIVITY_VARIABLES:
            raise ValueError(f"Unknown variable '{self.variable}'.")
        if self.output not in OUTPUTS:
            raise ValueError(f"Unknown output '{self.output}'.")
        if self.low >= self.high:
            raise ValueError("The search range low value must be below the high value.")
        return self


@router.post("/dcf/break-even")
def dcf_break_even(req: BreakEvenRequest):
    base = req.model.to_inputs()
    value = sensitivity.break_even(base, req.variable, req.output, req.target, req.low, req.high)
    return {"variable": req.variable, "output": req.output, "target": req.target, "value": value,
            "base_value": sensitivity.get_variable(base, req.variable),
            "message": None if value is not None else
            "No value in the search range produces the target (the output does not cross the target there)."}


# ---------------------------------------------------------------- Reverse DCF and valuation range

class ReverseDCFRequest(BaseModel):
    model: DCFRequest
    target: float = Field(description="Market price per share (or market equity / enterprise value)")
    variable: Literal["revenue_growth", "ebit_margin", "terminal_growth", "wacc", "exit_multiple"] = "revenue_growth"
    output: Literal["value_per_share", "equity_value", "enterprise_value"] = "value_per_share"


@router.post("/dcf/reverse")
def dcf_reverse(req: ReverseDCFRequest):
    return clean(asdict(valuation_range.reverse_dcf(req.model.to_inputs(), req.target, req.variable, req.output)))


class DistributionIn(BaseModel):
    variable: str
    kind: Literal["normal", "triangular", "uniform"]
    a: float
    b: float
    c: float | None = None
    clip_low: float | None = None
    clip_high: float | None = None


class MonteCarloRequest(BaseModel):
    model: DCFRequest
    distributions: list[DistributionIn] = Field(min_length=1, max_length=9)
    output: Literal["value_per_share", "equity_value", "enterprise_value"] = "value_per_share"
    simulations: int = Field(default=5000, ge=100, le=20000)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    target: float | None = None


@router.post("/dcf/monte-carlo")
def dcf_monte_carlo(req: MonteCarloRequest):
    dists = [valuation_range.Distribution(**d.model_dump()) for d in req.distributions]
    r = valuation_range.monte_carlo(req.model.to_inputs(), dists, req.output, req.simulations, req.seed, req.target)
    return clean(asdict(r))
