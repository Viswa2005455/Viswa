"""Financial ratio analysis.

Each ratio is computed only when its inputs are present. Every result carries the formula,
the inputs used, the calculation steps, the value, an interpretation and limitations, so the
UI and reports can show exactly how the number was produced.

Average balances: when a prior-period value is supplied (key suffix "_prior"), turnover and
return ratios use (opening + closing) / 2. Otherwise the closing balance is used and a note
says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Statement items understood by the engine (all in the same currency and units).
ITEMS = {
    "revenue": "Revenue",
    "cogs": "Cost of goods sold",
    "operating_income": "Operating income (EBIT)",
    "depreciation_amortization": "Depreciation & amortisation",
    "interest_expense": "Interest expense",
    "net_income": "Net income",
    "operating_cash_flow": "Operating cash flow",
    "cash": "Cash & equivalents",
    "marketable_securities": "Marketable securities",
    "receivables": "Accounts receivable",
    "inventory": "Inventory",
    "current_assets": "Current assets",
    "total_assets": "Total assets",
    "current_liabilities": "Current liabilities",
    "accounts_payable": "Accounts payable",
    "total_debt": "Total debt",
    "total_liabilities": "Total liabilities",
    "total_equity": "Shareholders' equity",
    "tax_rate": "Effective tax rate (decimal)",
    "debt_service": "Debt service (interest + principal)",
    "shares_outstanding": "Shares outstanding",
    "share_price": "Share price",
}

AVERAGEABLE = {"receivables", "inventory", "total_assets", "accounts_payable", "total_equity", "total_debt"}


@dataclass
class RatioResult:
    key: str
    name: str
    category: str
    formula: str
    unit: str  # "x" | "%" | "days" | "currency"
    value: float | None
    status: str  # "ok" | "missing" | "undefined"
    inputs: dict[str, float] = field(default_factory=dict)
    steps: str = ""
    interpretation: str = ""
    notes: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class _Ctx:
    def __init__(self, data: dict[str, float | None], days: int):
        self.data = {k: v for k, v in data.items() if v is not None}
        self.days = days
        self.used: dict[str, float] = {}
        self.notes: list[str] = []
        self.missing: list[str] = []

    def get(self, key: str, average: bool = False) -> float | None:
        if key not in self.data:
            self.missing.append(ITEMS.get(key, key))
            return None
        v = float(self.data[key])
        if average and key in AVERAGEABLE:
            prior = self.data.get(f"{key}_prior")
            if prior is not None:
                self.used[f"{key} (closing)"] = v
                self.used[f"{key} (opening)"] = float(prior)
                v = (v + float(prior)) / 2
                self.used[f"average {key}"] = v
                return v
            self.notes.append(f"Closing {ITEMS[key].lower()} used because no prior-period balance was supplied.")
        self.used[key] = v
        return v


def _fmt(v: float) -> str:
    return f"{v:,.4g}" if abs(v) < 1000 else f"{v:,.0f}"


def _ratio(key, name, category, formula, unit, interpretation_fn: Callable[[float], str],
           compute: Callable[[_Ctx], tuple[float | None, str] | None], data, days) -> RatioResult:
    ctx = _Ctx(data, days)
    res = RatioResult(key, name, category, formula, unit, None, "missing")
    out = compute(ctx)
    res.inputs, res.notes, res.missing = ctx.used, ctx.notes, sorted(set(ctx.missing))
    if res.missing:
        res.notes.insert(0, "Cannot calculate: required inputs are missing.")
        return res
    value, steps = out if out else (None, "")
    res.steps = steps
    if value is None:
        res.status = "undefined"
        res.notes.insert(0, steps or "Undefined: the denominator is zero.")
        return res
    res.value, res.status = value, "ok"
    res.interpretation = interpretation_fn(value)
    return res


def _div(n: float | None, d: float | None, label_n: str, label_d: str, scale: float = 1):
    if n is None or d is None:
        return None
    if d == 0:
        return None, f"{label_d} is zero, so the ratio is undefined."
    v = n / d * scale
    suffix = f" x {scale:g}" if scale != 1 else ""
    return v, f"{label_n} {_fmt(n)} / {label_d} {_fmt(d)}{suffix} = {v:,.4f}"


def compute_ratios(data: dict[str, float | None], period_days: int = 365) -> list[RatioResult]:
    days = period_days
    R: list[RatioResult] = []

    def add(*args):
        R.append(_ratio(*args, data, days))

    # ---------------- Liquidity ----------------
    add("current_ratio", "Current ratio", "Liquidity", "Current assets / Current liabilities", "x",
        lambda v: "Healthy short-term cover" if v >= 1.5 else "Adequate" if v >= 1 else "Current liabilities exceed current assets",
        lambda c: _div(c.get("current_assets"), c.get("current_liabilities"), "Current assets", "Current liabilities"))

    def quick(c: _Ctx):
        ca, inv, cl = c.get("current_assets"), c.get("inventory"), c.get("current_liabilities")
        if None in (ca, inv, cl):
            return None
        return _div(ca - inv, cl, "(Current assets - Inventory)", "Current liabilities")
    add("quick_ratio", "Quick ratio", "Liquidity", "(Current assets - Inventory) / Current liabilities", "x",
        lambda v: "Can meet current liabilities without selling inventory" if v >= 1 else "Relies on inventory to meet current liabilities", quick)

    def cash_ratio(c: _Ctx):
        cash, cl = c.get("cash"), c.get("current_liabilities")
        if None in (cash, cl):
            return None
        ms = data.get("marketable_securities")
        if ms is not None:
            c.used["marketable_securities"] = float(ms)
            return _div(cash + ms, cl, "(Cash + Marketable securities)", "Current liabilities")
        c.notes.append("Marketable securities not supplied; cash only.")
        return _div(cash, cl, "Cash", "Current liabilities")
    add("cash_ratio", "Cash ratio", "Liquidity", "(Cash + Marketable securities) / Current liabilities", "x",
        lambda v: "Strong cash cover" if v >= 0.5 else "Limited immediate cash cover", cash_ratio)

    add("ocf_ratio", "Operating cash flow ratio", "Liquidity", "Operating cash flow / Current liabilities", "x",
        lambda v: "Operations generate enough cash to cover current liabilities" if v >= 1 else "Operating cash flow does not fully cover current liabilities",
        lambda c: _div(c.get("operating_cash_flow"), c.get("current_liabilities"), "Operating cash flow", "Current liabilities"))

    # ---------------- Profitability ----------------
    def gross(c: _Ctx):
        rev, cogs = c.get("revenue"), c.get("cogs")
        if None in (rev, cogs):
            return None
        return _div(rev - cogs, rev, "Gross profit", "Revenue", 100)
    add("gross_margin", "Gross profit margin", "Profitability", "(Revenue - COGS) / Revenue x 100", "%",
        lambda v: f"Keeps {v:.1f} of every 100 of revenue after direct costs", gross)
    add("operating_margin", "Operating profit margin", "Profitability", "EBIT / Revenue x 100", "%",
        lambda v: "Operating loss" if v < 0 else f"Earns {v:.1f}% operating profit on revenue",
        lambda c: _div(c.get("operating_income"), c.get("revenue"), "EBIT", "Revenue", 100))

    def ebitda_m(c: _Ctx):
        ebit, da, rev = c.get("operating_income"), c.get("depreciation_amortization"), c.get("revenue")
        if None in (ebit, da, rev):
            return None
        return _div(ebit + da, rev, "EBITDA", "Revenue", 100)
    add("ebitda_margin", "EBITDA margin", "Profitability", "(EBIT + D&A) / Revenue x 100", "%",
        lambda v: "Cash-oriented operating profitability before capital intensity", ebitda_m)
    add("net_margin", "Net profit margin", "Profitability", "Net income / Revenue x 100", "%",
        lambda v: "Net loss" if v < 0 else f"Keeps {v:.1f}% of revenue as profit",
        lambda c: _div(c.get("net_income"), c.get("revenue"), "Net income", "Revenue", 100))
    add("roa", "Return on assets", "Profitability", "Net income / Average total assets x 100", "%",
        lambda v: "How efficiently assets generate profit",
        lambda c: _div(c.get("net_income"), c.get("total_assets", True), "Net income", "Avg total assets", 100))

    def roe(c: _Ctx):
        ni, eq = c.get("net_income"), c.get("total_equity", True)
        if None in (ni, eq):
            return None
        if eq <= 0:
            return None, "Equity is zero or negative, so ROE is not meaningful."
        return _div(ni, eq, "Net income", "Avg equity", 100)
    add("roe", "Return on equity", "Profitability", "Net income / Average shareholders' equity x 100", "%",
        lambda v: "Return generated for shareholders (boosted by leverage)", roe)

    def roic(c: _Ctx):
        ebit, t, debt, eq = c.get("operating_income"), c.get("tax_rate"), c.get("total_debt", True), c.get("total_equity", True)
        if None in (ebit, t, debt, eq):
            return None
        cash = data.get("cash")
        invested = debt + eq - (float(cash) if cash is not None else 0)
        if cash is None:
            c.notes.append("Cash not supplied; invested capital not reduced by cash.")
        else:
            c.used["cash"] = float(cash)
        if invested <= 0:
            return None, "Invested capital is zero or negative, so ROIC is not meaningful."
        return _div(ebit * (1 - t), invested, "NOPAT", "Invested capital", 100)
    add("roic", "Return on invested capital", "Profitability", "EBIT x (1 - tax rate) / (Debt + Equity - Cash) x 100", "%",
        lambda v: "Compare with WACC: ROIC above WACC creates value", roic)

    # ---------------- Efficiency ----------------
    add("inventory_turnover", "Inventory turnover", "Efficiency", "COGS / Average inventory", "x",
        lambda v: f"Inventory is sold and replaced about {v:.1f} times per period",
        lambda c: _div(c.get("cogs"), c.get("inventory", True), "COGS", "Avg inventory"))
    add("dio", "Days inventory outstanding", "Efficiency", f"Average inventory / COGS x {days}", "days",
        lambda v: f"Inventory is held for about {v:.0f} days",
        lambda c: _div(c.get("inventory", True), c.get("cogs"), "Avg inventory", "COGS", days))
    add("receivables_turnover", "Receivables turnover", "Efficiency", "Revenue / Average receivables", "x",
        lambda v: f"Receivables are collected about {v:.1f} times per period",
        lambda c: _div(c.get("revenue"), c.get("receivables", True), "Revenue", "Avg receivables"))
    add("dso", "Days sales outstanding", "Efficiency", f"Average receivables / Revenue x {days}", "days",
        lambda v: f"Customers pay in about {v:.0f} days on average",
        lambda c: _div(c.get("receivables", True), c.get("revenue"), "Avg receivables", "Revenue", days))
    add("payables_turnover", "Payables turnover", "Efficiency", "COGS / Average payables", "x",
        lambda v: f"Suppliers are paid about {v:.1f} times per period",
        lambda c: _div(c.get("cogs"), c.get("accounts_payable", True), "COGS", "Avg payables"))
    add("dpo", "Days payable outstanding", "Efficiency", f"Average payables / COGS x {days}", "days",
        lambda v: f"Suppliers are paid in about {v:.0f} days",
        lambda c: _div(c.get("accounts_payable", True), c.get("cogs"), "Avg payables", "COGS", days))
    add("asset_turnover", "Total asset turnover", "Efficiency", "Revenue / Average total assets", "x",
        lambda v: f"Generates {v:.2f} of revenue per unit of assets",
        lambda c: _div(c.get("revenue"), c.get("total_assets", True), "Revenue", "Avg total assets"))

    def ccc(c: _Ctx):
        inv, rec, ap = c.get("inventory", True), c.get("receivables", True), c.get("accounts_payable", True)
        rev, cogs = c.get("revenue"), c.get("cogs")
        if None in (inv, rec, ap, rev, cogs):
            return None
        if rev == 0 or cogs == 0:
            return None, "Revenue or COGS is zero, so the cash conversion cycle is undefined."
        dio, dso, dpo = inv / cogs * days, rec / rev * days, ap / cogs * days
        v = dio + dso - dpo
        return v, f"DIO {dio:.1f} + DSO {dso:.1f} - DPO {dpo:.1f} = {v:.1f} days"
    add("ccc", "Cash conversion cycle", "Efficiency", "DIO + DSO - DPO", "days",
        lambda v: "Suppliers finance the operating cycle" if v < 0 else f"Cash is tied up for about {v:.0f} days", ccc)

    # ---------------- Leverage & coverage ----------------
    def de(c: _Ctx):
        d, e = c.get("total_debt"), c.get("total_equity")
        if None in (d, e):
            return None
        if e <= 0:
            return None, "Equity is zero or negative; debt-to-equity is not meaningful (the company may be technically insolvent)."
        return _div(d, e, "Total debt", "Equity")
    add("debt_to_equity", "Debt-to-equity", "Leverage", "Total debt / Shareholders' equity", "x",
        lambda v: "Conservative leverage" if v < 0.5 else "Moderate leverage" if v < 1.5 else "High leverage", de)
    add("debt_to_assets", "Debt-to-assets", "Leverage", "Total debt / Total assets", "x",
        lambda v: f"{v:.0%} of assets are financed with debt",
        lambda c: _div(c.get("total_debt"), c.get("total_assets"), "Total debt", "Total assets"))
    add("interest_coverage", "Interest coverage", "Leverage", "EBIT / Interest expense", "x",
        lambda v: "Comfortable" if v >= 5 else "Adequate" if v >= 2 else "Weak: earnings barely cover interest",
        lambda c: _div(c.get("operating_income"), c.get("interest_expense"), "EBIT", "Interest expense"))

    def dscr(c: _Ctx):
        ebit, da, ds = c.get("operating_income"), c.get("depreciation_amortization"), c.get("debt_service")
        if None in (ebit, da, ds):
            return None
        return _div(ebit + da, ds, "EBITDA", "Debt service")
    add("dscr", "Debt service coverage", "Leverage", "EBITDA / (Interest + Principal repayments)", "x",
        lambda v: "Cash earnings cover debt service" if v >= 1.25 else "Thin or insufficient debt-service cover", dscr)

    def nd_ebitda(c: _Ctx):
        d, cash, ebit, da = c.get("total_debt"), c.get("cash"), c.get("operating_income"), c.get("depreciation_amortization")
        if None in (d, cash, ebit, da):
            return None
        ebitda = ebit + da
        if ebitda <= 0:
            return None, "EBITDA is zero or negative, so net debt / EBITDA is not meaningful."
        return _div(d - cash, ebitda, "Net debt", "EBITDA")
    add("net_debt_ebitda", "Net debt / EBITDA", "Leverage", "(Total debt - Cash) / EBITDA", "x",
        lambda v: "Net cash position" if v < 0 else "Low" if v < 2 else "Elevated" if v < 4 else "High leverage", nd_ebitda)

    # ---------------- Valuation ----------------
    add("eps", "Earnings per share", "Valuation", "Net income / Shares outstanding", "currency",
        lambda v: "Profit attributable to each share",
        lambda c: _div(c.get("net_income"), c.get("shares_outstanding"), "Net income", "Shares"))

    def pe(c: _Ctx):
        p, ni, sh = c.get("share_price"), c.get("net_income"), c.get("shares_outstanding")
        if None in (p, ni, sh):
            return None
        if ni <= 0:
            return None, "Earnings are zero or negative, so P/E is not meaningful."
        return _div(p, ni / sh, "Price", "EPS")
    add("pe", "Price-to-earnings", "Valuation", "Share price / EPS", "x", lambda v: f"Investors pay {v:.1f}x annual earnings", pe)

    def pb(c: _Ctx):
        p, eq, sh = c.get("share_price"), c.get("total_equity"), c.get("shares_outstanding")
        if None in (p, eq, sh):
            return None
        if eq <= 0:
            return None, "Book equity is zero or negative, so P/B is not meaningful."
        return _div(p, eq / sh, "Price", "Book value per share")
    add("pb", "Price-to-book", "Valuation", "Share price / Book value per share", "x", lambda v: "Market value relative to book equity", pb)

    def ev_ebitda(c: _Ctx):
        p, sh, d, cash, ebit, da = (c.get(k) for k in ("share_price", "shares_outstanding", "total_debt", "cash",
                                                       "operating_income", "depreciation_amortization"))
        if None in (p, sh, d, cash, ebit, da):
            return None
        ev, ebitda = p * sh + d - cash, ebit + da
        if ebitda <= 0:
            return None, "EBITDA is zero or negative, so EV/EBITDA is not meaningful."
        return _div(ev, ebitda, "Enterprise value", "EBITDA")
    add("ev_ebitda", "EV / EBITDA", "Valuation", "(Market cap + Debt - Cash) / EBITDA", "x",
        lambda v: "Capital-structure-neutral valuation multiple", ev_ebitda)

    def ey(c: _Ctx):
        p, ni, sh = c.get("share_price"), c.get("net_income"), c.get("shares_outstanding")
        if None in (p, ni, sh):
            return None
        return _div(ni / sh, p, "EPS", "Price", 100)
    add("earnings_yield", "Earnings yield", "Valuation", "EPS / Share price x 100", "%",
        lambda v: "Earnings return on the share price (inverse of P/E)", ey)

    return R
