"""Excel files whose formulas have no saved results (e.g. Screener.in / Moneycontrol exports)."""

import io

import pytest
from openpyxl import Workbook

from app.files.formula_eval import FormulaError, Unsupported, WorkbookEvaluator
from app.files.tabular import parse_xlsx


def evaluator(cells: dict[str, object], sheet: str = "S") -> WorkbookEvaluator:
    """Build a one-sheet evaluator from {"A1": value-or-formula}."""
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

    grid = [[None] * 10 for _ in range(10)]
    formulas = {}
    for addr, v in cells.items():
        col, row = coordinate_from_string(addr)
        r, c = row - 1, column_index_from_string(col) - 1
        if isinstance(v, str) and v.startswith("="):
            formulas[(r, c)] = v
        else:
            grid[r][c] = v
    return WorkbookEvaluator({sheet: grid}, {sheet: formulas})


def calc(formula: str, **cells):
    ev = evaluator({**cells, "J10": formula})
    return ev.cell("S", 9, 9)


def test_arithmetic_and_precedence():
    assert calc("=1+2*3") == 7
    assert calc("=(1+2)*3") == 9
    assert calc("=2^3^2") == 512  # Excel: right-associative here is fine for this case
    assert calc("=-2^2") == 4  # Excel applies negation before ^
    assert calc("=50%") == 0.5
    assert calc('="FY"&2025') == "FY2025"
    assert calc("=A1/B1-1", A1=1200, B1=1000) == pytest.approx(0.2)


def test_functions():
    cells = dict(A1=10, A2=20, A3=None, A4="text", A5=30)
    assert calc("=SUM(A1:A5)", **cells) == 60
    assert calc("=AVERAGE(A1:A5)", **cells) == 20  # blanks and text in ranges are ignored, like Excel
    assert calc("=MAX(A1:A5)-MIN(A1:A5)", **cells) == 20
    assert calc("=COUNT(A1:A5)", **cells) == 3 and calc("=COUNTA(A1:A5)", **cells) == 4
    assert calc("=ROUND(2.5,0)") == 3 and calc("=ROUND(-2.5,0)") == -3 and calc("=ROUND(1.2345,2)") == 1.23
    assert calc("=ROUNDUP(1.21,1)") == pytest.approx(1.3) and calc("=ROUNDDOWN(1.29,1)") == pytest.approx(1.2)
    assert calc("=SUMPRODUCT(A1:A2,B1:B2)", A1=2, A2=3, B1=4, B2=5) == 23
    assert calc("=MEDIAN(1,3,2,4)") == 2.5 and calc("=MOD(-7,3)") == 2 and calc("=INT(-1.5)") == -2
    assert calc('=IF(A1>5,"big","small")', A1=10) == "big"
    assert calc("=AND(TRUE,A1>5)", A1=10) is True and calc("=NOT(OR(FALSE,FALSE))") is True


def test_errors_and_iferror():
    assert isinstance(calc("=A1/0", A1=5), FormulaError)
    assert calc("=A1/0", A1=5).code == "#DIV/0!"
    assert calc('=IFERROR(A1/B1,"n/a")', A1=5, B1=0) == "n/a"
    assert calc("=IFERROR(A1/B1,0)", A1=6, B1=3) == 2
    # IF only evaluates the branch it needs, so the error branch is never reached
    assert calc("=IF(B1=0,0,A1/B1)", A1=5, B1=0) == 0
    assert calc('=A1+1', A1="abc").code == "#VALUE!"
    assert calc("=Nope!A1").code == "#REF!"


def test_circular_and_unsupported():
    ev = evaluator({"A1": "=B1+1", "B1": "=A1+1"})
    v = ev.cell("S", 0, 0)
    assert isinstance(v, FormulaError) and v.code == "#CIRCULAR"
    ev = evaluator({"A1": "=VLOOKUP(1,B1:C3,2,FALSE)"})
    with pytest.raises(Unsupported):
        ev.cell("S", 0, 0)
    assert ev.unsupported == {"VLOOKUP": 1}
    with pytest.raises(Unsupported):
        evaluator({"A1": "=SUM(B:B)"}).cell("S", 0, 0)  # whole-column ranges are not supported


def test_function_names_with_digits_are_not_cell_references():
    with pytest.raises(Unsupported):  # LOG10 is a function, not cell LOG10
        evaluator({"A1": "=LOG10(100)"}).cell("S", 0, 0)


def test_long_chains_do_not_crash():
    # 3,000 cells each referring to the one above: evaluated top-down, so the chain stays shallow.
    wb = Workbook()
    ws = wb.active
    ws["A1"] = 1
    for r in range(2, 3001):
        ws[f"A{r}"] = f"=A{r - 1}+1"
    buf = io.BytesIO()
    wb.save(buf)
    sheet = parse_xlsx(buf.getvalue())["sheets"][0]
    assert sheet["formulas_calculated"] == 2999 and sheet["formulas_without_cached_value"] == 0


def screener_style_workbook() -> bytes:
    """Like a Screener.in export: values in 'Data Sheet', formulas elsewhere, no saved results,
    and a formula-only column at the right edge (this crashed the parser with IndexError)."""
    wb = Workbook()
    data = wb.active
    data.title = "Data Sheet"
    data.append(["Narration", "Mar-23", "Mar-24", "Mar-25"])
    data.append(["Sales", 225458, 240893, 255324])
    data.append(["Net profit", 42147, 46099, 48797])
    data.append(["Other income", 3449, 4422, 0])
    pl = wb.create_sheet("Profit & Loss")
    pl.append(["Narration", "Mar-23", "Mar-24", "Mar-25", "Growth"])
    for r, label in ((2, "Sales"), (3, "Net profit")):
        pl.cell(r, 1, label)
        for c in "BCD":
            pl[f"{c}{r}"] = f"='Data Sheet'!{c}{r}"
        pl[f"E{r}"] = f"=D{r}/C{r}-1"
    pl["A4"] = "Net margin"
    for c in "BCD":
        pl[f"{c}4"] = f"=IFERROR({c}3/{c}2,\"\")"
    pl["A5"] = "Other income growth"
    pl["D5"] = "=D6/C6-1"  # refers to blank cells -> #DIV/0!, must stay blank, not 0
    pl["A6"] = "Unsupported"
    pl["B6"] = "=XLOOKUP(1,B2:D2,B3:D3)"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_screener_style_workbook_is_parsed_and_calculated():
    sheets = {s["name"]: s for s in parse_xlsx(screener_style_workbook())["sheets"]}
    pl = sheets["Profit & Loss"]
    rows = pl["preview"]["rows"]
    assert pl["n_cols"] == 5  # the formula-only Growth column is kept
    assert rows[1][1:4] == [225458, 240893, 255324]
    assert rows[1][4] == pytest.approx(255324 / 240893 - 1)
    assert rows[3][3] == pytest.approx(48797 / 255324)
    assert rows[4][3] is None  # #DIV/0! is left blank, never turned into zero
    assert rows[5][1] is None  # unsupported function is left blank
    assert "B2" in pl["calculated_cells"] and "E3" in pl["calculated_cells"]
    assert pl["formulas_calculated"] == 11 and pl["formulas_without_cached_value"] == 2
    assert any("calculated them" in w for w in pl["warnings"])
    assert any("could not be calculated" in w for w in pl["warnings"])
    sales = next(s for s in pl["series"] if s["label"] == "Sales")
    assert sales["refs"][:3] == ["B2", "C2", "D2"] and sales["calculated_values"] == 4
    # values that were really stored in the file are not marked as calculated
    assert sheets["Data Sheet"]["formulas_calculated"] == 0


def test_screener_style_upload_succeeds(client):
    r = client.post("/api/uploads", files=[("files", ("TCS.xlsx", screener_style_workbook()))])
    res = r.json()["results"][0]
    assert res["ok"], res
    assert res["upload"]["status"] != "failed"
