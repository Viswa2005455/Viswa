"""Recommend analysis workflows for a parsed file and suggest statement-line mappings.

Recommendations are suggestions only; the UI asks the user to confirm mappings.
"""

from __future__ import annotations

import re

from ..finance.ratios import ITEMS

# Synonyms used to map statement line labels to ratio-engine items.
SYNONYMS: dict[str, list[str]] = {
    "revenue": [r"^(total )?revenue(s)?( from operations)?$", r"^(net )?sales$", r"^turnover$", r"^total income$"],
    "cogs": [r"^cost of (goods sold|sales|revenue)$", r"^cogs$", r"^cost of materials consumed$"],
    "operating_income": [r"^operating (income|profit)$", r"^ebit$", r"^profit from operations$"],
    "depreciation_amortization": [r"^depreciation( and|&| &) amorti[sz]ation( expense)?$", r"^d&a$", r"^depreciation$"],
    "interest_expense": [r"^interest( expense)?$", r"^finance costs?$"],
    "net_income": [r"^net (income|profit)$", r"^profit (for the (year|period)|after tax)$", r"^pat$"],
    "operating_cash_flow": [r"^(net )?cash (flow )?(generated )?from operating activities$", r"^operating cash flow$"],
    "cash": [r"^cash( and|&| &) (cash )?equivalents$", r"^cash$"],
    "receivables": [r"^(accounts|trade) receivables?$", r"^debtors$", r"^receivables$"],
    "inventory": [r"^inventor(y|ies)$", r"^stock$"],
    "current_assets": [r"^total current assets$", r"^current assets$"],
    "total_assets": [r"^total assets$"],
    "current_liabilities": [r"^total current liabilities$", r"^current liabilities$"],
    "accounts_payable": [r"^(accounts|trade) payables?$", r"^creditors$"],
    "total_debt": [r"^total (debt|borrowings)$", r"^borrowings$"],
    "total_liabilities": [r"^total liabilities$"],
    "gross_profit": [r"^gross (profit|margin)$"],
    "operating_expenses": [r"^(total )?operating expenses$", r"^opex$", r"^(total )?other expenses$"],
    "ebitda": [r"^ebitda$"],
    "pretax_income": [r"^profit before tax(ation)?$", r"^pbt$", r"^(income|earnings) before (income )?tax(es)?$"],
    "income_tax": [r"^(income )?tax( expense)?$", r"^total tax expense$", r"^provision for tax(ation)?$"],
    "ppe": [r"^property,? plant (and|&) equipment( net)?$", r"^ppe$", r"^fixed assets$"],
    "capex": [r"^capital expenditure$", r"^capex$", r"^purchase of (property,? plant (and|&) equipment|fixed assets)$"],
    "investing_cash_flow": [r"^(net )?cash (flow )?(used in |from )?investing activities$"],
    "financing_cash_flow": [r"^(net )?cash (flow )?(used in |from )?financing activities$"],
    "net_change_in_cash": [r"^net (increase|decrease|increase decrease|change) in cash( and cash equivalents)?$"],
    "beginning_cash": [r"^cash( and cash equivalents)? at (the )?beginning of (the )?(year|period)$", r"^opening cash$"],
    "ending_cash": [r"^cash( and cash equivalents)? at (the )?end of (the )?(year|period)$", r"^closing cash$"],
    "total_equity": [r"^total (shareholders'?|stockholders'?)? ?equity$", r"^(shareholders'?|stockholders'?) equity$", r"^total equity$", r"^net worth$"],
}

STATEMENT_KEYWORDS = {
    "income_statement": ["revenue", "sales", "cost of goods", "gross profit", "operating income", "net income", "ebitda", "profit for the year"],
    "balance_sheet": ["total assets", "current assets", "current liabilities", "equity", "inventory", "receivable", "payable"],
    "cash_flow": ["operating activities", "investing activities", "financing activities", "net change in cash", "capital expenditure"],
}


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w&' ]", " ", label.lower())).strip()


def match_item(label: str) -> str | None:
    n = _norm(label)
    for key, pats in SYNONYMS.items():
        if any(re.match(p, n) for p in pats):
            return key
    return None


def suggest_statement_mapping(sheets: list[dict], file_name: str) -> list[dict]:
    """For row-oriented series whose label matches a known item, propose latest & prior values."""
    found: dict[str, dict] = {}
    for sheet in sheets:
        for s in sheet.get("series", []):
            if s["orientation"] != "row":
                continue
            key = match_item(s["label"])
            if not key or key in found or key not in ITEMS:
                continue
            vals, refs, periods = s["values"], s["refs"], s["period_labels"]
            # Ignore non-period columns such as "Growth" or "% of sales" when the row has periods.
            keep = [i for i, p in enumerate(periods) if is_period_label(p)]
            if keep:
                vals, refs, periods = [vals[i] for i in keep], [refs[i] for i in keep], [periods[i] for i in keep]
                years = [_period_year(p) for p in periods]
                if len(years) > 1 and all(y is not None for y in years) and years == sorted(years, reverse=True) and years[0] != years[-1]:
                    vals, refs, periods = vals[::-1], refs[::-1], periods[::-1]  # newest-first -> oldest-first
            found[key] = {
                "item": key, "item_label": ITEMS[key], "source_label": s["label"],
                "value": vals[-1], "source": f"{file_name} › {sheet['name']} › {refs[-1]}", "period": periods[-1],
                "prior_value": vals[-2] if len(vals) >= 2 else None,
                "prior_source": f"{file_name} › {sheet['name']} › {refs[-2]}" if len(vals) >= 2 else None,
                "prior_period": periods[-2] if len(vals) >= 2 else None,
            }
    return list(found.values())


def _text_blob(parsed: dict) -> str:
    parts = [parsed.get("text", "")[:20000]]
    for sh in parsed.get("sheets", []):
        parts += [c["name"] for c in sh.get("columns", [])]
        parts += [s["label"] for s in sh.get("series", [])]
    return " ".join(parts).lower()


def recommend(category: str, parsed: dict) -> list[dict]:
    recs: list[dict] = []

    def add(module: str, route: str, reason: str, confidence: str):
        recs.append({"module": module, "route": route, "reason": reason, "confidence": confidence})

    if parsed.get("kind") == "code":
        add("Data & Code Lab", "/code-lab", "Source code: explanation, review and (approved) sandbox execution.", "high")
        return recs
    if parsed.get("kind") == "archive":
        add("Upload & Analyse", "/upload", "Review the files inside the archive individually.", "high")
        return recs

    blob = _text_blob(parsed)
    scores = {k: sum(1 for kw in kws if kw in blob) for k, kws in STATEMENT_KEYWORDS.items()}
    headers = " ".join(c["name"].lower() for sh in parsed.get("sheets", []) for c in sh.get("columns", []))

    if "budget" in headers and "actual" in headers:
        add("Variance Analysis", "/variance", "Columns named 'Budget' and 'Actual' were found.", "high")
    if scores["income_statement"] >= 2:
        add("Ratio Analysis", "/ratios", "Looks like an income statement (profitability ratios, margins).", "high" if scores["income_statement"] >= 3 else "medium")
        add("Forecasting", "/forecasting", "Revenue and profit lines can be projected forward.", "medium")
    if scores["balance_sheet"] >= 2:
        add("Ratio Analysis", "/ratios", "Looks like a balance sheet (liquidity and leverage).", "high" if scores["balance_sheet"] >= 3 else "medium")
    if max(scores.values()) >= 2:
        add("Financial Statements", "/statements", "Statement-style line items: horizontal, vertical and reconciliation checks.", "high" if max(scores.values()) >= 3 else "medium")
    if scores["cash_flow"] >= 2:
        add("Cash Flow & Working Capital", "/cash-flow", "Looks like a cash flow statement.", "medium")
    if re.search(r"\b(project|initial investment|capex|cash flows?)\b", blob) and re.search(r"\b(year|period|t)\s?0\b", blob):
        add("Investment Appraisal", "/investment", "Project cash flows by period were detected (NPV, IRR, payback).", "medium")
    has_series = any(s for sh in parsed.get("sheets", []) for s in sh.get("series", []) if len(s["values"]) >= 4)
    if has_series and not any(r["module"] == "Forecasting" for r in recs):
        add("Forecasting", "/forecasting", "Numeric series with 4+ periods can be forecast.", "low")
    if parsed.get("kind") == "document" and parsed.get("text"):
        add("AI Finance Assistant", "/assistant", "Summarise or ask questions about the document (requires an AI provider and your consent).", "low")

    # de-duplicate by module, keep the highest-confidence reason
    order = {"high": 0, "medium": 1, "low": 2}
    best: dict[str, dict] = {}
    for r in recs:
        if r["module"] not in best or order[r["confidence"]] < order[best[r["module"]]["confidence"]]:
            best[r["module"]] = r
    return sorted(best.values(), key=lambda r: order[r["confidence"]])


REVENUE_HINT = re.compile(r"revenue|sales|income|turnover|receipts|interest earned|grant", re.I)


def suggest_variance_lines(sheets: list[dict], file_name: str) -> dict | None:
    """Find a sheet with Budget and Actual columns and build variance lines with cell references.

    The revenue/expense classification is a keyword guess the user must confirm.
    """
    for sheet in sheets:
        cols = sheet.get("columns", [])
        b = next((c for c in cols if re.search(r"\bbudget(ed)?\b|\bplan\b", c["name"], re.I)), None)
        a = next((c for c in cols if re.search(r"\bactuals?\b", c["name"], re.I)), None)
        label = next((c for c in cols if c["dtype"] == "text"), None)
        if not (b and a and label):
            continue
        by_id = {s["id"]: s for s in sheet.get("series", [])}
        bs, as_ = by_id.get(f"col:{b['index']}"), by_id.get(f"col:{a['index']}")
        if not bs or not as_:
            continue
        lines = []

        def row_of(ref: str) -> int:
            m = re.search(r"row (\d+)", ref) or re.search(r"(\d+)$", ref)
            return int(m.group(1))

        # Column series carry the first-column value of each row as their period label.
        actual_by_row = {row_of(r): (v, r) for v, r in zip(as_["values"], as_["refs"])}
        for v, r, name in zip(bs["values"], bs["refs"], bs["period_labels"]):
            row = row_of(r)
            if row not in actual_by_row or name.strip().isdigit() or re.match(r"^\s*(net|total)\b", name, re.I):
                continue
            av, ar = actual_by_row[row]
            lines.append({"name": name.strip(), "kind": "revenue" if REVENUE_HINT.search(name) else "expense",
                          "budget": v, "actual": av,
                          "source": f"{file_name} › {sheet['name']} › {r} / {ar}"})
        if lines:
            return {"sheet": sheet["name"], "budget_column": b["name"], "actual_column": a["name"], "lines": lines,
                    "note": "Revenue/expense types were guessed from line names. Please confirm before relying on the result."}
    return None


_YEAR = re.compile(r"(?:FY\s?)?((?:19|20)\d{2})|FY\s?(\d{2})\b", re.I)


def _period_year(label: str) -> int | None:
    m = _YEAR.search(label)
    if not m:
        return None
    return int(m.group(1)) if m.group(1) else 2000 + int(m.group(2))


_PERIODISH = re.compile(r"\b(?:FY|CY|H[12]|Q[1-4])\s?(?:FY)?\s?'?\d{2,4}\b|\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-']*\d{2,4}\b", re.I)


def is_period_label(label: str) -> bool:
    return bool(_PERIODISH.search(label))


def _statement_of(sheet_name: str, labels: list[str]) -> str:
    blob = (sheet_name + " " + " ".join(labels)).lower()
    scores = {
        "income": sum(kw in blob for kw in STATEMENT_KEYWORDS["income_statement"]) + 2 * ("income" in sheet_name.lower() or "p&l" in sheet_name.lower() or "profit" in sheet_name.lower()),
        "balance": sum(kw in blob for kw in STATEMENT_KEYWORDS["balance_sheet"]) + 2 * ("balance" in sheet_name.lower()),
        "cashflow": sum(kw in blob for kw in STATEMENT_KEYWORDS["cash_flow"]) + 2 * ("cash" in sheet_name.lower()),
    }
    return max(scores, key=scores.get)


def suggest_statements(sheets: list[dict], file_name: str) -> list[dict]:
    """Turn statement-shaped sheets (labels in a column, periods across) into statement grids.

    Periods are reordered oldest-first when headers are years in descending order (common in
    annual reports). Values keep their source cell reference.
    """
    out = []
    for sheet in sheets:
        rows = [s for s in sheet.get("series", []) if s["orientation"] == "row"]
        if len(rows) < 2:
            continue
        periods = [c["name"] for c in sheet.get("columns", []) if c["dtype"] == "number"]
        periods = [p for p in periods if any(p in r["period_labels"] for r in rows)]
        # Keep only reporting-period columns; "Growth" or "Budget/Actual" columns are not periods.
        periods = [p for p in periods if is_period_label(p)]
        if not periods:
            continue
        years = [_period_year(p) for p in periods]
        reversed_ = all(y is not None for y in years) and len(years) > 1 and years == sorted(years, reverse=True) and years[0] != years[-1]
        if reversed_:
            periods = periods[::-1]
        statement = _statement_of(sheet["name"], [r["label"] for r in rows])
        lines, used = [], set()
        for r in rows:
            vals, refs = [], []
            for p in periods:
                if p in r["period_labels"]:
                    i = r["period_labels"].index(p)
                    vals.append(r["values"][i])
                    refs.append(r["refs"][i])
                else:
                    vals.append(None)
                    refs.append(None)
            key = match_item(r["label"])
            if key in used:
                key = None
            if key:
                used.add(key)
            src_refs = [x for x in refs if x]
            lines.append({"label": r["label"], "key": key, "values": vals,
                          "source": f"{file_name} › {sheet['name']} › {src_refs[0]}–{src_refs[-1]}" if src_refs else None})
        out.append({"sheet": sheet["name"], "statement": statement, "periods": periods, "reordered": reversed_, "lines": lines})
    return out
