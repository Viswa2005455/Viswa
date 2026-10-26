"""Read a cash book, bank book or ledger export (Excel or CSV) into transaction rows for the tax
audit checks (Form 3CD clauses 21, 31 and 44, and the cash test of section 44AB).

Columns are matched by header name, ignoring case and punctuation, like the GST registers. A
row is a receipt or a payment from either a pair of columns (Receipt / Payment, Deposit /
Withdrawal, Debit / Credit) or an Amount column with a Type column. The payment mode comes from
a Mode column; when there is none and the sheet or file is called a cash book, every row is
taken as cash and the result says so. Files are read in memory; nothing is executed.
"""

from __future__ import annotations

from typing import Any

from .registers import _grids, _key, parse_date
from .tabular import parse_number

MAX_ROWS = 100_000
FIELDS: dict[str, list[str]] = {
    "date": ["date", "voucherdate", "txndate", "transactiondate", "valuedate", "entrydate", "trandate"],
    "party": ["party", "partyname", "name", "payee", "payer", "paidto", "receivedfrom", "customer", "supplier", "vendor",
              "customername", "suppliername", "vendorname", "personname"],
    "account": ["account", "accounthead", "head", "ledger", "ledgername", "ledgeraccount", "expensehead", "category", "nature",
                "accountname", "group"],
    "particulars": ["particulars"],
    "narration": ["narration", "description", "remarks", "details", "memo", "transactiondetails"],
    "mode": ["mode", "paymentmode", "modeofpayment", "paidby", "paymenttype", "instrument", "method", "instrumenttype", "channel"],
    "amount": ["amount", "amountrs", "amountinr", "value", "transactionamount"],
    "type": ["type", "drcr", "receiptpayment", "direction", "transactiontype", "crdr"],
    "receipt": ["receipt", "receipts", "received", "inflow", "deposit", "deposits", "moneyin", "receiptamount"],
    "payment": ["payment", "payments", "paid", "outflow", "withdrawal", "withdrawals", "moneyout", "paymentamount"],
    "debit": ["debit", "dr", "debitamount", "debitrs"],
    "credit": ["credit", "cr", "creditamount", "creditrs"],
    "gstin": ["gstin", "partygstin", "suppliergstin", "vendorgstin", "gstno", "gstnumber"],
}
_ALIASES = {alias: f for f, aliases in FIELDS.items() for alias in aliases}

TEMPLATE = ("Date,Party,Account head,Narration,Mode,Receipt,Payment,GSTIN\n"
            "2025-04-03,Sharma Traders,Sales,Counter sale,Cash,45000,,\n"
            "2025-04-05,Ravi Transport,Freight,Lorry hire Pune,Cash,,32000,\n"
            "2025-04-05,Office Mart,Office expenses,Stationery,Cash,,12500,27AAPFU0939F1ZV\n"
            "2025-04-09,Anil Mehta,Unsecured loan,Loan received,Cash,50000,,\n"
            "2025-04-12,Bharat Steel,Purchases,Invoice 118,Bank,,240000,27AABCB1234C1Z5\n")


def _header(grid: list[list[Any]]) -> tuple[int, dict[int, str]] | None:
    best = None
    for r in range(min(len(grid), 15)):
        mapping: dict[int, str] = {}
        for c, v in enumerate(grid[r]):
            f = _ALIASES.get(_key(v))
            if f and f not in mapping.values():
                mapping[c] = f
        got = set(mapping.values())
        money = "amount" in got and "type" in got or {"receipt", "payment"} <= got or {"debit", "credit"} <= got
        if "date" in got and money and got & {"party", "account", "particulars", "narration"}:
            if best is None or len(mapping) > len(best[1]):
                best = (r, mapping)
    return best


def _text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def read_ledger(filename: str, data: bytes) -> dict | None:
    """Return {"sheet", "rows", "columns", "skipped", "mode_source", "direction_rule"} or None when no ledger table is found.

    Each row: {date, party, account, narration, receipt, payment, cash (True/False/None), mode, gstin, ref}."""
    try:
        grids = _grids(filename, data)
    except ValueError:
        return None
    found = None
    for title, grid in grids:
        h = _header(grid)
        if h and (found is None or len(h[1]) > len(found[2])):
            found = (title, grid, h[1], h[0])
    if not found:
        return None
    title, grid, mapping, hdr = found
    got = set(mapping.values())
    cash_book = "cash" in f"{title} {filename}".lower() and "bank" not in f"{title} {filename}".lower()
    mode_source = "column" if "mode" in got else "cash book" if cash_book else None
    if {"receipt", "payment"} <= got:
        direction_rule = "Receipt and Payment columns"
    elif {"debit", "credit"} <= got:
        direction_rule = "Debit = receipt, Credit = payment (cash book / bank book convention)"
    else:
        direction_rule = "Amount column with a receipt/payment Type column"
    letters = [_col(i) for i in range(60)]
    rows, skipped = [], 0
    for r in range(hdr + 1, len(grid)):
        vals = grid[r]
        rec = {f: (vals[c] if c < len(vals) else None) for c, f in mapping.items()}
        receipt = payment = None
        if {"receipt", "payment"} <= got:
            receipt, payment = parse_number(rec.get("receipt"))[0], parse_number(rec.get("payment"))[0]
        elif {"debit", "credit"} <= got:
            receipt, payment = parse_number(rec.get("debit"))[0], parse_number(rec.get("credit"))[0]
        else:
            amt = parse_number(rec.get("amount"))[0]
            kind = _key(rec.get("type"))
            if amt is not None:
                if kind.startswith(("r", "dr", "debit", "in", "dep")) and not kind.startswith("refund"):
                    receipt = amt
                elif kind.startswith(("p", "cr", "credit", "out", "with", "exp")):
                    payment = amt
        date = parse_date(rec.get("date"))
        if not date or not (receipt or payment):
            if any(_text(v) for v in rec.values()):
                skipped += 1  # opening balance, totals, blank amounts
            continue
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"At most {MAX_ROWS:,} rows per file.")
        mode = _text(rec.get("mode"))
        if mode_source == "column":
            m = mode.lower()
            cash = True if ("cash" in m or "bearer" in m) else False if m else None
        else:
            cash = True if mode_source == "cash book" else None
        party = _text(rec.get("party")) or _text(rec.get("particulars"))
        account = _text(rec.get("account")) or _text(rec.get("particulars"))
        rows.append({"date": date, "party": party, "account": account, "narration": _text(rec.get("narration")),
                     "receipt": abs(receipt) if receipt else 0.0, "payment": abs(payment) if payment else 0.0,
                     "cash": cash, "mode": mode or ("cash (cash book)" if cash else ""), "gstin": _text(rec.get("gstin")).upper(),
                     "ref": f"{title}!{letters[min(mapping)]}{r + 1}" if mapping else f"{title}!row {r + 1}", "row": r + 1})
    header_row = grid[hdr]
    return {"sheet": title, "rows": rows, "columns": {f: str(header_row[c]) for c, f in mapping.items()}, "skipped": skipped,
            "mode_source": mode_source, "direction_rule": direction_rule}


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s
