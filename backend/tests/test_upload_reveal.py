"""The upload page shows the extracted data and the calculations straight after an upload.

These tests follow the same path the page takes: POST the file, read the analysis from that one
response, send the suggested statement lines to the existing engines, and check the results
against hand-calculated values.
"""

import io

import pytest
from openpyxl import Workbook


def workbook(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def post(client, name: str, data: bytes) -> dict:
    r = client.post("/api/uploads", files=[("files", (name, data))])
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["ok"], res
    return res["upload"]


PL = [["Line item", "FY2024", "FY2025"], ["Revenue", 11000, 12480], ["Gross profit", 3740, 4120]]


def test_post_returns_the_full_analysis_like_get(client):
    up = post(client, "pl.xlsx", workbook(PL))
    assert up["analysis"]["kind"] == "tabular"  # no longer stripped from the upload response
    got = client.get(f"/api/uploads/{up['id']}").json()
    for k in ("id", "name", "extension", "category", "summary", "recommendations", "statement_mapping", "variance_lines", "statements", "analysis"):
        assert up[k] == got[k], k


def test_series_cells_and_gross_margin_from_the_engine(client):
    up = post(client, "pl.xlsx", workbook(PL))
    sheet = up["analysis"]["sheets"][0]
    series = {s["label"]: s for s in sheet["series"] if s["orientation"] == "row"}
    assert set(series) >= {"Revenue", "Gross profit"}
    assert series["Revenue"]["refs"] == ["B2", "C2"] and series["Revenue"]["values"] == [11000, 12480]
    assert series["Gross profit"]["refs"][-1] == "C3"

    # The page sends the suggested statement lines to the statements engine unchanged.
    st = up["statements"][0]
    assert st["periods"] == ["FY2024", "FY2025"]
    keys = {l["label"]: l["key"] for l in st["lines"]}
    assert keys == {"Revenue": "revenue", "Gross profit": "gross_profit"}
    rep = client.post("/api/finance/statements", json={"periods": st["periods"], "lines": [
        {"label": l["label"], "statement": st["statement"], "key": l["key"], "values": l["values"], "source": l["source"]} for l in st["lines"]]}).json()
    # Hand calculation: 4,120 / 12,480 x 100 = 33.0128...%; 3,740 / 11,000 x 100 = 34.0%
    assert rep["metrics"]["gross_margin_pct"] == pytest.approx([3740 / 11000 * 100, 4120 / 12480 * 100])
    assert round(rep["metrics"]["gross_margin_pct"][-1], 1) == 33.0
    revenue = next(l for l in rep["lines"] if l["key"] == "revenue")
    assert revenue["changes"][-1]["pct"] == pytest.approx((12480 - 11000) / 11000 * 100)

    # The ratio engine's gross margin needs COGS, which this file does not have: it reports the
    # input as missing rather than inventing a figure.
    data = {m["item"]: m["value"] for m in up["statement_mapping"]}
    ratios = {r["key"]: r for r in client.post("/api/finance/ratios", json={"data": data}).json()["ratios"]}
    assert ratios["gross_margin"]["status"] == "missing" and ratios["gross_margin"]["value"] is None


def test_ratio_engine_gross_margin_when_cogs_is_in_the_file(client):
    up = post(client, "pl2.xlsx", workbook([["Line item", "FY2024", "FY2025"], ["Revenue", 11000, 12480], ["Cost of goods sold", 7260, 8360]]))
    m = {x["item"]: x for x in up["statement_mapping"]}
    assert m["revenue"]["value"] == 12480 and m["revenue"]["source"].endswith("C2")
    assert m["cogs"]["value"] == 8360 and m["cogs"]["source"].endswith("C3")
    ratios = {r["key"]: r for r in client.post("/api/finance/ratios", json={"data": {k: v["value"] for k, v in m.items()}}).json()["ratios"]}
    # Hand calculation: (12,480 - 8,360) / 12,480 x 100 = 33.0128...%
    assert ratios["gross_margin"]["status"] == "ok"
    assert ratios["gross_margin"]["value"] == pytest.approx((12480 - 8360) / 12480 * 100)


def test_text_note_gives_no_statement_inputs_and_no_ratio(client):
    up = post(client, "note.txt", b"Board meeting notes. Revenue grew strongly this year; margins held up.\n")
    assert up["analysis"]["kind"] != "tabular"
    # Nothing for the engines: no statement lines, no mapping, no variance lines.
    assert not up["statements"] and not up["statement_mapping"] and not up["variance_lines"]
    assert not any(r["module"] in ("Ratio Analysis", "Financial Statements") for r in up["recommendations"])
