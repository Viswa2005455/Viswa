"""Multi-period financial statement analysis.

Input: a list of periods (oldest first) and line items. Each line has a statement
("income" | "balance" | "cashflow"), a display label, an optional standard `key` (which
enables reconciliation checks and derived metrics) and one value per period. Missing values
are `None` and are never treated as zero.

Outputs
* Horizontal analysis: change vs the previous period, absolute and % (|prior| denominator;
  None when the prior value is zero or missing).
* Vertical (common-size) analysis: income statement and cash flow lines as % of revenue,
  balance sheet lines as % of total assets.
* Derived metrics: gross margin, EBITDA, free cash flow, net working capital, cash conversion,
  accruals ratio, CapEx / D&A, CAGR.
* Reconciliation checks and earnings-quality indicators. A failed check flags an
  inconsistency to investigate (omitted lines, rounding, extraction errors); it does not
  prove misstatement or fraud.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from . import FinanceInputError

Statement = Literal["income", "balance", "cashflow"]

STANDARD_ITEMS: dict[str, tuple[Statement, str]] = {
    "revenue": ("income", "Revenue"),
    "cogs": ("income", "Cost of goods sold"),
    "gross_profit": ("income", "Gross profit"),
    "operating_expenses": ("income", "Operating expenses"),
    "sga": ("income", "Selling, general & admin expenses"),
    "other_income": ("income", "Other income"),
    "ebitda": ("income", "EBITDA"),
    "depreciation_amortization": ("income", "Depreciation & amortisation"),
    "operating_income": ("income", "Operating income (EBIT)"),
    "interest_expense": ("income", "Interest expense"),
    "pretax_income": ("income", "Profit before tax"),
    "income_tax": ("income", "Income tax"),
    "net_income": ("income", "Net income"),
    "cash": ("balance", "Cash & equivalents"),
    "receivables": ("balance", "Accounts receivable"),
    "inventory": ("balance", "Inventory"),
    "current_assets": ("balance", "Total current assets"),
    "ppe": ("balance", "Property, plant & equipment (net)"),
    "total_assets": ("balance", "Total assets"),
    "accounts_payable": ("balance", "Accounts payable"),
    "current_liabilities": ("balance", "Total current liabilities"),
    "total_debt": ("balance", "Total debt"),
    "total_liabilities": ("balance", "Total liabilities"),
    "total_equity": ("balance", "Total equity"),
    "share_capital": ("balance", "Share capital"),
    "retained_earnings": ("balance", "Retained earnings / reserves"),
    "long_term_debt": ("balance", "Long-term debt"),
    "operating_cash_flow": ("cashflow", "Cash from operating activities"),
    "capex": ("cashflow", "Capital expenditure"),
    "investing_cash_flow": ("cashflow", "Cash from investing activities"),
    "financing_cash_flow": ("cashflow", "Cash from financing activities"),
    "net_change_in_cash": ("cashflow", "Net change in cash"),
    "beginning_cash": ("cashflow", "Cash at beginning of period"),
    "ending_cash": ("cashflow", "Cash at end of period"),
}

Num = float | None


@dataclass
class StatementLine:
    label: str
    statement: Statement
    values: list[Num]
    key: str | None = None
    source: str | None = None


@dataclass
class Change:
    absolute: Num
    pct: Num
    note: str | None = None


@dataclass
class LineAnalysis:
    label: str
    statement: str
    key: str | None
    values: list[Num]
    changes: list[Change | None]  # index 0 is None (no prior period)
    common_size: list[Num]
    cagr: Num
    source: str | None = None


@dataclass
class Check:
    name: str
    period: str
    status: Literal["pass", "fail", "insufficient"]
    difference: Num
    detail: str


@dataclass
class StatementReport:
    periods: list[str]
    lines: list[LineAnalysis]
    metrics: dict[str, list[Num]]
    checks: list[Check]
    quality_flags: list[str]
    notes: list[str] = field(default_factory=list)


def _ok(v: Num) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def change(prior: Num, current: Num) -> Change | None:
    if not (_ok(prior) and _ok(current)):
        return None
    diff = current - prior
    if prior == 0:
        return Change(diff, None, "Prior value is zero; % change is not meaningful.")
    note = "Sign changed between periods; interpret the % change with care." if (prior < 0) != (current < 0) and current != 0 else None
    return Change(diff, diff / abs(prior) * 100, note)


def cagr(first: Num, last: Num, years: int) -> Num:
    if years < 1 or not (_ok(first) and _ok(last)) or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _div(a: Num, b: Num, scale: float = 1.0) -> Num:
    if not (_ok(a) and _ok(b)) or b == 0:
        return None
    return a / b * scale


def _tolerance(*vals: Num) -> float:
    """Allow for rounding in published statements: 0.5% of the largest value, at least 1 unit."""
    m = max((abs(v) for v in vals if _ok(v)), default=0.0)
    return max(1.0, 0.005 * m)


def analyse(periods: list[str], lines: list[StatementLine]) -> StatementReport:
    n = len(periods)
    if not 1 <= n <= 20:
        raise FinanceInputError("Provide between 1 and 20 periods.")
    if not lines:
        raise FinanceInputError("Provide at least one line item.")
    seen_keys: set[str] = set()
    for line in lines:
        if len(line.values) != n:
            raise FinanceInputError(f"Line '{line.label}' has {len(line.values)} values; expected {n} (one per period).")
        if line.key:
            if line.key not in STANDARD_ITEMS:
                raise FinanceInputError(f"Unknown standard item '{line.key}' on line '{line.label}'.")
            if line.key in seen_keys:
                raise FinanceInputError(f"Standard item '{line.key}' is mapped to more than one line.")
            seen_keys.add(line.key)

    by_key = {l.key: l.values for l in lines if l.key}

    def k(key: str) -> list[Num]:
        return by_key.get(key, [None] * n)

    revenue, total_assets = k("revenue"), k("total_assets")
    out: list[LineAnalysis] = []
    for line in lines:
        changes: list[Change | None] = [None] + [change(line.values[i - 1], line.values[i]) for i in range(1, n)]
        base = total_assets if line.statement == "balance" else revenue
        common = [_div(line.values[i], base[i], 100) for i in range(n)]
        out.append(LineAnalysis(line.label, line.statement, line.key, line.values, changes, common,
                                cagr(line.values[0], line.values[-1], n - 1), line.source))

    # ---------------- derived metrics ----------------
    def series(fn) -> list[Num]:
        res = []
        for i in range(n):
            try:
                res.append(fn(i))
            except TypeError:  # an input was None
                res.append(None)
        return res

    rev, cogs, ebit, da = k("revenue"), k("cogs"), k("operating_income"), k("depreciation_amortization")
    ni, ocf, capex = k("net_income"), k("operating_cash_flow"), k("capex")
    ca, cl = k("current_assets"), k("current_liabilities")
    gp = [g if _ok(g) else (r - c if _ok(r) and _ok(c) else None) for g, r, c in zip(k("gross_profit"), rev, cogs)]
    ebitda = [e if _ok(e) else (b + d if _ok(b) and _ok(d) else None) for e, b, d in zip(k("ebitda"), ebit, da)]
    # CapEx may be entered as a negative cash outflow or as a positive amount; it is always an outflow.
    fcf = series(lambda i: ocf[i] - abs(capex[i]))
    nwc = series(lambda i: ca[i] - cl[i])
    avg_ta = [None] + [((total_assets[i] + total_assets[i - 1]) / 2) if _ok(total_assets[i]) and _ok(total_assets[i - 1]) else None
                       for i in range(1, n)]
    metrics = {
        "gross_margin_pct": [_div(g, r, 100) for g, r in zip(gp, rev)],
        "ebitda": ebitda,
        "ebitda_margin_pct": [_div(e, r, 100) for e, r in zip(ebitda, rev)],
        "operating_margin_pct": [_div(e, r, 100) for e, r in zip(ebit, rev)],
        "net_margin_pct": [_div(x, r, 100) for x, r in zip(ni, rev)],
        "free_cash_flow": fcf,
        "fcf_margin_pct": [_div(f, r, 100) for f, r in zip(fcf, rev)],
        "net_working_capital": nwc,
        "change_in_nwc": [None] + [nwc[i] - nwc[i - 1] if _ok(nwc[i]) and _ok(nwc[i - 1]) else None for i in range(1, n)],
        "cash_conversion": [_div(o, x) if _ok(x) and x > 0 else None for o, x in zip(ocf, ni)],
        "accruals_ratio_pct": [_div((ni[i] - ocf[i]) if _ok(ni[i]) and _ok(ocf[i]) else None, avg_ta[i], 100) for i in range(n)],
        "capex_to_da": [_div(abs(c) if _ok(c) else None, d) for c, d in zip(capex, da)],
    }

    # ---------------- reconciliation checks ----------------
    checks: list[Check] = []

    def check(name: str, i: int, lhs: Num, rhs: Num, detail: str):
        if not (_ok(lhs) and _ok(rhs)):
            checks.append(Check(name, periods[i], "insufficient", None, "Required lines are missing for this period."))
            return
        diff = lhs - rhs
        status = "pass" if abs(diff) <= _tolerance(lhs, rhs) else "fail"
        checks.append(Check(name, periods[i], status, diff, detail))

    has = lambda *keys: all(key in by_key for key in keys)  # noqa: E731
    for i in range(n):
        if has("total_assets", "total_equity") and (has("total_liabilities")):
            check("Assets = Liabilities + Equity", i, total_assets[i],
                  (k("total_liabilities")[i] + k("total_equity")[i]) if _ok(k("total_liabilities")[i]) and _ok(k("total_equity")[i]) else None,
                  "Balance sheet must balance.")
        if has("revenue", "cogs", "gross_profit"):
            check("Gross profit = Revenue − COGS", i, k("gross_profit")[i],
                  (rev[i] - cogs[i]) if _ok(rev[i]) and _ok(cogs[i]) else None, "Income statement arithmetic.")
        if has("pretax_income", "income_tax", "net_income"):
            pt, tx = k("pretax_income")[i], k("income_tax")[i]
            check("Net income = Profit before tax − Tax", i, ni[i], (pt - tx) if _ok(pt) and _ok(tx) else None,
                  "Excludes minority interests and discontinued operations, if any.")
        if has("operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "net_change_in_cash"):
            parts = [ocf[i], k("investing_cash_flow")[i], k("financing_cash_flow")[i]]
            check("Operating + Investing + Financing = Net change in cash", i, k("net_change_in_cash")[i],
                  sum(parts) if all(_ok(p) for p in parts) else None, "Excludes FX effects on cash, if any.")
        if has("beginning_cash", "net_change_in_cash", "ending_cash"):
            bc, nc = k("beginning_cash")[i], k("net_change_in_cash")[i]
            check("Ending cash = Beginning cash + Net change", i, k("ending_cash")[i], (bc + nc) if _ok(bc) and _ok(nc) else None,
                  "Cash flow statement roll-forward.")
        if has("ending_cash", "cash"):
            check("Cash flow ending cash = Balance sheet cash", i, k("ending_cash")[i], k("cash")[i],
                  "Differences can be legitimate (e.g. bank overdrafts or restricted cash defined differently).")
        if i > 0 and has("ending_cash", "beginning_cash"):
            check("Beginning cash = prior period ending cash", i, k("beginning_cash")[i], k("ending_cash")[i - 1], "Period-to-period continuity.")
        if has("current_assets", "cash", "receivables", "inventory"):
            parts = [k("cash")[i], k("receivables")[i], k("inventory")[i]]
            if _ok(ca[i]) and all(_ok(p) for p in parts):
                excess = sum(parts) - ca[i]
                checks.append(Check("Current-asset components ≤ total current assets", periods[i],
                                    "fail" if excess > _tolerance(ca[i]) else "pass", excess,
                                    "Cash + receivables + inventory should not exceed total current assets."))

    # ---------------- earnings-quality indicators ----------------
    flags: list[str] = []
    if n >= 2:
        conv = [c for c in metrics["cash_conversion"] if _ok(c)]
        if len(conv) >= 2 and all(c < 0.8 for c in conv):
            flags.append("Operating cash flow has been below 80% of net income in every period with data; profits are not fully converting to cash.")
        rec, inv = k("receivables"), k("inventory")
        g = lambda s: change(s[0], s[-1]).pct if change(s[0], s[-1]) else None  # noqa: E731
        rg, recg, invg, cogsg = g(rev), g(rec), g(inv), g(cogs)
        if _ok(rg) and _ok(recg) and recg > rg + 10:
            flags.append(f"Receivables grew {recg:.0f}% vs revenue {rg:.0f}% over the period; check collection and revenue recognition.")
        if _ok(cogsg) and _ok(invg) and invg > cogsg + 10:
            flags.append(f"Inventory grew {invg:.0f}% vs COGS {cogsg:.0f}%; check for slow-moving stock.")
        acc = [a for a in metrics["accruals_ratio_pct"] if _ok(a)]
        if acc and acc[-1] > 10:
            flags.append(f"Latest accruals ratio is {acc[-1]:.1f}% of average assets; high accruals can signal lower earnings quality.")
        cd = [c for c in metrics["capex_to_da"] if _ok(c)]
        if len(cd) >= 2 and all(c < 0.8 for c in cd):
            flags.append("CapEx has stayed below 80% of D&A; the asset base may be under-invested.")

    notes = ["Earnings-quality indicators are prompts for investigation, not evidence of misstatement."]
    if not by_key:
        notes.append("No lines are mapped to standard items, so checks and derived metrics are unavailable.")
    return StatementReport(periods, out, metrics, checks, flags, notes)
