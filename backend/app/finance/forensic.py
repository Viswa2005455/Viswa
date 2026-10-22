"""Red-flag (forensic accounting) screens: Beneish M-score, Altman Z-score, Piotroski F-score
and cash-quality checks.

These are statistical screening tools, not proof of fraud or failure. Every score lists the
formula, its components with their inputs, and which inputs were missing. A component whose
inputs are missing is never filled with zero: the score is either computed with a documented
alternative model (e.g. the 5-variable Beneish model) or reported as "missing".

Input shape: `periods` oldest -> newest, `items` = {standard item key: [value per period]}.
All money amounts must be in the same currency and units.

References:
* Beneish, M. D. (1999). The detection of earnings manipulation. Financial Analysts Journal.
* Altman, E. I. (1968); Altman (2000/2005) Z'' model for non-manufacturers and emerging markets.
* Piotroski, J. D. (2000). Value investing: the use of historical financial statement information.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import FinanceInputError
from .statements import STANDARD_ITEMS

Num = float | None

LABELS = {
    "revenue": "Revenue", "cogs": "Cost of goods sold", "gross_profit": "Gross profit", "sga": "Selling, general & admin",
    "depreciation_amortization": "Depreciation", "operating_income": "Operating income (EBIT)", "interest_expense": "Interest",
    "pretax_income": "Profit before tax", "other_income": "Other income", "net_income": "Net income",
    "receivables": "Receivables", "inventory": "Inventory", "current_assets": "Current assets", "ppe": "Net PPE (net block)",
    "total_assets": "Total assets", "current_liabilities": "Current liabilities", "long_term_debt": "Long-term debt",
    "total_debt": "Total debt", "total_liabilities": "Total liabilities", "total_equity": "Total equity",
    "retained_earnings": "Retained earnings / reserves", "share_capital": "Share capital",
    "operating_cash_flow": "Operating cash flow", "shares_outstanding": "Shares outstanding", "share_price": "Share price",
    "market_cap": "Market capitalisation",
}


@dataclass
class Component:
    key: str
    name: str
    formula: str
    value: Num
    inputs: dict[str, Num] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Score:
    key: str
    name: str
    model: str
    status: str  # "ok" | "missing"
    value: Num
    verdict: str | None  # e.g. "safe" / "grey" / "distress" / "flag" / "no_flag"
    verdict_text: str
    thresholds: str
    formula: str
    period: str
    components: list[Component] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    limitations: str = ""


@dataclass
class Criterion:
    name: str
    test: str
    result: str  # "pass" | "fail" | "missing"
    detail: str


@dataclass
class Piotroski:
    status: str
    period: str
    score: int
    tested: int
    criteria: list[Criterion]
    verdict_text: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Flag:
    severity: str  # "high" | "medium" | "low"
    title: str
    detail: str
    period: str | None = None


@dataclass
class ForensicReport:
    periods: list[str]
    current: str
    prior: str
    beneish: Score
    altman: list[Score]
    piotroski: Piotroski
    flags: list[Flag]
    derived: list[str]
    disclaimer: str


def _ok(v: Num) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _div(a: Num, b: Num) -> Num:
    if not (_ok(a) and _ok(b)) or b == 0:
        return None
    return a / b


class _Data:
    def __init__(self, periods: list[str], items: dict[str, list[Num]]):
        n = len(periods)
        self.n, self.periods = n, periods
        self.items = {k: list(v) for k, v in items.items()}
        self.derived: list[str] = []
        for k, v in self.items.items():
            if len(v) != n:
                raise FinanceInputError(f"'{LABELS.get(k, k)}' has {len(v)} values; expected {n} (one per period).")
        self._derive()

    def get(self, key: str, i: int) -> Num:
        if i < 0:
            return None
        v = self.items.get(key, [None] * self.n)[i]
        return float(v) if _ok(v) else None

    def _fill(self, key: str, fn, note: str):
        vals = self.items.get(key, [None] * self.n)
        made = False
        for i in range(self.n):
            if not _ok(vals[i]):
                try:
                    v = fn(i)
                except TypeError:
                    v = None
                if _ok(v):
                    vals[i] = v
                    made = True
        if made:
            self.items[key] = vals
            self.derived.append(note)

    def _derive(self):
        g = self.get
        self._fill("total_equity", lambda i: g("share_capital", i) + g("retained_earnings", i),
                   "Total equity = share capital + reserves (where total equity was not given).")
        self._fill("total_liabilities", lambda i: g("total_assets", i) - g("total_equity", i),
                   "Total liabilities = total assets − total equity (accounting identity, where not given).")
        self._fill("gross_profit", lambda i: g("revenue", i) - g("cogs", i),
                   "Gross profit = revenue − cost of goods sold (where not given).")
        self._fill("market_cap", lambda i: g("share_price", i) * g("shares_outstanding", i),
                   "Market capitalisation = share price × shares outstanding.")


def _component(key, name, formula, inputs: dict[str, Num], fn, note: str = "") -> Component:
    missing = [k for k, v in inputs.items() if not _ok(v)]
    value = None
    if not missing:
        try:
            value = fn()
        except (ZeroDivisionError, TypeError):
            value = None
        if value is None:
            note = (note + " " if note else "") + "Undefined (a denominator is zero)."
    return Component(key, name, formula, value, inputs, missing, note)


# --------------------------------------------------------------------------- Beneish

def _gmi(gm_p: Num, gm_t: Num) -> float:
    # With a zero or negative margin the ratio flips sign or explodes: -0.10 / -0.20 = 0.5 would read
    # as "margins improving" when they fell. Beneish's index assumes positive margins.
    if not (_ok(gm_p) and _ok(gm_t)) or gm_p <= 0 or gm_t <= 0:
        raise ZeroDivisionError
    return gm_p / gm_t


def beneish(d: _Data, t: int) -> Score:
    p = t - 1
    g = d.get
    notes: list[str] = []
    ltd_key = "long_term_debt"
    if g("long_term_debt", t) is None or g("long_term_debt", p) is None:
        ltd_key = "total_debt"
    sec_note = "Securities are not separated here, so AQI uses 1 − (current assets + net PPE) / total assets."

    def ratio(a, b):
        if not (_ok(a) and _ok(b)) or b == 0:
            raise ZeroDivisionError
        return a / b

    gm_t = _div(g("gross_profit", t), g("revenue", t))
    gm_p = _div(g("gross_profit", p), g("revenue", p))
    comps = [
        _component("DSRI", "Days sales in receivables index", "(Rec_t / Sales_t) / (Rec_t−1 / Sales_t−1)",
                   {"Receivables (t)": g("receivables", t), "Revenue (t)": g("revenue", t),
                    "Receivables (t−1)": g("receivables", p), "Revenue (t−1)": g("revenue", p)},
                   lambda: ratio(ratio(g("receivables", t), g("revenue", t)), ratio(g("receivables", p), g("revenue", p))),
                   "Above 1 means receivables grew faster than sales."),
        _component("GMI", "Gross margin index", "Gross margin_t−1 / Gross margin_t",
                   {"Gross margin (t−1)": gm_p, "Gross margin (t)": gm_t},
                   lambda: _gmi(gm_p, gm_t), "Above 1 means margins are deteriorating. Not calculated when either "
                   "gross margin is zero or negative, because the index then changes meaning."),
        _component("AQI", "Asset quality index", "[1 − (CA_t + PPE_t) / TA_t] / [1 − (CA_t−1 + PPE_t−1) / TA_t−1]",
                   {"Current assets (t)": g("current_assets", t), "Net PPE (t)": g("ppe", t), "Total assets (t)": g("total_assets", t),
                    "Current assets (t−1)": g("current_assets", p), "Net PPE (t−1)": g("ppe", p), "Total assets (t−1)": g("total_assets", p)},
                   lambda: ratio(1 - ratio(g("current_assets", t) + g("ppe", t), g("total_assets", t)),
                                 1 - ratio(g("current_assets", p) + g("ppe", p), g("total_assets", p))),
                   "Above 1 means more costs are being capitalised as soft assets. " + sec_note),
        _component("SGI", "Sales growth index", "Sales_t / Sales_t−1",
                   {"Revenue (t)": g("revenue", t), "Revenue (t−1)": g("revenue", p)},
                   lambda: ratio(g("revenue", t), g("revenue", p)), "High growth creates pressure to keep up appearances."),
        _component("DEPI", "Depreciation index", "[Dep_t−1 / (Dep_t−1 + PPE_t−1)] / [Dep_t / (Dep_t + PPE_t)]",
                   {"Depreciation (t−1)": g("depreciation_amortization", p), "Net PPE (t−1)": g("ppe", p),
                    "Depreciation (t)": g("depreciation_amortization", t), "Net PPE (t)": g("ppe", t)},
                   lambda: ratio(ratio(g("depreciation_amortization", p), g("depreciation_amortization", p) + g("ppe", p)),
                                 ratio(g("depreciation_amortization", t), g("depreciation_amortization", t) + g("ppe", t))),
                   "Above 1 means depreciation is slowing (possibly longer useful lives)."),
        _component("SGAI", "SG&A index", "(SGA_t / Sales_t) / (SGA_t−1 / Sales_t−1)",
                   {"SG&A (t)": g("sga", t), "Revenue (t)": g("revenue", t), "SG&A (t−1)": g("sga", p), "Revenue (t−1)": g("revenue", p)},
                   lambda: ratio(ratio(g("sga", t), g("revenue", t)), ratio(g("sga", p), g("revenue", p)))),
        _component("LVGI", "Leverage index", "[(CL_t + LTD_t) / TA_t] / [(CL_t−1 + LTD_t−1) / TA_t−1]",
                   {"Current liabilities (t)": g("current_liabilities", t), f"{LABELS[ltd_key]} (t)": g(ltd_key, t),
                    "Total assets (t)": g("total_assets", t), "Current liabilities (t−1)": g("current_liabilities", p),
                    f"{LABELS[ltd_key]} (t−1)": g(ltd_key, p), "Total assets (t−1)": g("total_assets", p)},
                   lambda: ratio(ratio(g("current_liabilities", t) + g(ltd_key, t), g("total_assets", t)),
                                 ratio(g("current_liabilities", p) + g(ltd_key, p), g("total_assets", p)))),
        _component("TATA", "Total accruals to total assets", "(Net income_t − Operating cash flow_t) / TA_t",
                   {"Net income (t)": g("net_income", t), "Operating cash flow (t)": g("operating_cash_flow", t),
                    "Total assets (t)": g("total_assets", t)},
                   lambda: ratio(g("net_income", t) - g("operating_cash_flow", t), g("total_assets", t)),
                   "Positive means profits are running ahead of cash."),
    ]
    if ltd_key == "total_debt":
        notes.append("Long-term debt was not given, so total debt is used in LVGI (this can double-count short-term debt).")
    c = {x.key: x.value for x in comps}
    all_missing = sorted({m for x in comps for m in x.missing})
    common = dict(key="beneish", name="Beneish M-score", period=f"{d.periods[p]} → {d.periods[t]}", components=comps,
                  limitations="A screening model estimated on US manufacturing firms (1982–1992). Indian and service "
                              "companies, mergers, and large one-off items can trigger false alarms. A flag means "
                              "'look closer at the notes', not 'fraud'.")
    if all(c[k] is not None for k in ("DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA")):
        m = (-4.84 + 0.920 * c["DSRI"] + 0.528 * c["GMI"] + 0.404 * c["AQI"] + 0.892 * c["SGI"] + 0.115 * c["DEPI"]
             - 0.172 * c["SGAI"] + 4.679 * c["TATA"] - 0.327 * c["LVGI"])
        flag = m > -1.78
        return Score(**common, model="8-variable (Beneish 1999)", status="ok", value=m,
                     verdict="flag" if flag else "no_flag",
                     verdict_text=("Above −1.78: the pattern resembles companies that manipulated earnings. Check the notes on "
                                   "revenue recognition, receivables and capitalised costs." if flag else
                                   "Below −1.78: no manipulation pattern detected by this model."),
                     thresholds="M > −1.78 → possible manipulator (some analysts use the stricter −2.22).",
                     formula="M = −4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI",
                     missing=[], notes=notes)
    if all(c[k] is not None for k in ("DSRI", "GMI", "AQI", "SGI", "DEPI")):
        m = -6.065 + 0.823 * c["DSRI"] + 0.906 * c["GMI"] + 0.593 * c["AQI"] + 0.717 * c["SGI"] + 0.107 * c["DEPI"]
        flag = m > -2.22
        notes.append("SG&A, leverage or accruals inputs were missing, so the 5-variable model was used: "
                     + ", ".join(k for k in ("SGAI", "LVGI", "TATA") if c[k] is None) + " not available.")
        return Score(**common, model="5-variable (Beneish 1999)", status="ok", value=m,
                     verdict="flag" if flag else "no_flag",
                     verdict_text=("Above −2.22: the pattern resembles companies that manipulated earnings." if flag else
                                   "Below −2.22: no manipulation pattern detected by this model."),
                     thresholds="M > −2.22 → possible manipulator (5-variable model).",
                     formula="M = −6.065 + 0.823·DSRI + 0.906·GMI + 0.593·AQI + 0.717·SGI + 0.107·DEPI",
                     missing=all_missing, notes=notes)
    undefined = [x.key for x in comps[:5] if x.value is None and not x.missing]
    reason = (f"{', '.join(undefined)} cannot be calculated because a denominator is zero, so the score cannot be calculated."
              if undefined and not all_missing else
              "Not enough data: the score needs at least DSRI, GMI, AQI, SGI and DEPI for two periods.")
    return Score(**common, model="—", status="missing", value=None, verdict=None,
                 verdict_text=reason,
                 thresholds="M > −1.78 (8-variable) or > −2.22 (5-variable) → possible manipulator.",
                 formula="M = −4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI",
                 missing=all_missing, notes=notes)


# --------------------------------------------------------------------------- Altman

def altman(d: _Data, t: int) -> list[Score]:
    g = d.get
    ta = g("total_assets", t)
    wc = (g("current_assets", t) - g("current_liabilities", t)) if _ok(g("current_assets", t)) and _ok(g("current_liabilities", t)) else None
    x1 = _component("X1", "Working capital / Total assets", "(CA − CL) / TA",
                    {"Current assets": g("current_assets", t), "Current liabilities": g("current_liabilities", t), "Total assets": ta},
                    lambda: wc / ta, "Liquidity.")
    x2 = _component("X2", "Retained earnings / Total assets", "RE / TA",
                    {"Retained earnings / reserves": g("retained_earnings", t), "Total assets": ta},
                    lambda: g("retained_earnings", t) / ta, "Cumulative profitability. Indian 'Reserves' may include more than retained earnings.")
    x3 = _component("X3", "EBIT / Total assets", "EBIT / TA", {"EBIT": g("operating_income", t), "Total assets": ta},
                    lambda: g("operating_income", t) / ta, "Operating return on assets.")
    x4m = _component("X4", "Market value of equity / Total liabilities", "Market cap / TL",
                     {"Market capitalisation": g("market_cap", t), "Total liabilities": g("total_liabilities", t)},
                     lambda: g("market_cap", t) / g("total_liabilities", t), "Solvency cushion at market value.")
    x4b = _component("X4", "Book equity / Total liabilities", "Equity / TL",
                     {"Total equity": g("total_equity", t), "Total liabilities": g("total_liabilities", t)},
                     lambda: g("total_equity", t) / g("total_liabilities", t), "Solvency cushion at book value.")
    x5 = _component("X5", "Sales / Total assets", "Revenue / TA", {"Revenue": g("revenue", t), "Total assets": ta},
                    lambda: g("revenue", t) / ta, "Asset turnover.")
    period = d.periods[t]
    lim = ("Developed on US firms; best used to compare a company with its own history and peers. "
           "Very low liabilities make X4 large and push the score up.")
    out = []

    def build(key, name, model, comps, weights, const, zones, formula, extra_note=""):
        vals = [c.value for c in comps]
        missing = sorted({m for c in comps for m in c.missing})
        notes = [extra_note] if extra_note else []
        if any(v is None for v in vals):
            return Score(key, name, model, "missing", None, None,
                         "Not enough data: " + (", ".join(missing) if missing else "a denominator is zero") + ".",
                         zones[2], formula, period, comps, missing, notes, lim)
        z = const + sum(w * v for w, v in zip(weights, vals))
        safe, distress = zones[0], zones[1]
        verdict = "safe" if z > safe else "distress" if z < distress else "grey"
        text = {"safe": f"Above {safe}: safe zone — low near-term bankruptcy risk by this model.",
                "grey": f"Between {distress} and {safe}: grey zone — monitor leverage and cash flow.",
                "distress": f"Below {distress}: distress zone — elevated financial-distress risk; check debt maturities and cash."}[verdict]
        return Score(key, name, model, "ok", z, verdict, text, zones[2], formula, period, comps, [], notes, lim)

    out.append(build("altman_z2", "Altman Z''-score", "Non-manufacturing / emerging markets (Z'')",
                     [x1, x2, x3, x4b], [6.56, 3.26, 6.72, 1.05], 0.0, (2.6, 1.1, "Z'' > 2.6 safe · 1.1–2.6 grey · < 1.1 distress"),
                     "Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4 (book equity)",
                     "Recommended for service, IT and non-manufacturing companies, and for unlisted firms."))
    out.append(build("altman_z", "Altman Z-score", "Original (listed manufacturers, 1968)",
                     [x1, x2, x3, x4m, x5], [1.2, 1.4, 3.3, 0.6, 1.0], 0.0, (2.99, 1.81, "Z > 2.99 safe · 1.81–2.99 grey · < 1.81 distress"),
                     "Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 (market value) + 1.0·X5",
                     "Designed for listed manufacturing companies; needs the share price and shares outstanding."))
    return out


# --------------------------------------------------------------------------- Piotroski

def piotroski(d: _Data, t: int) -> Piotroski:
    g = d.get
    p = t - 1
    notes: list[str] = []
    beginning = g("total_assets", p - 1) is not None
    if not beginning:
        notes.append("Piotroski scales by beginning-of-year assets. With fewer than three periods, year-end total assets "
                     "are used for ROA and asset turnover.")

    def assets_for(i):  # denominator for period i
        return g("total_assets", i - 1) if beginning else g("total_assets", i)

    crit: list[Criterion] = []

    def add(name, test, cond, detail_ok, inputs_ok=True):
        if not inputs_ok or cond is None:
            crit.append(Criterion(name, test, "missing", "Inputs missing."))
        else:
            crit.append(Criterion(name, test, "pass" if cond else "fail", detail_ok))

    roa_t, roa_p = _div(g("net_income", t), assets_for(t)), _div(g("net_income", p), assets_for(p))
    cfo_t = g("operating_cash_flow", t)
    add("Profitable", "ROA > 0", None if roa_t is None else roa_t > 0, f"ROA {roa_t:.2%}" if roa_t is not None else "")
    add("Positive operating cash flow", "CFO > 0", None if cfo_t is None else cfo_t > 0, f"CFO {cfo_t:,.0f}" if cfo_t is not None else "")
    add("Improving ROA", "ROA_t > ROA_t−1", None if roa_t is None or roa_p is None else roa_t > roa_p,
        f"{roa_p:.2%} → {roa_t:.2%}" if roa_t is not None and roa_p is not None else "")
    ni_t = g("net_income", t)
    add("Earnings backed by cash", "CFO > Net income", None if cfo_t is None or ni_t is None else cfo_t > ni_t,
        f"CFO {cfo_t:,.0f} vs NI {ni_t:,.0f}" if cfo_t is not None and ni_t is not None else "")
    ltd = "long_term_debt" if g("long_term_debt", t) is not None and g("long_term_debt", p) is not None else "total_debt"
    lev_t, lev_p = _div(g(ltd, t), g("total_assets", t)), _div(g(ltd, p), g("total_assets", p))
    lev_cond = None if lev_t is None or lev_p is None else (lev_t < lev_p or (lev_t == 0 and lev_p == 0))
    add("Lower leverage", f"{LABELS[ltd]} / TA fell (or stayed at zero)", lev_cond,
        f"{lev_p:.2%} → {lev_t:.2%}" if lev_t is not None and lev_p is not None else "")
    if ltd == "total_debt":
        notes.append("Long-term debt was not given; total debt is used for the leverage test.")
    cr_t, cr_p = _div(g("current_assets", t), g("current_liabilities", t)), _div(g("current_assets", p), g("current_liabilities", p))
    add("Better liquidity", "Current ratio rose", None if cr_t is None or cr_p is None else cr_t > cr_p,
        f"{cr_p:.2f} → {cr_t:.2f}" if cr_t is not None and cr_p is not None else "")
    sh_t, sh_p = g("shares_outstanding", t), g("shares_outstanding", p)
    add("No new shares issued", "Shares outstanding did not increase", None if sh_t is None or sh_p is None else sh_t <= sh_p,
        f"{sh_p:,.0f} → {sh_t:,.0f}" if sh_t is not None and sh_p is not None else "")
    gm_t, gm_p = _div(g("gross_profit", t), g("revenue", t)), _div(g("gross_profit", p), g("revenue", p))
    add("Higher gross margin", "Gross margin rose", None if gm_t is None or gm_p is None else gm_t > gm_p,
        f"{gm_p:.2%} → {gm_t:.2%}" if gm_t is not None and gm_p is not None else "")
    at_t, at_p = _div(g("revenue", t), assets_for(t)), _div(g("revenue", p), assets_for(p))
    add("Higher asset turnover", "Revenue / assets rose", None if at_t is None or at_p is None else at_t > at_p,
        f"{at_p:.2f} → {at_t:.2f}" if at_t is not None and at_p is not None else "")

    score = sum(c.result == "pass" for c in crit)
    tested = sum(c.result != "missing" for c in crit)
    if tested == 0:
        text, status = "Not enough data to test any criterion.", "missing"
    else:
        status = "ok"
        base = f"{score} of {tested} tests passed" + (f" ({9 - tested} could not be tested)" if tested < 9 else "")
        if tested == 9:
            band = "strong (8–9)" if score >= 8 else "weak (0–2)" if score <= 2 else "average (3–7)"
            text = f"{base}: {band} financial position by Piotroski's scale."
        else:
            text = f"{base}. Piotroski's bands (8–9 strong, 0–2 weak) need all nine tests."
    return Piotroski(status, f"{d.periods[p]} → {d.periods[t]}", score, tested, crit, text, notes)


# --------------------------------------------------------------------------- cash-quality flags

def _growth(a: Num, b: Num) -> Num:
    if not (_ok(a) and _ok(b)) or a <= 0:
        return None
    return b / a - 1


def cash_flags(d: _Data) -> list[Flag]:
    g, n, P = d.get, d.n, d.periods
    flags: list[Flag] = []
    # profits not turning into cash
    ni_all = [g("net_income", i) for i in range(n)]
    cfo_all = [g("operating_cash_flow", i) for i in range(n)]
    pairs = [(x, c) for x, c in zip(ni_all, cfo_all) if x is not None and c is not None]
    if len(pairs) >= 2:
        tot_ni, tot_cfo = sum(x for x, _ in pairs), sum(c for _, c in pairs)
        if tot_ni > 0 and tot_cfo / tot_ni < 0.8:
            flags.append(Flag("high", "Profits are not turning into cash",
                              f"Over {len(pairs)} periods, operating cash flow was {tot_cfo / tot_ni:.0%} of net income "
                              "(below 80%). Check receivables, inventory and revenue-recognition policies."))
    for i in range(n):
        if ni_all[i] is not None and cfo_all[i] is not None and ni_all[i] > 0 and cfo_all[i] < 0:
            flags.append(Flag("high", "Profit with negative operating cash flow",
                              "Net income was positive but operating cash flow was negative.", P[i]))
    for i in range(1, n):
        rg = _growth(g("revenue", i - 1), g("revenue", i))
        for key, label in (("receivables", "Receivables"), ("inventory", "Inventory")):
            xg = _growth(g(key, i - 1), g(key, i))
            if rg is not None and xg is not None and xg - rg > 0.10 and xg > 0.10:
                flags.append(Flag("medium", f"{label} growing faster than sales",
                                  f"{label} grew {xg:.0%} while revenue grew {rg:.0%}. This can signal aggressive "
                                  "credit terms, channel stuffing or slow-moving stock.", P[i]))
        eq_t, eq_p = g("total_equity", i), g("total_equity", i - 1)
        if eq_t is not None and eq_t <= 0 and (eq_p is None or eq_p > 0):
            flags.append(Flag("high", "Equity turned zero or negative",
                              "Shareholders' equity is zero or negative: liabilities exceed assets. Debt-to-equity is "
                              "not meaningful here, and the company may be technically insolvent.", P[i]))
        de_t = _div(g("total_debt", i), eq_t) if eq_t is not None and eq_t > 0 else None
        de_p = _div(g("total_debt", i - 1), eq_p) if eq_p is not None and eq_p > 0 else None
        if de_t is not None and de_p is not None and de_t - de_p > 0.25:
            flags.append(Flag("medium", "Debt rising quickly relative to equity",
                              f"Debt-to-equity went from {de_p:.2f} to {de_t:.2f}.", P[i]))
        da_t, da_p = g("depreciation_amortization", i), g("depreciation_amortization", i - 1)
        ppe_t, ppe_p = g("ppe", i), g("ppe", i - 1)
        r_t, r_p = _div(da_t, ppe_t), _div(da_p, ppe_p)
        if r_t is not None and r_p is not None and r_p > 0 and r_t < 0.8 * r_p:
            flags.append(Flag("low", "Depreciation rate fell",
                              f"Depreciation / net PPE fell from {r_p:.1%} to {r_t:.1%}. Check for changes in useful lives, "
                              "which raise reported profit.", P[i]))
    for i in range(n):
        oi, pbt = g("other_income", i), g("pretax_income", i)
        if oi is not None and pbt is not None and pbt > 0 and oi / pbt > 0.25:
            flags.append(Flag("medium", "Large share of profit from other income",
                              f"Other income was {oi / pbt:.0%} of profit before tax. Core operations may be weaker than "
                              "headline profit suggests.", P[i]))
        ebit, interest = g("operating_income", i), g("interest_expense", i)
        if ebit is not None and interest is not None and interest > 0 and ebit / interest < 1.5:
            flags.append(Flag("high", "Low interest cover",
                              f"EBIT covers interest only {ebit / interest:.1f} times (below 1.5×).", P[i]))
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f.severity], f.period or ""))
    return flags


def analyse(periods: list[str], items: dict[str, list[Num]]) -> ForensicReport:
    if len(periods) < 2:
        raise FinanceInputError("Red-flag screens compare years, so provide at least two periods.")
    if len(periods) > 20:
        raise FinanceInputError("Provide at most 20 periods.")
    unknown = sorted(set(items) - set(LABELS) - set(STANDARD_ITEMS))
    if unknown:
        raise FinanceInputError(f"Unknown item(s): {', '.join(unknown)}.")
    d = _Data(periods, items)
    t = d.n - 1
    return ForensicReport(
        periods=periods, current=periods[t], prior=periods[t - 1],
        beneish=beneish(d, t), altman=altman(d, t), piotroski=piotroski(d, t), flags=cash_flags(d),
        derived=d.derived,
        disclaimer="These are screening models, not proof of fraud, distress or quality. Read them with the annual "
                   "report's notes, the auditor's report and industry context. Educational use — not investment advice.",
    )
