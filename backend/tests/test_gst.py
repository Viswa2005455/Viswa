"""GST: return selection, GSTR-3B set-off (s.49 / Rule 88A), GSTR-1 tables, 2B reconciliation."""

import datetime as dt

import pytest

from app.finance import FinanceInputError
from app.finance.gst import (GSTProfile, GSTR3BIn, Heads, Invoice, Purchase, gstr1, gstr3b, late_fee_per_return, norm_invoice,
                             reconcile_2b, select_returns, valid_gstin)
from app.files.registers import PURCHASE_TEMPLATE, SALES_TEMPLATE, read_register

OWN = "27AAPFU0939F1ZV"


def forms(r):
    return {x["form"]: x for x in r["returns"]}


def test_return_selection_and_due_dates():
    r = forms(select_returns(GSTProfile(state_code="27", aggregate_turnover_prev_fy=3e7, qrmp=True, year=2026, month=9)))
    assert r["GSTR-1"]["next_due"] == "2026-10-13" and r["GSTR-3B"]["next_due"] == "2026-10-22"
    assert r["GSTR-9"]["optional"] is False and "GSTR-9C" not in r
    r = forms(select_returns(GSTProfile(state_code="07", aggregate_turnover_prev_fy=1e7, qrmp=True, month=9)))
    assert r["GSTR-3B"]["next_due"] == "2026-10-24" and r["GSTR-9"]["optional"] is True
    r = forms(select_returns(GSTProfile(state_code="07", qrmp=True, month=8)))
    assert r["PMT-06"]["next_due"] == "2026-09-25" and r["IFF"]["optional"] and "GSTR-3B" not in r
    big = select_returns(GSTProfile(aggregate_turnover_prev_fy=6e7, qrmp=True, month=9))
    assert big["warnings"] and forms(big)["GSTR-1"]["next_due"] == "2026-10-11" and "GSTR-9C" in forms(big)
    comp = select_returns(GSTProfile(registration="composition", state_code="12", aggregate_turnover_prev_fy=8e6, month=9))
    assert comp["warnings"] and forms(comp)["CMP-08"]["next_due"] == "2026-10-18" and forms(comp)["GSTR-4"]["next_due"] == "2027-06-30"
    reg = select_returns(GSTProfile(registration="not_registered", state_code="36", aggregate_turnover_prev_fy=2.5e6))
    assert reg["registration_required"] and reg["threshold"] == 2e6
    reg = select_returns(GSTProfile(registration="not_registered", state_code="27", aggregate_turnover_prev_fy=2.5e6))
    assert not reg["registration_required"] and reg["threshold"] == 4e6
    assert forms(select_returns(GSTProfile(registration="tds_deductor", month=9)))["GSTR-7"]["next_due"] == "2026-10-10"
    with pytest.raises(FinanceInputError):
        select_returns(GSTProfile(state_code="99"))


def test_setoff_minimises_cash_and_follows_section_49():
    r = gstr3b(GSTR3BIn(outward_tax=Heads(igst=100, cgst=50, sgst=50), itc_available=Heads(igst=120, cgst=10, sgst=30)))
    assert r["total_cash"] == pytest.approx(40) and r["utilisation"]["igst->igst"] == 100
    assert r["closing_credit"]["igst"] == pytest.approx(0)
    r = gstr3b(GSTR3BIn(outward_tax=Heads(cgst=100, sgst=100), itc_available=Heads(igst=50, cgst=100)))
    assert r["utilisation"]["igst->sgst"] == 50 and r["cash"]["sgst"] == 50 and "cgst->sgst" not in r["utilisation"]
    r = gstr3b(GSTR3BIn(outward_tax=Heads(igst=100), itc_available=Heads(cgst=60, sgst=60)))
    assert r["utilisation"]["cgst->igst"] == 60 and r["utilisation"]["sgst->igst"] == 40 and r["closing_credit"]["sgst"] == 20
    # IGST credit is used against CGST/SGST before their own credit (s.49A), keeping CGST/SGST credit
    r = gstr3b(GSTR3BIn(outward_tax=Heads(cgst=100, sgst=100), itc_available=Heads(igst=100, cgst=100, sgst=100)))
    assert r["utilisation"]["igst->cgst"] + r["utilisation"]["igst->sgst"] == 100 and r["total_cash"] == 0
    # reverse charge always in cash; reversals reduce credit
    r = gstr3b(GSTR3BIn(outward_tax=Heads(cgst=10, sgst=10), reverse_charge_tax=Heads(igst=18), itc_available=Heads(cgst=50, sgst=50),
                        itc_reversed=Heads(cgst=5, sgst=5)))
    assert r["cash"]["igst"] == 18 and r["closing_credit"]["cgst"] == 35
    with pytest.raises(FinanceInputError):
        gstr3b(GSTR3BIn(itc_available=Heads(igst=1), itc_reversed=Heads(igst=2)))


def test_rule_86b_interest_and_late_fee():
    r = gstr3b(GSTR3BIn(outward_tax=Heads(cgst=100, sgst=100), itc_available=Heads(cgst=1000, sgst=1000), taxable_value_month=6e6))
    assert r["total_cash"] == pytest.approx(2) and r["credit_used"] == pytest.approx(198)
    r = gstr3b(GSTR3BIn(outward_tax=Heads(igst=1000), due_date=dt.date(2026, 10, 20), filing_date=dt.date(2026, 10, 30),
                        aggregate_turnover=1e7))
    assert r["interest"]["amount"] == pytest.approx(1000 * 0.18 * 10 / 365) and r["late_fee"]["fee"] == 500
    assert late_fee_per_return(30, True, None)["fee"] == 500 and late_fee_per_return(100, False, 3e7)["fee"] == 5000


def test_gstin_validation():
    assert valid_gstin(OWN) and not valid_gstin("27AAPFU0939F1ZX") and not valid_gstin("27AAPFU0939F1V") and not valid_gstin("")


def test_gstr1_from_template():
    reg = read_register("sales.csv", SALES_TEMPLATE.encode())
    assert len(reg["rows"]) == 4 and reg["columns"]["gstin"] == "Customer GSTIN"
    inv = [Invoice(**{k: v for k, v in r.items()}) for r in reg["rows"]]
    out = gstr1(inv, OWN, aggregate_turnover=3e7)
    t = out["tables"]
    assert [r["number"] for r in t["b2b"]] == ["INV-001"] and [r["number"] for r in t["b2cl"]] == ["INV-002"]
    assert t["b2cs"][0]["place_of_supply"] == "27" and t["b2cs"][0]["taxable_value"] == 20000
    assert t["cdnr"][0]["note_type"] == "C"
    assert out["liability"] == {"igst": 27000, "cgst": 9900, "sgst": 9900, "cess": 0}
    hsn = {(h["section"], h["hsn"]): h["taxable_value"] for h in t["hsn"]}
    assert hsn[("B2B", "8471")] == 90000 and hsn[("B2C", "8471")] == 150000 and out["errors"] == 0


def test_gstr1_flags_problems():
    out = gstr1([Invoice(number="A1", gstin="27AAPFU0939F1ZX", taxable_value=100, rate=18, igst=18, hsn="84"),
                 Invoice(number="A1", taxable_value=100, rate=18, hsn="8471"),
                 Invoice(number="A2", place_of_supply="29", taxable_value=50_000, rate=18, cgst=4500, sgst=4500, hsn="8471")], OWN)
    msgs = " | ".join(i["message"] for i in out["issues"])
    assert "not valid" in msgs and "Duplicate" in msgs and "should carry IGST" in msgs and "Intra-state supply" in msgs
    assert "fewer than 4 digits" in msgs
    with pytest.raises(FinanceInputError):
        gstr1([Invoice(number="x", taxable_value=1, rate=5)], "BAD")


def test_reconcile_2b():
    books = [Purchase(OWN, "S/2026/101", taxable_value=50_000, cgst=4500, sgst=4500),
             Purchase(OWN, "S/2026/102", taxable_value=10_000, cgst=900, sgst=900),
             Purchase(OWN, "S/2026/103", taxable_value=20_000, igst=3600),
             Purchase(OWN, "S/2026/104", taxable_value=5_000, cgst=450, sgst=450)]
    portal = [Purchase(OWN, "s-2026-101 ", taxable_value=50_000, cgst=4500, sgst=4500),
              Purchase(OWN, "S/2026/102", taxable_value=10_000, cgst=850, sgst=850),
              Purchase(OWN, "S/2026/1O3", taxable_value=20_000, igst=3600),
              Purchase(OWN, "S/2026/200", taxable_value=1_000, igst=180)]
    r = reconcile_2b(books, portal)
    s = r["summary"]
    assert s["matched"]["count"] == 1 and s["mismatch"]["count"] == 1 and s["probable"]["count"] == 1
    assert s["missing_in_2b"]["count"] == 1 and s["missing_in_books"]["count"] == 1
    assert s["credit_safe_to_claim"] == pytest.approx(9000 + 1700 + 3600)
    assert norm_invoice("INV-0007") == norm_invoice("inv 0007") and norm_invoice("007") == "7"


def test_register_reader_two_row_header_and_purchases():
    csv = ("GSTR-2B B2B invoices,,,,,,\n"
           "GSTIN of supplier,Invoice details,,Taxable Value (₹),Tax Amount,,\n"
           ",Invoice number,Invoice Date,,Integrated Tax(₹),Central Tax(₹),State/UT Tax(₹)\n"
           f"{OWN},X-1,01/09/2026,\"1,000\",180,,\n"
           "Total,,,1000,180,,\n")
    reg = read_register("2b.csv", csv.encode())
    assert reg["rows"][0]["number"] == "X-1" and reg["rows"][0]["taxable_value"] == 1000 and reg["rows"][0]["igst"] == 180
    assert reg["skipped"] == 1
    assert read_register("p.csv", PURCHASE_TEMPLATE.encode())["rows"][0]["cgst"] == 4500
    with pytest.raises(ValueError):
        read_register("x.csv", b"a,b\n1,2\n")


def test_tax_api(client):
    r = client.post("/api/tax/individual", json={"salary": 1_300_000})
    assert r.status_code == 200 and r.json()["new"]["total_tax"] == 26_000
    assert client.post("/api/tax/itr-form", json={"total_income": 900_000}).json()["form"] == "ITR-1"
    assert client.post("/api/tax/entity", json={"entity": "company", "total_income": 1e6}).status_code == 422
    assert client.post("/api/tax/due-dates", json={"category": "audit", "filing_date": "2026-11-25", "total_income": 1e6}).json()["late_filing"]["fee_234f"] == 5000
    assert client.post("/api/gst/returns", json={"state_code": "27", "month": 9}).status_code == 200
    r = client.post("/api/gst/gstr3b", json={"outward_tax": {"igst": 100}, "itc_available": {"igst": 40}})
    assert r.json()["total_cash"] == 60
    r = client.post("/api/gst/gstr1", data={"supplier_gstin": OWN}, files={"file": ("sales.csv", SALES_TEMPLATE.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["liability"]["igst"] == 27000 and r.json()["file"]["rows"] == 4
    r = client.post("/api/gst/reconcile", files={"books": ("b.csv", PURCHASE_TEMPLATE.encode()), "gstr2b": ("p.csv", PURCHASE_TEMPLATE.encode())})
    assert r.json()["summary"]["matched"]["count"] == 1
    t = client.get("/api/gst/template/sales")
    assert t.status_code == 200 and "Invoice number" in t.text and "attachment" in t.headers["content-disposition"]
    assert client.post("/api/gst/gstr1", data={"supplier_gstin": OWN}, files={"file": ("x.pdf", b"%PDF-1.4")}).status_code == 422


def test_tax_api_requires_sign_in(anon_client):
    assert anon_client.post("/api/tax/individual", json={}).status_code == 401
    assert anon_client.post("/api/gst/gstr3b", json={}).status_code == 401
