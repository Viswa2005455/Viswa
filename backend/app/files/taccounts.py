"""Read two-sided ("T-format", To / By) accounts: the Trading and Profit & Loss account and the
Balance Sheet as Indian accountants and Tally print them, with expenses / liabilities on the left
and income / assets on the right, each side with its own Amount column.

Each account found is rewritten as a one-period statement (label, amount) so the existing
statement and ratio engines can use it. Every amount keeps the cell it came from. Totals the
statement engines need (revenue, cost of goods sold, equity, current assets…) are worked out from
the lines and shown with the cells they add up; they are checked against the file's own totals.

A workbook can hold the accounts of several businesses (an accountant's working file). Only one
business is used for calculations, so their figures are never mixed: the one whose name matches
the file name, else the first in the workbook. The others are listed by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from openpyxl.utils import get_column_letter

LEFT_HEAD = re.compile(r"^(particulars|expenditure|expenses|liabilities|debit|dr\.?|payments)$", re.I)
RIGHT_HEAD = re.compile(r"^(particulars|income|assets|credit|cr\.?|receipts)$", re.I)
AMOUNT_HEAD = re.compile(r"^(amount|amt\.?|rs\.?|₹|inr|amount\s*\(?(rs\.?|₹|inr)\)?)$", re.I)
TITLE = re.compile(r"balance\s*sheet|profit\s*(&|and)\s*loss|trading|receipts\s*(&|and)\s*payments|income\s*(&|and)\s*expenditure|"
                   r"capital\s*account|computation", re.I)
STOP = re.compile(r"^assessee$|^for\s.*$|^partner|^proprietor$|^auditor", re.I)
MARKER = re.compile(r"^(to|by)\.?$", re.I)
DATE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")
MAX_BLOCK_ROWS = 120


@dataclass
class Item:
    side: str            # "L" or "R"
    label: str
    amount: float
    ref: str
    group: str = ""
    marker: bool = False
    row: int = 0


@dataclass
class Block:
    sheet: str
    entity: str
    title: str
    kind: str            # "pl" or "bs"
    period: str
    first_row: int
    last_row: int
    items: list[Item] = field(default_factory=list)
    totals: dict[str, list[tuple[float, str]]] = field(default_factory=lambda: {"L": [], "R": []})


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("₹", "").replace("Rs.", "")
    if not s or s in ("-", "—"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        f = float(s.strip("()"))
    except ValueError:
        return None
    return -f if neg else f


def _period(title: str) -> str:
    m = DATE.search(title)
    if not m:
        return "Year"
    mo, y = int(m.group(2)), int(m.group(3))
    y = y + 2000 if y < 100 else y
    start = y - 1 if mo <= 3 else y
    return f"FY{start}-{(start + 1) % 100:02d}"


def _header(row: list[Any]) -> tuple[int, int, int, int] | None:
    """(left label col, left amount col, right label col, right amount col) for a T-account heading row."""
    cells = [(c, _text(v)) for c, v in enumerate(row) if _text(v)]
    for i, (lc, lt) in enumerate(cells):
        if not LEFT_HEAD.match(lt):
            continue
        rest = cells[i + 1:]
        la = next(((c, t) for c, t in rest if AMOUNT_HEAD.match(t)), None)
        if not la:
            continue
        rl = next(((c, t) for c, t in rest if c > la[0] and RIGHT_HEAD.match(t)), None)
        if not rl:
            continue
        ra = next(((c, t) for c, t in rest if c > rl[0] and AMOUNT_HEAD.match(t)), None)
        if ra:
            return lc, la[0], rl[0], ra[0]
    return None


def _context(grid: list[list[Any]], hdr: int, floor: int) -> tuple[str, str]:
    """Entity name and title from the text rows just above a heading row. The search stops at the
    previous account, a signature line ("ASSESSEE") or a gap of four empty rows."""
    title, names, gap = "", [], 0
    for r in range(hdr - 1, max(floor, hdr - 14) - 1, -1):
        t = " ".join(_text(v) for v in grid[r] if _text(v))
        if not t:
            gap += 1
            if title and gap >= 4:
                break
            continue
        gap = 0
        if STOP.match(t):
            break
        if not title and TITLE.search(t):
            title = t
            continue
        if title:
            names.append(t)
    names = [t for t in reversed(names) if not re.match(r"^(pan|gstin|doc|accounting year|a\.?y\.?)\b", t, re.I) and not DATE.search(t)]
    # the name, plus the next line when it names the business rather than an address ("PROP : M/S …", "CONTRACTOR")
    entity = names[0] if names else ""
    if len(names) > 1 and not re.search(r"\d", names[1]):
        entity = f"{entity} · {names[1]}"
    return entity, title


def _side(row: list[Any], cols: range, amount_col: int) -> tuple[str, bool, int | None, float | None, bool]:
    """(label, has To/By marker, label column, amount, amount cell holds an error)."""
    texts = [(c, _text(row[c])) for c in cols if c < len(row) and _text(row[c])]
    marker = bool(texts) and bool(MARKER.match(texts[0][1]))
    if marker:
        texts = texts[1:]
    texts = [(c, t) for c, t in texts if not re.fullmatch(r"(rs\.?|₹|inr)", t, re.I)]
    label = " ".join(t for _, t in texts).strip().rstrip(":").strip()
    raw = row[amount_col] if amount_col < len(row) else None
    err = isinstance(raw, str) and raw.strip().startswith("#")
    return label, marker, (texts[0][0] if texts else None), _num(raw), err


def find_blocks(sheet: str, grid: list[list[Any]]) -> list[Block]:
    blocks: list[Block] = []
    floor = 0
    r = 0
    while r < len(grid):
        h = _header(grid[r])
        if not h:
            r += 1
            continue
        lc, la, rc, ra = h
        entity, title = _context(grid, r, floor)
        # an account with no name of its own is never merged with another business
        b = Block(sheet, entity or f"Unnamed business ({sheet} row {r + 1})", title, "", _period(title), r + 1, r + 1)
        heading = {"L": "", "R": ""}
        blank = 0
        end = r + 1
        for rr in range(r + 1, min(len(grid), r + 1 + MAX_BLOCK_ROWS)):
            row = grid[rr]
            line = " ".join(_text(v) or ("" if v is None else str(v)) for v in row[: ra + 1]).strip()
            if rr > r + 1 and (_header(row) or (TITLE.search(line) and not _num_in(row, la, ra))):
                break
            if any(STOP.match(_text(v)) for v in row[: ra + 1] if _text(v)):
                end = rr
                break
            if not line:
                blank += 1
                if blank >= 6:
                    break
                continue
            blank = 0
            end = rr
            for side, cols, acol in (("L", range(0, la), la), ("R", range(la + 1, ra), ra)):
                label, marker, _, amount, err = _side(row, cols, acol)
                ref = f"{sheet}!{get_column_letter(acol + 1)}{rr + 1}"
                if label and amount is None and not err:
                    heading[side] = label            # a heading: the lines below belong to it
                    continue
                if not label and amount is not None:
                    b.totals[side].append((amount, ref))
                    continue
                if not label or amount is None:
                    continue
                if marker:
                    heading[side] = ""
                group = heading[side]
                b.items.append(Item(side, label, amount, ref, group, marker, rr + 1))
        b.last_row = end + 1
        floor = end + 1
        labels = " ".join(i.label.lower() for i in b.items)
        if re.search(r"capital\s*account|computation", title, re.I):
            b.kind = ""                      # a capital account or tax computation is not a statement
        elif re.search(r"balance\s*sheet", title, re.I) or ("capital" in labels and "net profit" not in labels and "assets" in
                                                          " ".join(_text(v).lower() for v in grid[r])):
            b.kind = "bs"
        elif re.search(r"gross profit|net profit|net loss", labels):
            b.kind = "pl"
        if b.kind and b.items:
            blocks.append(b)
        r = end + 1
    return blocks


def _num_in(row: list[Any], la: int, ra: int) -> bool:
    return any(_num(row[c]) is not None for c in (la, ra) if c < len(row))


# ---------------------------------------------------------------- rewriting as statements
def _sum(items: list[Item]) -> tuple[float, str]:
    return sum(i.amount for i in items), " + ".join(i.ref.split("!")[-1] for i in items)


def _label(i: Item) -> str:
    return f"{i.group} – {i.label}" if i.group and i.group.lower() not in i.label.lower() else i.label


def _pl_rows(b: Block) -> tuple[list[tuple[str, float, str]], list[str]]:
    rows: list[tuple[str, float, str]] = []
    notes: list[str] = []
    L = [i for i in b.items if i.side == "L"]
    R = [i for i in b.items if i.side == "R"]
    gp_l = next((i for i in L if re.match(r"gross profit", i.label, re.I)), None)
    gp_r = next((i for i in R if re.match(r"gross profit", i.label, re.I)), None)
    gl_r = next((i for i in R if re.match(r"gross loss", i.label, re.I)), None)
    trade_l = [i for i in L if gp_l and i.row < gp_l.row] if gp_l else []
    trade_r = [i for i in R if gp_r and i.row < gp_r.row or (gp_l and not gp_r and i.row <= gp_l.row)] if (gp_l or gp_r) else []
    pl_l = [i for i in L if i not in trade_l and i is not gp_l]
    pl_r = [i for i in R if i not in trade_r and i is not gp_r and i is not gl_r]

    def full(i: Item) -> str:
        return f"{i.group} {i.label}".lower()

    opening = [i for i in trade_l if "opening stock" in full(i)]
    purchases = [i for i in trade_l if "purchase" in full(i) and i not in opening]
    direct = [i for i in trade_l if i not in opening and i not in purchases]
    closing = [i for i in trade_r if "closing stock" in full(i)]
    sales = [i for i in trade_r if i not in closing]
    if not trade_r:  # no trading section: sales are on the P&L side
        closing = [i for i in pl_r if "closing stock" in full(i)]
        sales = [i for i in pl_r if re.search(r"sales|turnover|receipts|revenue|fees|income from", full(i)) and i not in closing]
        pl_r = [i for i in pl_r if i not in sales and i not in closing]
        opening = [i for i in pl_l if "opening stock" in full(i)]
        purchases = [i for i in pl_l if "purchase" in full(i) and i not in opening]
        pl_l = [i for i in pl_l if i not in opening and i not in purchases]
    net_profit = next((i for i in pl_l if re.match(r"net profit", i.label, re.I)), None)
    net_loss = next((i for i in pl_r if re.match(r"net loss", i.label, re.I)), None)
    expenses = [i for i in pl_l if i is not net_profit]
    other_income = [i for i in pl_r if i is not net_loss]
    interest = [i for i in expenses if re.search(r"\binterest\b", i.label, re.I)]
    depreciation = [i for i in expenses if re.search(r"depreciation", i.label, re.I)]

    for i in sales:
        rows.append((f"Sales – {i.group + ' ' if i.group and 'sales' not in i.group.lower() else ''}{i.label}".replace("Sales – Sales", "Sales")
                     if i.group or "sales" not in i.label.lower() else i.label, i.amount, i.ref))
    rev = None
    if sales:
        rev, refs = _sum(sales)
        rows.append(("Revenue", rev, f"total of {refs}" if len(sales) > 1 else sales[0].ref))
    for name, grp in (("Opening stock", opening), ("Purchases", purchases)):
        if grp:
            v, refs = _sum(grp)
            rows.append((name, v, refs if len(grp) > 1 else grp[0].ref))
    for i in direct:
        rows.append((_label(i), i.amount, i.ref))
    if closing:
        v, refs = _sum(closing)
        rows.append(("Closing stock", v, refs if len(closing) > 1 else closing[0].ref))
    cogs = None
    if trade_l or opening or purchases:
        o, p, dct, c = (_sum(g)[0] for g in (opening, purchases, direct, closing))
        cogs = o + p + dct - c
        parts = " + ".join(x for x in ("opening stock" if opening else "", "purchases" if purchases else "",
                                       "direct expenses" if direct else "") if x)
        rows.append(("Cost of goods sold", cogs, f"worked out: {parts}{' − closing stock' if closing else ''}"))
    gp = gp_l.amount if gp_l else (-gl_r.amount if gl_r else None)
    if gp is not None:
        rows.append(("Gross profit", gp, (gp_l or gl_r).ref))
        if rev is not None and cogs is not None and abs(rev - cogs - gp) > 1:
            notes.append(f"Check: revenue − cost of goods sold = {rev - cogs:,.0f}, but the account shows gross profit {gp:,.0f}.")
    elif rev is not None and cogs is not None:
        gp = rev - cogs
        rows.append(("Gross profit", gp, "worked out: revenue − cost of goods sold"))
    for i in expenses:
        rows.append((_label(i), i.amount, i.ref))
    opex = [i for i in expenses if i not in interest]
    if opex:
        v, refs = _sum(opex)
        rows.append(("Operating expenses", v, f"total of {len(opex)} expense lines"))
        if gp is not None:
            rows.append(("Operating income", gp - v, "worked out: gross profit − operating expenses"))
    if interest:
        v, refs = _sum(interest)
        rows.append(("Interest expense", v, refs))
    if depreciation:
        v, refs = _sum(depreciation)
        rows.append(("Depreciation", v, refs))
    if other_income:
        for i in other_income:
            rows.append((_label(i), i.amount, i.ref))
        v, refs = _sum(other_income)
        rows.append(("Other income", v, refs))
    np_ = net_profit.amount if net_profit else (-net_loss.amount if net_loss else None)
    if np_ is not None:
        rows.append(("Net profit", np_, (net_profit or net_loss).ref))
        if gp is not None:
            calc = gp + _sum(other_income)[0] - _sum(expenses)[0]
            if abs(calc - np_) > 1:
                notes.append(f"Check: gross profit + other income − expenses = {calc:,.0f}, but the account shows net profit {np_:,.0f}.")
    for (lt, lref), (rt, rref) in zip(b.totals["L"], b.totals["R"]):
        if abs(lt - rt) > 1:
            notes.append(f"Check: the two sides do not agree ({lref} {lt:,.0f} vs {rref} {rt:,.0f}).")
    return rows, notes


FIXED = re.compile(r"land|building|machine|machinery|plant|vehicle|car\b|tavera|two wheeler|furniture|fitting|equipment|computer|"
                   r"tools|electronic|fixed asset", re.I)


def _bs_rows(b: Block) -> tuple[list[tuple[str, float, str]], list[str]]:
    rows: list[tuple[str, float, str]] = []
    notes: list[str] = []
    L = [i for i in b.items if i.side == "L"]
    R = [i for i in b.items if i.side == "R"]

    def g(i: Item) -> str:
        return f"{i.group} {i.label}".lower()

    debt = [i for i in L if re.search(r"\bloans?\b|borrow|overdraft|\bod\b|cash credit|\bcc\b", g(i))]
    current = [i for i in L if i not in debt and re.search(r"current liabilit|creditor|payable|outstanding|provision", g(i))]
    equity = [i for i in L if i not in debt and i not in current]
    payables = [i for i in current if re.search(r"creditor|payable", i.label, re.I)]
    for i in equity:
        rows.append((_label(i), i.amount, i.ref))
    if equity:
        v, refs = _sum(equity)
        rows.append(("Total equity", v, f"total of {refs}" if len(equity) > 1 else equity[0].ref))
    for i in current:
        rows.append((_label(i), i.amount, i.ref))
    if payables:
        v, refs = _sum(payables)
        rows.append(("Accounts payable", v, refs))
    if current:
        v, refs = _sum(current)
        rows.append(("Total current liabilities", v, f"total of {refs}" if len(current) > 1 else current[0].ref))
    for i in debt:
        rows.append((_label(i), i.amount, i.ref))
    if debt:
        v, refs = _sum(debt)
        rows.append(("Total debt", v, f"total of {refs}" if len(debt) > 1 else debt[0].ref))
    if current or debt:
        rows.append(("Total liabilities", _sum(current)[0] + _sum(debt)[0], "worked out: current liabilities + debt"))

    fixed = [i for i in R if "fixed asset" in i.group.lower() or (not re.search(r"current asset", i.group, re.I) and FIXED.search(i.label))]
    cur = [i for i in R if i not in fixed]
    for i in fixed:
        rows.append((_label(i), i.amount, i.ref))
    if fixed:
        v, refs = _sum(fixed)
        rows.append(("Fixed assets", v, f"total of {refs}" if len(fixed) > 1 else fixed[0].ref))
    for i in cur:
        rows.append((_label(i), i.amount, i.ref))
    stock = [i for i in cur if re.search(r"stock|inventor", i.label, re.I)]
    cash = [i for i in cur if re.search(r"\bcash\b|\bbank\b", i.label, re.I) and i not in stock]
    debtors = [i for i in cur if re.search(r"debtor|receivable", i.label, re.I) and not re.search(r"gst|tax|tds|tcs|input", i.label, re.I)]
    for name, grp in (("Inventories", stock), ("Cash and cash equivalents", cash), ("Trade receivables", debtors)):
        if grp:
            v, refs = _sum(grp)
            rows.append((name, v, refs))
    if cur:
        v, refs = _sum(cur)
        rows.append(("Total current assets", v, f"total of {len(cur)} lines"))
    total_r = b.totals["R"][-1] if b.totals["R"] else None
    rows.append(("Total assets", total_r[0] if total_r else _sum(R)[0], total_r[1] if total_r else "worked out: total of assets"))
    lt, rt = _sum(L)[0], _sum(R)[0]
    if abs(lt - rt) > 1:
        notes.append(f"Check: liabilities {lt:,.0f} and assets {rt:,.0f} do not agree.")
    for side, items in (("L", L), ("R", R)):
        if b.totals[side] and abs(b.totals[side][-1][0] - _sum(items)[0]) > 1:
            notes.append(f"Check: the lines on the {'liabilities' if side == 'L' else 'assets'} side add up to {_sum(items)[0]:,.0f}, "
                         f"but the total in {b.totals[side][-1][1]} is {b.totals[side][-1][0]:,.0f}.")
    return rows, notes


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]{3,}", s.lower()) if t not in ("xlsx", "xls", "csv", "the", "and", "pvt", "ltd")}


def statement_sheets(grids: list[tuple[str, list[list[Any]]]], file_name: str = "") -> tuple[list[dict], list[str]]:
    """Statement grids for the business this file is about: [{"name", "grid", "refs", "source"}], plus notes."""
    blocks = [b for title, grid in grids for b in find_blocks(title, grid)]
    if not blocks:
        return [], []
    entities: list[str] = []
    for b in blocks:
        if b.entity not in entities:
            entities.append(b.entity)
    fname = _tokens(re.sub(r"\.[a-z0-9]+$", "", file_name.replace("_", " ")))
    chosen = max(entities, key=lambda e: (len(_tokens(e) & fname), -entities.index(e)))
    out, notes = [], []
    for b in blocks:
        if b.entity != chosen:
            continue
        rows, n = (_pl_rows(b) if b.kind == "pl" else _bs_rows(b))
        if not rows:
            continue
        kind = "Profit and loss" if b.kind == "pl" else "Balance sheet"
        out.append({"name": f"{b.sheet} · {kind} {b.period}"[:60], "grid": [["Line item", b.period], *[[r[0], r[1]] for r in rows]],
                     "refs": [r[2] for r in rows], "kind": b.kind,
                     "source": {"kind": "two-sided account", "sheet": b.sheet, "rows": f"{b.first_row}–{b.last_row}",
                                "entity": b.entity, "title": b.title}})
        notes += [f"{kind} {b.period}: {x}" for x in n]
    names = ", ".join(f"{b.sheet} rows {b.first_row}–{b.last_row}" for b in blocks if b.entity == chosen)
    notes.insert(0, f"Two-sided (To / By) accounts of {chosen or 'this business'} read from {names}; totals such as revenue and "
                    "cost of goods sold are worked out from the lines and show the cells they add up.")
    others = [e for e in entities if e != chosen]
    if others:
        notes.insert(1, "This workbook also holds accounts of " + "; ".join(others) +
                     ". They are not mixed into these calculations: save each business in its own file to analyse it.")
    return out, notes
