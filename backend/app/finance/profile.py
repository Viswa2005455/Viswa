"""Company profile: key performance, return, safety, cash and valuation metrics for every year.

Feeds the company dashboard. Each metric is computed only when its inputs exist for that year
(and the prior year, for growth and average balances); otherwise it is None, never zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import FinanceInputError
from .forensic import _Data, _ok, altman, beneish, piotroski

Num = float | None

METRICS = {
    # key: (label, unit, group, formula)
    "revenue": ("Revenue", "amount", "Scale", "Revenue"),
    "net_income": ("Net profit", "amount", "Scale", "Net income"),
    "ebitda": ("EBITDA", "amount", "Scale", "EBIT + depreciation & amortisation"),
    "free_cash_flow": ("Free cash flow", "amount", "Scale", "Operating cash flow − |CapEx|"),
    "revenue_growth": ("Revenue growth", "%", "Growth", "Revenue_t / Revenue_t−1 − 1"),
    "profit_growth": ("Net profit growth", "%", "Growth", "Net income_t / Net income_t−1 − 1"),
    "ebitda_margin": ("EBITDA margin", "%", "Margins", "EBITDA / Revenue"),
    "operating_margin": ("EBIT margin", "%", "Margins", "EBIT / Revenue"),
    "net_margin": ("Net margin", "%", "Margins", "Net income / Revenue"),
    "employee_cost_pct": ("Employee cost / revenue", "%", "Margins", "Employee cost / Revenue"),
    "roe": ("ROE", "%", "Returns", "Net income / average equity"),
    "roce": ("ROCE", "%", "Returns", "EBIT / average (equity + debt)"),
    "roa": ("ROA", "%", "Returns", "Net income / average total assets"),
    "asset_turnover": ("Asset turnover", "x", "Efficiency", "Revenue / average total assets"),
    "receivable_days": ("Receivable days", "days", "Efficiency", "Receivables / Revenue × 365"),
    "debt_equity": ("Debt / equity", "x", "Safety", "Total debt / Total equity"),
    "interest_cover": ("Interest cover", "x", "Safety", "EBIT / Interest"),
    "cash_conversion": ("Cash conversion", "x", "Cash", "Operating cash flow / Net income"),
    "payout_ratio": ("Dividend payout", "%", "Cash", "Dividends / Net income"),
    "eps": ("EPS", "per_share", "Valuation", "Net income / Shares outstanding"),
    "market_cap": ("Market cap", "amount", "Valuation", "Share price × Shares outstanding"),
    "pe": ("P/E", "x", "Valuation", "Market cap / Net income"),
    "pb": ("P/B", "x", "Valuation", "Market cap / Total equity"),
    "ev_ebitda": ("EV / EBITDA", "x", "Valuation", "(Market cap + Debt − Cash) / EBITDA"),
    "dividend_yield": ("Dividend yield", "%", "Valuation", "Dividends / Market cap"),
}


@dataclass
class Profile:
    periods: list[str]
    series: dict[str, list[Num]]
    metrics: dict[str, dict]
    cagr: dict[str, dict]
    scores: dict[str, dict]
    highlights: list[str]
    derived: list[str] = field(default_factory=list)


def _div(a: Num, b: Num) -> Num:
    return a / b if _ok(a) and _ok(b) and b != 0 else None


def _avg(a: Num, b: Num) -> Num:
    return (a + b) / 2 if _ok(a) and _ok(b) else None


def _cagr(first: Num, last: Num, years: int) -> Num:
    if not (_ok(first) and _ok(last)) or years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def build(periods: list[str], items: dict[str, list[Num]]) -> Profile:
    if not periods:
        raise FinanceInputError("Provide at least one period.")
    d = _Data(periods, items)
    g, n = d.get, d.n
    s: dict[str, list[Num]] = {k: [] for k in METRICS}
    for t in range(n):
        p = t - 1
        rev, ni, ebit, da = g("revenue", t), g("net_income", t), g("operating_income", t), g("depreciation_amortization", t)
        ebitda = ebit + da if _ok(ebit) and _ok(da) else None
        ocf, capex = g("operating_cash_flow", t), g("capex", t)
        eq, debt, cash = g("total_equity", t), g("total_debt", t), g("cash", t)
        mcap = g("market_cap", t)
        ce = lambda i: g("total_equity", i) + g("total_debt", i) if _ok(g("total_equity", i)) and _ok(g("total_debt", i)) else None  # noqa: E731
        vals = {
            "revenue": rev, "net_income": ni, "ebitda": ebitda,
            "free_cash_flow": ocf - abs(capex) if _ok(ocf) and _ok(capex) else None,
            "revenue_growth": (rev / g("revenue", p) - 1) if _ok(rev) and _ok(g("revenue", p)) and g("revenue", p) > 0 else None,
            "profit_growth": (ni / g("net_income", p) - 1) if _ok(ni) and _ok(g("net_income", p)) and g("net_income", p) > 0 else None,
            "ebitda_margin": _div(ebitda, rev), "operating_margin": _div(ebit, rev), "net_margin": _div(ni, rev),
            "employee_cost_pct": _div(g("employee_cost", t), rev),
            "roe": _div(ni, _avg(eq, g("total_equity", p))),
            "roce": _div(ebit, _avg(ce(t), ce(p)) if p >= 0 else None),
            "roa": _div(ni, _avg(g("total_assets", t), g("total_assets", p))),
            "asset_turnover": _div(rev, _avg(g("total_assets", t), g("total_assets", p))),
            "receivable_days": (_div(g("receivables", t), rev) * 365) if _ok(_div(g("receivables", t), rev)) else None,
            "debt_equity": _div(debt, eq) if _ok(eq) and eq > 0 else None,
            "interest_cover": _div(ebit, g("interest_expense", t)) if _ok(g("interest_expense", t)) and g("interest_expense", t) > 0 else None,
            "cash_conversion": _div(ocf, ni) if _ok(ni) and ni > 0 else None,
            "payout_ratio": _div(g("dividends", t), ni) if _ok(ni) and ni > 0 else None,
            "eps": _div(ni, g("shares_outstanding", t)),
            "market_cap": mcap,
            "pe": _div(mcap, ni) if _ok(ni) and ni > 0 else None,
            "pb": _div(mcap, eq) if _ok(eq) and eq > 0 else None,
            "ev_ebitda": _div(mcap + debt - cash, ebitda) if _ok(mcap) and _ok(debt) and _ok(cash) and _ok(ebitda) and ebitda > 0 else None,
            "dividend_yield": _div(g("dividends", t), mcap),
        }
        for k in METRICS:
            v = vals[k]
            s[k].append(v if _ok(v) else None)

    cagr = {}
    for key, label in (("revenue", "Revenue"), ("net_income", "Net profit"), ("eps", "EPS")):
        vs = s[key]
        for yrs in (3, 5, 10):
            if n - 1 >= yrs:
                v = _cagr(vs[n - 1 - yrs], vs[n - 1], yrs)
                cagr[f"{key}_{yrs}y"] = {"label": f"{label} CAGR {yrs}y", "value": v}

    scores = {}
    if n >= 2:
        b, (z2, z), pf = beneish(d, n - 1), altman(d, n - 1), piotroski(d, n - 1)
        scores = {
            "beneish": {"value": b.value, "verdict": b.verdict, "model": b.model},
            "altman_z2": {"value": z2.value, "verdict": z2.verdict},
            "altman_z": {"value": z.value, "verdict": z.verdict},
            "piotroski": {"value": pf.score if pf.tested else None, "tested": pf.tested},
        }

    hl: list[str] = []
    last = n - 1

    def fmt_pct(v):
        return f"{v * 100:.1f}%"

    if (c := cagr.get("revenue_5y", cagr.get("revenue_3y"))) and c["value"] is not None:
        hl.append(f"{c['label']}: {fmt_pct(c['value'])}.")
    if s["net_margin"][last] is not None and n >= 2 and s["net_margin"][last - 1] is not None:
        diff = (s["net_margin"][last] - s["net_margin"][last - 1]) * 100
        hl.append(f"Net margin {fmt_pct(s['net_margin'][last])} in {periods[last]} "
                  f"({'up' if diff >= 0 else 'down'} {abs(diff):.1f} percentage points on the prior year).")
    if s["roe"][last] is not None:
        hl.append(f"ROE {fmt_pct(s['roe'][last])} in {periods[last]}.")
    if s["debt_equity"][last] is not None:
        hl.append(f"Debt/equity {s['debt_equity'][last]:.2f}× ({'low' if s['debt_equity'][last] < 0.5 else 'moderate' if s['debt_equity'][last] < 1.5 else 'high'} leverage).")
    conv = [v for v in s["cash_conversion"] if v is not None]
    if len(conv) >= 2:
        hl.append(f"Operating cash flow averaged {sum(conv) / len(conv):.2f}× net profit across {len(conv)} years.")
    return Profile(periods, s, {k: {"label": a, "unit": u, "group": gr, "formula": f} for k, (a, u, gr, f) in METRICS.items()},
                   cagr, scores, hl, d.derived)
