"""Screener.in workbook import."""

import pytest

from app.files.screener import NotScreener, parse_screener
from app.finance.forensic import analyse

from .screener_fixture import screener_bytes


def test_parses_annual_blocks_with_sources():
    r = parse_screener(screener_bytes())
    assert r["company"] == "TATA CONSULTANCY SERVICES LTD"
    assert r["periods"] == ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025"]
    by = {l["key"]: l for l in r["lines"] if l["key"]}
    assert by["revenue"]["values"][-1] == 255324 and by["revenue"]["source"] == "Data Sheet!B17–F17"
    assert by["net_income"]["values"][0] == 32430
    assert by["total_assets"]["values"][-1] == 152020
    assert by["operating_cash_flow"]["values"][-1] == 48908
    # quarterly "Sales" must not overwrite the annual series
    assert len(by["revenue"]["values"]) == 5
    assert any("Quarterly results were found and skipped" in n for n in r["notes"])


def test_derived_lines_are_labelled_and_market_data_found():
    r = parse_screener(screener_bytes())
    by = {l["key"]: l for l in r["lines"] if l["key"]}
    assert by["total_equity"]["values"][-1] == 362 + 94394 and by["total_equity"]["source"] == "derived"
    assert "derived" in by["operating_income"]["label"]
    assert by["operating_income"]["values"][-1] == 64648 + 796
    assert r["market"]["share_price"][-1] == 3600 and r["market"]["shares_outstanding"][-1] == 361.8
    # approximations are offered separately, never applied automatically
    assert "current_assets" not in by and "current_assets" in r["approximations"]


def test_imported_company_feeds_red_flags():
    r = parse_screener(screener_bytes())
    items = {l["key"]: l["values"] for l in r["lines"] if l["key"]}
    items.update(r["market"])
    rep = analyse(r["periods"], items)
    z = {s.key: s for s in rep.altman}
    assert z["altman_z"].status == "missing"  # needs current assets/liabilities
    items.update({k: v["values"] for k, v in r["approximations"].items()})
    z = {s.key: s for s in analyse(r["periods"], items).altman}
    assert z["altman_z"].status == "ok" and z["altman_z2"].status == "ok"


def test_rejects_other_workbooks():
    from openpyxl import Workbook
    import io

    buf = io.BytesIO()
    Workbook().save(buf)
    with pytest.raises(NotScreener):
        parse_screener(buf.getvalue())


def test_screener_endpoint(client):
    up = client.post("/api/uploads", files=[("files", ("TCS.xlsx", screener_bytes()))]).json()["results"][0]
    assert up["ok"], up
    r = client.post(f"/api/analysis/screener/{up['upload']['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["company"].startswith("TATA")
    csv = client.post("/api/uploads", files=[("files", ("a.csv", b"x,y\n1,2\n"))]).json()["results"][0]["upload"]
    assert client.post(f"/api/analysis/screener/{csv['id']}").status_code == 422


def test_cogs_approximation_enables_beneish():
    r = parse_screener(screener_bytes())
    cogs = r["approximations"]["cogs"]
    assert cogs["values"][-1] == 0 + 0 + 48000 - 0 and "approx." in cogs["label"]
    items = {l["key"]: l["values"] for l in r["lines"] if l["key"]}
    items.update(r["market"])
    items.update({k: v["values"] for k, v in r["approximations"].items()})
    assert analyse(r["periods"], items).beneish.status == "ok"
