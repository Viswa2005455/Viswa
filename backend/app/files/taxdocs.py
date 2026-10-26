"""Read uploaded tax documents (Form 16, Form 26AS, AIS/TIS, capital-gains statements, P&L, bank
statements…) for the facts that decide which ITR form applies.

Rule-based and deterministic: every fact carries the file, page/line or cell, and the text it was
read from. Nothing is guessed silently:
* "found"     — the document states it directly (e.g. "Form No. 16", "section 194N", "Tax audit report").
* "suggested" — the wording points to it but needs the user's confirmation (e.g. a P&L could be
                someone else's business; an amount on a line may not be the final figure).
Facts that no document mentions are returned as unanswered questions; the ITR selector then uses
the user's own answers for them.

PAN and Aadhaar numbers are masked in every snippet returned to the browser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PAN = re.compile(r"\b([A-Z]{3})([PCHFATBLJG])([A-Z])(\d{4})([A-Z])\b")
AADHAAR = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
AMOUNT = re.compile(r"(?<![\w.])(?:rs\.?|₹|inr)?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)(?![\w%])", re.I)

QUESTIONS: dict[str, str] = {
    "taxpayer_type": "Taxpayer type",
    "residential_status": "Residential status",
    "total_income": "Total income",
    "salary_or_pension": "Salary or pension",
    "house_properties": "Income from house property (number of properties)",
    "business_income": "Income from business or profession",
    "presumptive": "Presumptive taxation (44AD / 44ADA / 44AE)",
    "partner_remuneration": "Interest, salary or commission from a partnership firm",
    "stcg": "Short-term capital gains",
    "ltcg_112a": "Long-term capital gains on listed equity (112A)",
    "other_capital_gains": "Other capital gains (property, debt funds, unlisted shares…)",
    "agricultural_income": "Agricultural income",
    "director": "Director of a company",
    "unlisted_equity": "Unlisted equity shares held",
    "foreign_assets_or_income": "Foreign assets or foreign income",
    "tds_194n": "TDS under 194N (cash withdrawals)",
    "esop_tax_deferred": "Tax on ESOPs deferred",
    "losses_to_carry_forward": "Losses to carry forward / brought-forward losses",
    "accounts_audited": "Accounts audited (tax audit)",
    "files_under_139_4a_to_4d": "Must file under section 139(4A)–(4D)",
}

DOC_TYPES: list[tuple[str, re.Pattern]] = [
    ("Form 16 (salary TDS certificate)", re.compile(r"\bform\s*(no\.?\s*)?16\b(?!\s*a)|certificate under section 203", re.I)),
    ("Form 16A (non-salary TDS certificate)", re.compile(r"\bform\s*(no\.?\s*)?16\s*a\b", re.I)),
    ("Form 26AS (annual tax statement)", re.compile(r"\b26\s?AS\b|annual tax statement", re.I)),
    ("AIS / TIS (annual information statement)", re.compile(r"annual information statement|taxpayer information summary|\bAIS\b|\bTIS\b")),
    ("Capital gains statement", re.compile(r"capital gains?\s+(statement|report|summary)|realised (gain|p&l)|tax p&l", re.I)),
    ("Profit and loss statement", re.compile(r"profit\s*(and|&)\s*loss|statement of profit", re.I)),
    ("Balance sheet", re.compile(r"\bbalance sheet\b", re.I)),
    ("Tax audit report", re.compile(r"form\s*(no\.?\s*)?3C[ABD]\b|tax audit report", re.I)),
    ("Salary slip", re.compile(r"\b(pay\s?slip|salary slip)\b", re.I)),
    ("Bank statement", re.compile(r"statement of account|opening balance|closing balance", re.I)),
]

# (field, value, status, pattern, note). A rule fires on any line that matches its pattern.
BoolRule = tuple[str, Any, str, re.Pattern, str]
RULES: list[BoolRule] = [
    ("salary_or_pension", True, "found", re.compile(r"\bform\s*(no\.?\s*)?16\b(?!\s*a)|\bgross salary\b|section\s*17\s*\(1\)|under the head\s*\W?salar|\bsalary\b.*\b192\b|\b192\b.*\bsalary\b|\b(family )?pension (received|income)\b|\bpensioner\b", re.I), ""),
    ("house_properties", 1, "suggested", re.compile(r"income from house property|\blet[- ]out\b|self[- ]occupied|interest on (housing|home) loan|section\s*24\s*\(?b\)?", re.I),
     "House property is mentioned; the number of properties is not stated, so 1 is suggested. Enter how many you own."),
    ("business_income", True, "found", re.compile(r"profits? and gains of business", re.I), ""),
    ("business_income", True, "suggested", re.compile(r"income from business|business or profession|\bgross receipts\b", re.I),
     "Business or professional income is mentioned; confirm it is yours."),
    ("business_income", True, "suggested", re.compile(r"profit\s*(and|&)\s*loss|statement of profit|\bturnover\b", re.I),
     "A P&L or turnover figure was found; confirm it is your own business or profession."),
    ("presumptive", "44ADA", "suggested", re.compile(r"\b44\s?ADA\b", re.I), "Section 44ADA is mentioned; confirm you opt for presumptive taxation."),
    ("presumptive", "44AE", "suggested", re.compile(r"\b44\s?AE\b", re.I), "Section 44AE is mentioned; confirm you opt for presumptive taxation."),
    ("presumptive", "44AD", "suggested", re.compile(r"\b44\s?AD\b(?!A)", re.I), "Section 44AD is mentioned; confirm you opt for presumptive taxation."),
    ("partner_remuneration", True, "suggested", re.compile(r"remuneration (from|paid to|to) (the )?partners?|interest on (partners?'?\s*)?capital|share of profit from (the )?firm", re.I),
     "Partner remuneration or interest on capital is mentioned; confirm you received it."),
    ("stcg", True, "found", re.compile(r"short[- ]term capital gains?|\bSTCG\b|section\s*111\s?A\b", re.I), ""),
    ("other_capital_gains", True, "suggested", re.compile(r"section\s*112\b(?!\s?A)|sale of (land|building|property|house|flat)|\bdebt (mutual )?funds?\b|\bindexation\b", re.I),
     "Gains other than listed equity seem to be mentioned; confirm."),
    ("director", True, "suggested", re.compile(r"\bdirector\b.*\bDIN\b|\bDIN\b.*\bdirector\b|director of (the )?company", re.I), "A directorship is mentioned; confirm you were a director during the year."),
    ("unlisted_equity", True, "suggested", re.compile(r"unlisted (equity )?shares", re.I), "Unlisted shares are mentioned; confirm you held them during the year."),
    ("foreign_assets_or_income", True, "found", re.compile(r"schedule\s*FA\b|foreign tax credit|\bform\s*(no\.?\s*)?67\b", re.I), ""),
    ("foreign_assets_or_income", True, "suggested", re.compile(r"foreign (asset|income|bank account|account)|outside india|\bRSUs?\b|\bESPP\b", re.I),
     "Foreign assets or income seem to be mentioned; confirm."),
    ("tds_194n", True, "found", re.compile(r"\b194\s?N\b", re.I), ""),
    ("esop_tax_deferred", True, "suggested", re.compile(r"\bESOPs?\b.*(defer|80-?IAC)|defer.*\bESOPs?\b|section\s*192\s*\(1C\)", re.I), "Deferred ESOP tax is mentioned; confirm it applies to you."),
    ("losses_to_carry_forward", True, "suggested", re.compile(r"(brought|carried) forward (business |capital )?loss|loss(es)? to be carried forward|\bcarry forward\b", re.I),
     "Losses to carry forward are mentioned; confirm."),
    ("accounts_audited", True, "found", re.compile(r"\btax audit\b|section\s*44\s?AB\b|form\s*(no\.?\s*)?3C[ABD]\b", re.I), ""),
    ("files_under_139_4a_to_4d", True, "found", re.compile(r"139\s*\(\s*4\s*[ABCD]\s*\)", re.I), ""),
    ("residential_status", "rnor", "suggested", re.compile(r"not ordinarily resident|\bRNOR\b", re.I), "Residential status 'not ordinarily resident' is mentioned; confirm."),
    ("residential_status", "non_resident", "suggested", re.compile(r"\bnon[- ]resident\b|\bNRI\b", re.I), "Non-resident status is mentioned; confirm."),
]

AMOUNT_RULES: list[tuple[str, re.Pattern, str]] = [
    ("total_income", re.compile(r"total taxable income|gross total income|\btotal income\b", re.I),
     "Read from the document; it may not include income this document does not cover. Confirm the full figure."),
    ("ltcg_112a", re.compile(r"\b112\s?A\b|long[- ]term capital gains?.*(equity|listed|shares|mutual fund)|\bLTCG\b.*(equity|listed)", re.I),
     "Read from the line shown; confirm it is your total long-term gain on listed equity and equity funds."),
    ("agricultural_income", re.compile(r"agricultur(al|e) income", re.I), "Read from the line shown; confirm the amount."),
]
PAN_OWNER = re.compile(r"employee|assessee|deductee|taxpayer|pan of the (employee|assessee|deductee)|permanent account number", re.I)
PAN_TYPE = {"P": "individual", "H": "huf", "F": "firm", "C": "company", "A": "aop_boi", "B": "aop_boi", "T": "trust_or_institution",
            "L": "local_authority", "J": "aop_boi", "G": "local_authority"}


def mask(text: str) -> str:
    """Hide PAN and Aadhaar numbers; the PAN's 4th character (taxpayer type) stays visible."""
    text = PAN.sub(lambda m: f"XXX{m.group(2)}X####{m.group(5)}", text)
    return AADHAAR.sub("XXXX XXXX XXXX", text)


@dataclass
class Line:
    file: str
    where: str
    text: str


@dataclass
class Fact:
    field: str
    value: Any
    status: str  # found | suggested
    evidence: list[dict] = field(default_factory=list)
    note: str = ""


def lines_of(analysis: dict, file: str) -> list[Line]:
    """Every line of text the parser kept, with where it came from (page and line, or sheet and cell)."""
    out: list[Line] = []
    if analysis.get("pages"):
        for p in analysis["pages"]:
            for i, t in enumerate((p.get("text") or "").splitlines(), 1):
                if t.strip():
                    out.append(Line(file, f"page {p['page']}, line {i}", t.strip()))
    elif analysis.get("text"):
        for i, t in enumerate(analysis["text"].splitlines(), 1):
            if t.strip():
                out.append(Line(file, f"line {i}", t.strip()))
    if analysis.get("kind") == "tabular":
        for sh in analysis.get("sheets", []):
            letters = sh.get("preview", {}).get("column_letters", [])
            for r, row in enumerate(sh.get("preview", {}).get("rows", []), 1):
                cells = [(c, v) for c, v in enumerate(row) if v not in (None, "")]
                if not cells:
                    continue
                c0 = cells[0][0]
                ref = f"{letters[c0]}{r}" if c0 < len(letters) else f"row {r}"
                out.append(Line(file, f"{sh['name']}!{ref}", " | ".join(str(v) for _, v in cells)))
    return out


def _amounts(text: str) -> list[float]:
    vals = []
    for m in AMOUNT.finditer(PAN.sub("", text)):
        s = m.group(1)
        if "," not in s and "." not in s and 1990 <= int(s) <= 2099:
            continue  # a year, not an amount
        vals.append(float(s.replace(",", "")))
    return vals


ZERO = re.compile(r"(?:^|[\s:|=₹(])0+(?:\.0+)?(?=$|[\s|)])")


def _only_zero(text: str) -> bool:
    """A line such as "Short-term capital gains | 0.00" reports nothing, so it is not evidence."""
    return not _amounts(text) and bool(ZERO.search(text))


def _ev(line: Line) -> dict:
    return {"file": line.file, "where": line.where, "text": mask(line.text[:200])}


def extract(lines: list[Line]) -> tuple[dict[str, Fact], list[dict]]:
    """Facts from the lines of one or more documents, plus the document types recognised per file."""
    facts: dict[str, Fact] = {}
    rank = {"found": 0, "suggested": 1}

    def add(fld: str, value: Any, status: str, line: Line, note: str = ""):
        f = facts.get(fld)
        if f is None or rank[status] < rank[f.status]:
            facts[fld] = f = Fact(fld, value, status, [], note if status == "suggested" else "")
        if len(f.evidence) < 5 and all(e["where"] != line.where or e["file"] != line.file for e in f.evidence):
            f.evidence.append(_ev(line))

    for line in lines:
        if _only_zero(line.text):
            continue
        for fld, value, status, pat, note in RULES:
            if pat.search(line.text):
                if fld in ("presumptive", "residential_status") and fld in facts and facts[fld].value != value:
                    continue  # the first, most specific mention wins; the user can change it
                add(fld, value, status, line, note)
        for fld, pat, note in AMOUNT_RULES:
            if pat.search(line.text):
                vals = _amounts(line.text)
                if vals and fld not in facts:
                    add(fld, vals[-1], "suggested", line, note)
                elif vals and fld in facts and len(facts[fld].evidence) < 5:
                    facts[fld].evidence.append(_ev(line))

    # Taxpayer type from the 4th character of the taxpayer's own PAN (not the employer's or deductor's).
    owner = next((l for l in lines if PAN.search(l.text) and PAN_OWNER.search(l.text)), None)
    if owner:
        letter = PAN.search(owner.text).group(2)
        kind = PAN_TYPE.get(letter)
        if kind == "firm" and re.search(r"\bLLP\b|limited liability partnership", " ".join(l.text for l in lines), re.I):
            kind = "llp"
        if kind:
            facts["taxpayer_type"] = Fact("taxpayer_type", kind, "suggested", [_ev(owner)],
                                          f"From the 4th character of the PAN ('{letter}'). Confirm this is your PAN, not your employer's.")

    if "presumptive" in facts and "business_income" not in facts:
        facts["business_income"] = Fact("business_income", True, "suggested", list(facts["presumptive"].evidence),
                                        "Presumptive taxation implies business or professional income; confirm.")

    docs: dict[str, list[str]] = {}
    for line in lines:
        for name, pat in DOC_TYPES:
            if pat.search(line.text) and name not in docs.setdefault(line.file, []):
                docs[line.file].append(name)
    return facts, [{"file": f, "types": t} for f, t in docs.items()]
