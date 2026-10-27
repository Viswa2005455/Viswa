"""Uploads that used to give no calculations: three-statement models with actual and projected
years, annual-report PDFs whose statements are printed as text, and ZIP archives.

Figures are from Crocs, Inc.'s 2025 Form 10-K (consolidated statements of operations), as
printed; every expected value below is read straight from the source line."""

import io
import zipfile

from openpyxl import Workbook

from app.files.documents import statement_tables
from app.files.routing import suggest_statement_mapping, suggest_statements
from app.files.tabular import analyse_grid


def model_workbook() -> bytes:
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a.append(["Assumptions", None, "FY2026E", "FY2027E"])
    a.append(["Revenue growth %", None, 0.02, 0.025])
    a.append(["Gross margin %", None, 0.58, 0.58])
    ws = wb.create_sheet("Income Statement")
    ws.append(["Crocs, Inc. — Income Statement"])
    ws.append(["$ in thousands"])
    ws.append([])
    ws.append(["INCOME STATEMENT", None, "FY2023A", "FY2024A", "FY2025A", "FY2026E", "FY2027E"])
    ws.append([])
    ws.append(["Revenues", None, 3962347, 4102108, 4040647, 4121459.94, 4224496.44])
    ws.append(["Cost of sales", None, -1752337, -1691850, -1683592, -1710405.88, -1753166.02])
    ws.append(["Gross profit", None, 2210010, 2410258, 2357055, 2411054.06, 2471330.42])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def post(client, name: str, data: bytes) -> list[dict]:
    r = client.post("/api/uploads", files=[("files", (name, data))])
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert all(x["ok"] for x in res), res
    return res


def test_model_uses_the_latest_actual_year_not_a_projection(client):
    up = post(client, "model.xlsx", model_workbook())[0]["upload"]
    m = {x["item"]: x for x in up["statement_mapping"]}
    # FY2025A, not FY2027E (the last column)
    assert m["revenue"]["value"] == 4040647 and m["revenue"]["period"] == "FY2025A"
    assert m["revenue"]["source"].endswith("Income Statement › E6")
    assert m["revenue"]["prior_value"] == 4102108 and m["revenue"]["prior_period"] == "FY2024A"
    assert m["revenue"]["projected_left_out"] == ["FY2026E", "FY2027E"]
    # costs shown as negatives are used as positive costs, with a note
    assert m["cogs"]["value"] == 1683592 and m["cogs"]["prior_value"] == 1691850 and "negative" in m["cogs"]["note"]
    sts = up["statements"]
    # the assumptions tab holds only projections and is left out; the income statement keeps actual years
    assert [s["sheet"] for s in sts] == ["Income Statement"]
    assert sts[0]["periods"] == ["FY2023A", "FY2024A", "FY2025A"] and sts[0]["projected_left_out"] == ["FY2026E", "FY2027E"]
    rev = next(line for line in sts[0]["lines"] if line["key"] == "revenue")
    assert rev["values"] == [3962347, 4102108, 4040647]
    # the ratio engine then gives gross margin = (4,040,647 − 1,683,592) / 4,040,647 = 58.33%
    data = {k: v["value"] for k, v in m.items()}
    g = next(r for r in client.post("/api/finance/ratios", json={"data": data}).json()["ratios"] if r["key"] == "gross_margin")
    assert round(g["value"], 2) == 58.33


def test_years_typed_as_numbers_are_headers():
    sh = analyse_grid("P&L", [["Particulars", 2024, 2025], ["Revenue", 1000, 1200], ["Net income", 100, 150]], excel=True)
    assert sh["header_row"] == 1 and [c["name"] for c in sh["columns"]][1:] == ["2024", "2025"]
    m = {x["item"]: x for x in suggest_statement_mapping([sh], "pl.xlsx")}
    assert m["revenue"]["value"] == 1200 and m["revenue"]["period"] == "2025"


def test_pdf_table_without_year_headings_is_not_used():
    # An MD&A table: 2025, 2024, $ change, % change — but the year line was lost in extraction.
    grid = [["Revenues", "$", "4,040,647", "$", "4,102,108", "$", "(61,461)", "(1.5)"],
            ["Cost of sales", "1,683,592", None, "1,691,850", None, "8,258", None, "0.5"]]
    sh = analyse_grid("Page 40 · Table 1", grid, excel=False)
    assert suggest_statement_mapping([sh], "10k.pdf") == []  # never "Revenues = -1.5"
    assert suggest_statements([sh], "10k.pdf") == []


PAGE_69 = """Table of Contents
CROCS, INC. AND SUBSIDIARIES
CONSOLIDATED STATEMENTS OF OPERATIONS
(in thousands, except per share data)
Year Ended December 31,
2025 2024 2023
Revenues $ 4,040,647 $ 4,102,108 $ 3,962,347
Cost of sales 1,683,592 1,691,850 1,752,337
Gross profit 2,357,055 2,410,258 2,210,010
Goodwill impairment 307,000 — —
Interest expense (88,287) (109,264) (161,351)
Net income (loss) $ (81,198) $ 950,071 $ 792,566
F- 4"""


def test_statement_page_read_line_by_line_with_its_years():
    t = statement_tables(["cover page", PAGE_69])
    assert len(t) == 1 and t[0]["page"] == 2 and t[0]["years"] == ["2025", "2024", "2023"]
    assert t[0]["units"] == "(in thousands, except per share data)"
    rows = {r[0]: r[1:] for r in t[0]["grid"][1:]}
    assert rows["Revenues"] == [4040647, 4102108, 3962347]
    assert rows["Goodwill impairment"] == [307000, None, None]  # "—" is nil, not a guessed number
    assert rows["Interest expense"] == [-88287, -109264, -161351]
    assert rows["Net income (loss)"] == [-81198, 950071, 792566]
    assert "F-" not in rows
    sh = analyse_grid(t[0]["name"], t[0]["grid"], excel=False)
    st = suggest_statements([sh], "10k.pdf")[0]
    assert st["periods"] == ["2023", "2024", "2025"] and st["reordered"]  # newest-first years put oldest-first
    m = {x["item"]: x for x in suggest_statement_mapping([sh], "10k.pdf")}
    assert m["revenue"]["value"] == 4040647 and m["revenue"]["period"] == "2025"
    assert m["interest_expense"]["value"] == 88287  # printed as (88,287): used as a positive cost


def test_statement_of_equity_and_plain_pages_are_skipped():
    equity = "CONSOLIDATED STATEMENTS OF STOCKHOLDERS' EQUITY\n2025 2024\nBalance 1 2\nNet 3 4\nOther 5 6\n"
    assert statement_tables([equity, "Just text 2025 2024\nRevenue 1 2"]) == []


def test_zip_files_are_analysed_one_by_one(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Models/model.xlsx", model_workbook())
        z.writestr("notes.txt", "Board notes. Revenue grew.")
    res = post(client, "Templates and Downloads.zip", buf.getvalue())
    archive, *inside = res
    assert archive["upload"]["category"] == "archive" and len(inside) == 2
    assert {x["from_archive"] for x in inside} == {archive["upload"]["id"]}
    names = {x["upload"]["name"]: x["upload"] for x in inside}
    assert set(names) == {"Templates and Downloads › model.xlsx", "Templates and Downloads › notes.txt"}
    model = names["Templates and Downloads › model.xlsx"]
    assert model["statements"][0]["periods"] == ["FY2023A", "FY2024A", "FY2025A"]
    # the archive links each member to its own upload, and does not store the member analysis twice
    kids = {c["path"]: c for c in archive["upload"]["analysis"]["children"]}
    assert kids["Models/model.xlsx"]["upload_id"] == model["id"] and "parsed" not in kids["Models/model.xlsx"]
    # each member keeps its own bytes, so it can be read again later (e.g. by the tax audit)
    listed = {u["id"] for u in client.get("/api/uploads").json()["uploads"]}
    assert model["id"] in listed and client.get(f"/api/uploads/{model['id']}").json()["statements"]


PAGE_73 = """CONSOLIDATED STATEMENTS OF CASH FLOWS
(in thousands)
Year Ended December 31,
2025 2024 2023
Net income (loss) $ (81,198) $ 950,071 $ 792,566
Inventories (13,842) 22,055 86,350
Accounts payable 709 3,951 37,197
Cash provided by operating activities 710,431 992,486 930,444
Purchases of property, equipment, and software (51,231) (69,347) (115,625)
Cash used in investing activities (51,231) (69,347) (115,671)"""


def test_cash_flow_page_gives_capex_but_not_balances():
    t = statement_tables([PAGE_73])[0]
    sh = analyse_grid(t["name"], t["grid"], excel=False)
    st = suggest_statements([sh], "10k.pdf")[0]
    keys = {line["label"]: line["key"] for line in st["lines"]}
    assert st["statement"] == "cashflow"
    assert keys["Cash provided by operating activities"] == "operating_cash_flow"
    assert keys["Purchases of property, equipment, and software"] == "capex"
    # changes in working capital on a cash flow statement are not balance-sheet balances
    assert keys["Inventories"] is None and keys["Accounts payable"] is None
    m = {x["item"]: x for x in suggest_statement_mapping([sh], "10k.pdf", all_items=True)}
    assert "inventory" not in m and m["operating_cash_flow"]["value"] == 710431
    assert m["capex"]["value"] == 51231  # printed as (51,231): an outflow, used as a positive amount
