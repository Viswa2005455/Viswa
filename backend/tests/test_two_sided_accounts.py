"""Two-sided (To / By) Trading & P&L accounts and balance sheets, as Indian accountants and Tally
print them, with several businesses on one sheet. All names and figures are fictional; every
expected value is worked by hand from the rows below."""

import io

from openpyxl import Workbook

from app.files import taccounts


def workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Accounts"
    rows = [
        [None, "MEENA SILKS"], [None, "12, CAR STREET"], [None, "MADURAI"], [], [],
        [None, "TRADING AND PROFIT & LOSS A/C FOR THE YEAR ENDED 31/03/2025"],
        [None, None, "PARTICULARS", None, "Amount", None, "PARTICULARS", "Amount"], [],
        [None, "To ", "Opening Stock", None, None, "By ", "Sales"],
        [None, None, None, "SILK", 300000, None, "SILK", 900000],
        [None, None, None, "COTTON", 100000, None, "COTTON", 300000],
        [None, "To ", "Purchases", None, 700000, "By ", "Closing Stock", 350000],
        [None, "To ", "Wages", None, 50000],
        [None, "To ", "Gross Profit", None, 400000],
        [None, None, None, None, 1550000, None, None, 1550000],
        [None, "To ", "Rent", None, 60000, "By ", "Gross Profit", 400000],
        [None, "To ", "Salary", None, 120000, "By ", "Interest received", 5000],
        [None, "To ", "Interest on loan", None, 25000],
        [None, "To ", "Net profit", None, 200000],
        [None, None, None, None, 405000, None, None, 405000],
        [None, None, None, None, None, None, None, "ASSESSEE"], [], [],
        [None, "MEENA SILKS"], [None, "12, CAR STREET"], [],
        [None, "BALANCE SHEET AS ON 31/03/2025"],
        [None, None, "LIABILITIES", None, "AMOUNT ", None, "ASSETS", "AMOUNT "], [],
        [None, None, "Capital Account", None, 800000, None, "FIXED ASSETS"],
        [None, None, "Current Liabilities :", None, None, None, "Furniture", 150000],
        [None, None, "Sundry Creditors", None, 250000, None, "CURRENT ASSETS"],
        [None, None, "Bank Loan", None, 100000, None, "Closing Stock", 350000],
        [None, None, None, None, None, None, "Sundry Debtors", 400000],
        [None, None, None, None, None, None, "GST Receivable", 50000],
        [None, None, None, None, None, None, "Cash at Bank", 150000],
        [None, None, None, None, 1150000, None, None, 1100000],
        [None, None, None, None, None, None, None, "ASSESSEE"], [], [], [],
        [None, "RAVI TRADERS"], [None, "4, MAIN ROAD"], [],
        [None, "PROFIT & LOSS ACCOUNT FOR THE YEAR ENDED 31/03/2025"],
        [None, None, "EXPENDITURE", None, "Amount", None, "INCOME", "Amount"],
        [None, "To ", "Purchases", None, 90000, "By ", "Sales", 150000],
        [None, "To ", "Gross Profit", None, 60000],
        [None, None, None, None, 150000, None, None, 150000],
        [None, "To ", "Rent", None, 10000, "By ", "Gross Profit", 60000],
        [None, "To ", "Net profit", None, 50000],
    ]
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def lines(sheet: dict) -> dict:
    return {r[0]: (r[1], ref) for r, ref in zip(sheet["grid"][1:], sheet["refs"])}


def grids() -> list:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(workbook()), data_only=True)
    return [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]


def test_trading_and_pl_account_is_rewritten_with_cells():
    out, notes = taccounts.statement_sheets(grids(), "Meena_Silks.xlsx")
    pl = lines(next(s for s in out if s["kind"] == "pl"))
    assert pl["Sales – SILK"] == (900000, "Accounts!H10")
    assert pl["Revenue"][0] == 1200000                                  # 9,00,000 + 3,00,000
    assert pl["Opening stock"][0] == 400000 and pl["Closing stock"][0] == 350000
    # cost of goods sold = 4,00,000 + 7,00,000 + 50,000 (wages) − 3,50,000 = 8,00,000
    assert pl["Cost of goods sold"][0] == 800000
    assert pl["Gross profit"] == (400000, "Accounts!E14")             # = 12,00,000 − 8,00,000
    assert pl["Operating expenses"][0] == 180000                       # rent + salary (interest kept apart)
    assert pl["Interest expense"][0] == 25000 and pl["Other income"][0] == 5000
    assert pl["Operating income"][0] == 220000                         # 4,00,000 − 1,80,000
    assert pl["Net profit"] == (200000, "Accounts!E19")                # 4,00,000 + 5,000 − 2,05,000
    assert not [n for n in notes if n.startswith("Profit and loss") and "Check:" in n]   # both sides agree


def test_balance_sheet_groups_and_a_side_that_does_not_add_up():
    out, notes = taccounts.statement_sheets(grids(), "Meena_Silks.xlsx")
    bs = lines(next(s for s in out if s["kind"] == "bs"))
    assert bs["Total equity"][0] == 800000 and bs["Total current liabilities"][0] == 250000
    assert bs["Total debt"][0] == 100000 and bs["Total liabilities"][0] == 350000
    assert bs["Fixed assets"][0] == 150000 and bs["Inventories"][0] == 350000
    assert bs["Trade receivables"][0] == 400000                        # GST receivable is not a trade receivable
    assert bs["Total current assets"][0] == 950000
    # assets add up to 11,00,000 but liabilities to 11,50,000: reported, never forced to agree
    assert any("do not agree" in n for n in notes)


def test_businesses_are_never_mixed_and_the_file_name_chooses():
    out, notes = taccounts.statement_sheets(grids(), "Ravi_Traders.xlsx")
    assert [s["source"]["entity"] for s in out] == ["RAVI TRADERS"]
    assert lines(out[0])["Revenue"][0] == 150000
    assert "MEENA SILKS" in notes[1]
    out, _ = taccounts.statement_sheets(grids(), "accounts.xlsx")      # no match: the first business
    assert {s["source"]["entity"] for s in out} == {"MEENA SILKS"}


def test_upload_gives_ratio_inputs(client):
    r = client.post("/api/uploads", files=[("files", ("Meena_Silks.xlsx", workbook()))]).json()["results"][0]
    up = r["upload"]
    m = {x["item"]: x for x in up["statement_mapping"]}
    assert m["revenue"]["value"] == 1200000 and m["revenue"]["period"] == "FY2024-25"
    assert m["cogs"]["value"] == 800000 and m["net_income"]["value"] == 200000
    assert m["current_assets"]["value"] == 950000 and m["current_liabilities"]["value"] == 250000
    assert up["analysis"]["warnings"][0].startswith("Two-sided (To / By) accounts of MEENA SILKS")
    ratios = {x["key"]: x for x in client.post("/api/finance/ratios", json={"data": {k: v["value"] for k, v in m.items()}}).json()["ratios"]}
    assert round(ratios["gross_margin"]["value"], 2) == 33.33          # (12,00,000 − 8,00,000) ÷ 12,00,000
    assert round(ratios["current_ratio"]["value"], 2) == 3.8           # 9,50,000 ÷ 2,50,000
