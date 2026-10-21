"""Overview dashboard data.

Phase 1 only has SAMPLE data. Every response is flagged `is_sample: true` and the UI shows a
"Sample data" badge; sample figures are never mixed with user uploads. The KPIs are still
produced by the real calculation engine (variance, forecasting, ratios).
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from ..finance import forecasting, ratios, variance
from .finance import clean

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

SAMPLE_COMPANY = "Northwind Components Ltd (fictional sample)"
MONTHS = ["Nov-25", "Dec-25", "Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26", "Jul-26", "Aug-26", "Sep-26", "Oct-26"]
REVENUE = [182.0, 191.5, 176.2, 188.9, 205.3, 199.8, 214.6, 221.0, 218.4, 230.7, 238.1, 245.9]
BUDGET_REVENUE = [180, 188, 185, 190, 200, 205, 210, 215, 220, 225, 232, 240]
COGS_PCT = [0.58, 0.58, 0.59, 0.585, 0.575, 0.58, 0.57, 0.57, 0.575, 0.565, 0.565, 0.56]
OPEX = [42.0, 44.5, 41.0, 42.3, 45.1, 44.0, 46.2, 46.8, 47.5, 48.1, 49.0, 50.2]
BUDGET_OPEX = [43, 43, 43, 44, 44, 45, 45, 46, 46, 47, 47, 48]
DA = [6.0] * 6 + [6.4] * 6
OCF = [24.1, 30.2, 18.4, 22.0, 31.5, 27.3, 33.0, 29.8, 31.6, 35.2, 34.0, 38.4]
TAX = 0.25
INTEREST = 1.8


@router.get("/sample")
def sample_dashboard():
    cogs = [r * p for r, p in zip(REVENUE, COGS_PCT)]
    ebitda = [r - c - o for r, c, o in zip(REVENUE, cogs, OPEX)]
    ebit = [e - d for e, d in zip(ebitda, DA)]
    net = [(e - INTEREST) * (1 - TAX) for e in ebit]

    fc = forecasting.forecast(REVENUE, "linear", 6, confidence=0.9)
    rep = variance.analyse([
        {"name": "Revenue", "kind": "revenue", "budget": BUDGET_REVENUE[-1], "actual": REVENUE[-1]},
        {"name": "Cost of goods sold", "kind": "expense", "budget": round(BUDGET_REVENUE[-1] * 0.57, 2), "actual": round(cogs[-1], 2)},
        {"name": "Operating expenses", "kind": "expense", "budget": BUDGET_OPEX[-1], "actual": OPEX[-1]},
    ])
    ytd = variance.analyse([
        {"name": "Revenue", "kind": "revenue", "budget": sum(BUDGET_REVENUE), "actual": sum(REVENUE)},
        {"name": "Operating expenses", "kind": "expense", "budget": sum(BUDGET_OPEX), "actual": sum(OPEX)},
    ])
    rs = {r.key: r for r in ratios.compute_ratios({
        "revenue": sum(REVENUE), "cogs": sum(cogs), "operating_income": sum(ebit), "depreciation_amortization": sum(DA),
        "interest_expense": INTEREST * 12, "net_income": sum(net), "operating_cash_flow": sum(OCF),
        "current_assets": 610, "current_liabilities": 340, "inventory": 190, "cash": 140, "receivables": 260,
        "accounts_payable": 175, "total_assets": 1480, "total_assets_prior": 1390, "total_debt": 320, "total_equity": 820,
        "total_equity_prior": 760, "inventory_prior": 176, "receivables_prior": 238, "accounts_payable_prior": 160,
    })}
    health = [{"key": k, "name": rs[k].name, "value": rs[k].value, "unit": rs[k].unit, "interpretation": rs[k].interpretation}
              for k in ("current_ratio", "quick_ratio", "net_margin", "roe", "debt_to_equity", "interest_coverage", "ccc")]

    return clean({
        "is_sample": True,
        "company": SAMPLE_COMPANY,
        "currency": "INR",
        "units": "lakhs",
        "period": f"{MONTHS[0]} to {MONTHS[-1]}",
        "kpis": {
            "revenue": {"value": REVENUE[-1], "prior": REVENUE[-2], "label": f"Revenue ({MONTHS[-1]})"},
            "ebitda": {"value": ebitda[-1], "prior": ebitda[-2], "label": f"EBITDA ({MONTHS[-1]})"},
            "net_income": {"value": net[-1], "prior": net[-2], "label": f"Net income ({MONTHS[-1]})"},
            "operating_cash_flow": {"value": OCF[-1], "prior": OCF[-2], "label": f"Operating cash flow ({MONTHS[-1]})"},
            "budget_variance": {"value": float(rep.totals["profit"].variance),
                                "pct": float(rep.totals["profit"].variance_pct) if rep.totals["profit"].variance_pct is not None else None,
                                "status": rep.totals["profit"].status, "label": f"Profit vs budget ({MONTHS[-1]})"},
        },
        "trend": [{"period": m, "revenue": r, "ebitda": e, "net_income": n, "budget_revenue": b, "type": "actual"}
                  for m, r, e, n, b in zip(MONTHS, REVENUE, ebitda, net, BUDGET_REVENUE)],
        "forecast": [{"period": f"F+{i + 1}", "revenue": p, "lower": lo, "upper": hi, "type": "forecast"}
                     for i, (p, lo, hi) in enumerate(zip(fc.forecast, fc.lower, fc.upper))],
        "forecast_method": "Linear trend, 90% prediction interval",
        "budget_vs_actual": [{"period": m, "budget": b, "actual": a} for m, b, a in zip(MONTHS, BUDGET_REVENUE, REVENUE)],
        "ytd_variance": [{"name": l.name, "budget": float(l.budget), "actual": float(l.actual), "variance": float(l.variance),
                          "variance_pct": float(l.variance_pct) if l.variance_pct is not None else None, "status": l.status}
                         for l in ytd.lines],
        "health": health,
        "insights": [
            f"Revenue grew {(REVENUE[-1] / REVENUE[0] - 1):.1%} over the 12 sample months.",
            f"Latest month profit is {rep.totals['profit'].status.replace('_', ' ')} to budget by "
            f"{abs(float(rep.totals['profit'].variance)):.1f} lakhs.",
            f"Cash conversion cycle is {rs['ccc'].value:.0f} days.",
            "These insights are computed from fictional sample data, not from your files.",
        ],
        "ratio_details": [asdict(rs[k]) for k in ("current_ratio", "net_margin", "roe")],
    })
