"""Peer comparison: the same metrics for several companies, side by side, with ranks.

Each company supplies its statements (`periods` oldest -> newest, `items` = standard item ->
values). Metrics use each company's latest period (and the one before it for growth and
average balances). A metric that cannot be calculated for a company is shown as missing and
that company is simply not ranked on it — it is never treated as zero.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from . import FinanceInputError
from .forensic import _Data, _ok, altman, beneish, piotroski

Num = float | None


@dataclass
class MetricDef:
    key: str
    name: str
    group: str
    unit: str  # "%" | "x" | "days" | "amount" | "score"
    better: str  # "higher" | "lower" | "neutral"
    formula: str


METRICS = [
    MetricDef("revenue", "Revenue (latest year)", "Size", "amount", "neutral", "Revenue"),
    MetricDef("revenue_growth", "Revenue growth", "Growth", "%", "higher", "Revenue_t / Revenue_t−1 − 1"),
    MetricDef("revenue_cagr", "Revenue CAGR (all years given)", "Growth", "%", "higher", "(Revenue_last / Revenue_first)^(1/years) − 1"),
    MetricDef("profit_growth", "Net profit growth", "Growth", "%", "higher", "Net income_t / Net income_t−1 − 1"),
    MetricDef("gross_margin", "Gross margin", "Profitability", "%", "higher", "Gross profit / Revenue"),
    MetricDef("ebitda_margin", "EBITDA margin", "Profitability", "%", "higher", "(EBIT + D&A) / Revenue"),
    MetricDef("operating_margin", "Operating (EBIT) margin", "Profitability", "%", "higher", "EBIT / Revenue"),
    MetricDef("net_margin", "Net margin", "Profitability", "%", "higher", "Net income / Revenue"),
    MetricDef("roe", "Return on equity (ROE)", "Returns", "%", "higher", "Net income / average equity"),
    MetricDef("roa", "Return on assets (ROA)", "Returns", "%", "higher", "Net income / average total assets"),
    MetricDef("roce", "Return on capital employed (ROCE)", "Returns", "%", "higher", "EBIT / average (equity + debt)"),
    MetricDef("asset_turnover", "Asset turnover", "Efficiency", "x", "higher", "Revenue / average total assets"),
    MetricDef("receivable_days", "Receivable days (DSO)", "Efficiency", "days", "lower", "Average receivables / Revenue × 365"),
    MetricDef("cash_conversion", "Cash conversion", "Cash quality", "x", "higher", "Operating cash flow / Net income"),
    MetricDef("fcf_margin", "Free cash flow margin", "Cash quality", "%", "higher", "(Operating cash flow − |CapEx|) / Revenue"),
    MetricDef("debt_equity", "Debt / Equity", "Safety", "x", "lower", "Total debt / Total equity"),
    MetricDef("interest_cover", "Interest cover", "Safety", "x", "higher", "EBIT / Interest"),
    MetricDef("current_ratio", "Current ratio", "Safety", "x", "higher", "Current assets / Current liabilities"),
    MetricDef("altman_z2", "Altman Z''-score", "Red flags", "score", "higher", "6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4"),
    MetricDef("beneish_m", "Beneish M-score", "Red flags", "score", "lower", "Eight-variable manipulation score (lower is better)"),
    MetricDef("piotroski", "Piotroski F-score (tests passed)", "Red flags", "score", "higher", "Points out of the tests that could run"),
    MetricDef("pe", "Price / Earnings", "Valuation", "x", "lower", "Market cap / Net income"),
    MetricDef("pb", "Price / Book", "Valuation", "x", "lower", "Market cap / Total equity"),
    MetricDef("ev_ebitda", "EV / EBITDA", "Valuation", "x", "lower", "(Market cap + Debt − Cash) / EBITDA"),
]


@dataclass
class CompanyIn:
    name: str
    periods: list[str]
    items: dict[str, list[Num]]


@dataclass
class Row:
    key: str
    name: str
    group: str
    unit: str
    better: str
    formula: str
    values: list[Num]
    ranks: list[int | None]
    median: Num
    notes: list[str] = field(default_factory=list)


@dataclass
class PeerReport:
    companies: list[str]
    latest_periods: list[str]
    rows: list[Row]
    average_rank: list[Num]
    ranked_on: list[int]
    warnings: list[str]


def _div(a: Num, b: Num) -> Num:
    return a / b if _ok(a) and _ok(b) and b != 0 else None


def _scale(v: Num, k: float) -> Num:
    return v * k if _ok(v) else None


def _avg(a: Num, b: Num) -> Num:
    if _ok(a) and _ok(b):
        return (a + b) / 2
    return a if _ok(a) else None


def _metrics(c: CompanyIn) -> dict[str, Num]:
    d = _Data(c.periods, c.items)
    t, p = d.n - 1, d.n - 2
    g = d.get
    rev, ni, ebit, da = g("revenue", t), g("net_income", t), g("operating_income", t), g("depreciation_amortization", t)
    eq_avg, ta_avg = _avg(g("total_equity", t), g("total_equity", p)), _avg(g("total_assets", t), g("total_assets", p))
    debt_t = g("total_debt", t)
    ce = lambda i: (g("total_equity", i) + g("total_debt", i)) if _ok(g("total_equity", i)) and _ok(g("total_debt", i)) else None  # noqa: E731
    ebitda = (ebit + da) if _ok(ebit) and _ok(da) else None
    first = next((i for i in range(d.n) if _ok(g("revenue", i)) and g("revenue", i) > 0), None)
    years = t - first if first is not None else 0
    cagr = ((rev / g("revenue", first)) ** (1 / years) - 1) if first is not None and years > 0 and _ok(rev) and rev > 0 else None
    ocf, capex = g("operating_cash_flow", t), g("capex", t)
    mcap = g("market_cap", t)
    m = {
        "revenue": rev,
        "revenue_growth": (rev / g("revenue", p) - 1) if p >= 0 and _ok(rev) and _ok(g("revenue", p)) and g("revenue", p) > 0 else None,
        "revenue_cagr": cagr,
        "profit_growth": (ni / g("net_income", p) - 1) if p >= 0 and _ok(ni) and _ok(g("net_income", p)) and g("net_income", p) > 0 else None,
        "gross_margin": _div(g("gross_profit", t), rev),
        "ebitda_margin": _div(ebitda, rev),
        "operating_margin": _div(ebit, rev),
        "net_margin": _div(ni, rev),
        "roe": _div(ni, eq_avg) if _ok(eq_avg) and eq_avg > 0 else None,
        "roa": _div(ni, ta_avg),
        "roce": _div(ebit, _avg(ce(t), ce(p) if p >= 0 else None)),
        "asset_turnover": _div(rev, ta_avg),
        "receivable_days": _scale(_div(_avg(g("receivables", t), g("receivables", p)), rev), 365),
        "cash_conversion": _div(ocf, ni) if _ok(ni) and ni > 0 else None,
        "fcf_margin": _div((ocf - abs(capex)) if _ok(ocf) and _ok(capex) else None, rev),
        "debt_equity": _div(debt_t, g("total_equity", t)) if _ok(g("total_equity", t)) and g("total_equity", t) > 0 else None,
        "interest_cover": _div(ebit, g("interest_expense", t)) if _ok(g("interest_expense", t)) and g("interest_expense", t) > 0 else None,
        "current_ratio": _div(g("current_assets", t), g("current_liabilities", t)),
        "pe": _div(mcap, ni) if _ok(ni) and ni > 0 else None,
        "pb": _div(mcap, g("total_equity", t)) if _ok(g("total_equity", t)) and g("total_equity", t) > 0 else None,
        "ev_ebitda": _div((mcap + debt_t - g("cash", t)) if _ok(mcap) and _ok(debt_t) and _ok(g("cash", t)) else None, ebitda)
        if _ok(ebitda) and ebitda > 0 else None,
    }
    if d.n >= 2:
        z2 = altman(d, t)[0]
        bm = beneish(d, t)
        pf = piotroski(d, t)
        m["altman_z2"] = z2.value if z2.status == "ok" else None
        m["beneish_m"] = bm.value if bm.status == "ok" else None
        m["piotroski"] = float(pf.score) if pf.tested else None
        m["_piotroski_tested"] = float(pf.tested)
        m["_beneish_model"] = bm.model
    return m


def compare(companies: list[CompanyIn]) -> PeerReport:
    if not 2 <= len(companies) <= 12:
        raise FinanceInputError("Compare between 2 and 12 companies.")
    names = [c.name.strip() or f"Company {i + 1}" for i, c in enumerate(companies)]
    if len(set(n.lower() for n in names)) != len(names):
        raise FinanceInputError("Give each company a different name.")
    for c in companies:
        if not c.periods:
            raise FinanceInputError(f"'{c.name}' has no periods.")
    data = [_metrics(c) for c in companies]
    latest = [c.periods[-1] for c in companies]
    warnings = ["Check that every company uses the same currency, units (e.g. ₹ crores) and accounting year before comparing."]
    if len(set(latest)) > 1:
        warnings.append("Latest periods differ (" + ", ".join(f"{n}: {p}" for n, p in zip(names, latest)) + "), so the comparison mixes years.")
    rows: list[Row] = []
    for md in METRICS:
        vals = [m.get(md.key) for m in data]
        if all(v is None for v in vals):
            continue
        present = [(i, v) for i, v in enumerate(vals) if v is not None]
        ranks: list[int | None] = [None] * len(vals)
        if md.better != "neutral" and len(present) >= 2:
            order = sorted(present, key=lambda iv: iv[1], reverse=md.better == "higher")
            pos = 0
            prev = None
            for n, (i, v) in enumerate(order, 1):
                if v != prev:
                    pos, prev = n, v
                ranks[i] = pos  # ties share a rank
        notes = []
        if md.key == "piotroski":
            tested = {int(m.get("_piotroski_tested", 0)) for m in data if m.get("piotroski") is not None}
            if len(tested) > 1:
                notes.append("Companies were scored on different numbers of tests; compare with care.")
        if md.key == "beneish_m":
            models = {m.get("_beneish_model") for m in data if m.get("beneish_m") is not None}
            if len(models) > 1:
                notes.append("Some scores use the 5-variable model and some the 8-variable model; they are not directly comparable.")
        if md.key in ("pe", "pb", "ev_ebitda"):
            notes.append("Lower can mean cheaper or lower expected growth; this is not a buy or sell signal.")
        rows.append(Row(md.key, md.name, md.group, md.unit, md.better, md.formula, vals, ranks,
                        statistics.median(v for _, v in present) if present else None, notes))
    avg_rank: list[Num] = []
    ranked_on: list[int] = []
    for i in range(len(companies)):
        rs = [r.ranks[i] for r in rows if r.ranks[i] is not None]
        avg_rank.append(sum(rs) / len(rs) if rs else None)
        ranked_on.append(len(rs))
    if len(set(ranked_on)) > 1:
        warnings.append("Companies were ranked on different numbers of metrics because some data is missing; the average rank is less reliable.")
    return PeerReport(names, latest, rows, avg_rank, ranked_on, warnings)
