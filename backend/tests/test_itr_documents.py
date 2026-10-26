"""Income Tax: read uploaded documents for the facts that decide the ITR form, then choose the form
with the existing rules (/api/tax/itr-form) from the confirmed answers."""

import io

from openpyxl import Workbook

FORM16 = """FORM NO. 16
[See rule 31(1)(a)]
PART A - Certificate under section 203 of the Income-tax Act, 1961 for tax deducted at source on salary
Name and address of the Employer: Northwind Components Ltd   PAN of the Deductor: AAACN1234Q
Name of the Employee: Asha Kumar   PAN of the Employee: ABCPK5678L
Assessment Year 2026-27
PART B
1. Gross Salary (a) Salary as per provisions contained in section 17(1) 11,40,000.00
Income chargeable under the head "Salaries" 10,65,000.00
Gross total income 9,80,000.00
Short term capital gains 0.00
"""


def post(client, name: str, data: bytes) -> str:
    r = client.post("/api/uploads", files=[("files", (name, data))])
    res = r.json()["results"][0]
    assert res["ok"], res
    return res["upload"]["id"]


def read(client, *ids: str) -> dict:
    r = client.post("/api/tax/itr-from-uploads", json={"upload_ids": list(ids)})
    assert r.status_code == 200, r.text
    return r.json()


def facts(out: dict) -> dict:
    return {f["field"]: f for f in out["facts"]}


def itr(client, **answers) -> dict:
    r = client.post("/api/tax/itr-form", json=answers)
    assert r.status_code == 200, r.text
    return r.json()


def test_form16_salary_points_to_itr1_with_evidence_and_masked_pan(client):
    out = read(client, post(client, "form16.txt", FORM16.encode()))
    f = facts(out)
    assert out["documents"][0]["types"][0].startswith("Form 16")
    assert f["salary_or_pension"]["status"] == "found" and f["salary_or_pension"]["value"] is True
    ev = f["salary_or_pension"]["evidence"][0]
    assert ev["file"] == "form16.txt" and ev["where"].startswith("line ")
    # Taxpayer type comes from the employee's PAN ("P" = individual), not the employer's ("C").
    assert f["taxpayer_type"]["value"] == "individual" and f["taxpayer_type"]["status"] == "suggested"
    assert f["total_income"]["value"] == 980000 and f["total_income"]["status"] == "suggested"
    assert "stcg" not in f  # "Short term capital gains 0.00" reports nothing
    assert "ABCPK5678L" not in str(out) and "AAACN1234Q" not in str(out)
    assert any(u["field"] == "foreign_assets_or_income" for u in out["unanswered"])
    # The existing rules choose the form from the confirmed answers.
    r = itr(client, taxpayer_type="individual", total_income=980000, salary_or_pension=True)
    assert r["form"] == "ITR-1"


def test_capital_gains_statement_moves_to_itr2(client):
    wb = Workbook()
    ws = wb.active
    ws.title = "Tax P&L"
    for row in [["Capital gains statement FY 2025-26", None], ["Category", "Amount"],
                ["Short Term Capital Gain (111A)", 45000], ["Long Term Capital Gain - listed equity (112A)", 180000]]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    out = read(client, post(client, "form16.txt", FORM16.encode()), post(client, "gains.xlsx", buf.getvalue()))
    f = facts(out)
    assert f["stcg"]["status"] == "found" and f["stcg"]["evidence"][0]["where"] == "Tax P&L!A3"
    assert f["ltcg_112a"]["value"] == 180000 and f["ltcg_112a"]["status"] == "suggested"
    assert {d["file"] for d in out["documents"]} == {"form16.txt", "gains.xlsx"}
    r = itr(client, taxpayer_type="individual", total_income=980000, salary_or_pension=True, stcg=True, ltcg_112a=180000)
    assert r["form"] == "ITR-2"


def test_presumptive_profession_and_tax_audit(client):
    pl = b"Statement of profit and loss for FY 2025-26\nGross receipts from profession 38,00,000\nIncome computed under section 44ADA at 50%\n"
    f = facts(read(client, post(client, "pl.txt", pl)))
    assert f["presumptive"]["value"] == "44ADA" and f["presumptive"]["status"] == "suggested"
    assert f["business_income"]["value"] is True
    assert itr(client, taxpayer_type="individual", total_income=1900000, business_income=True, presumptive="44ADA")["form"] == "ITR-4"

    audit = b"FORM NO. 3CD\nStatement of particulars required to be furnished under section 44AB\nProfits and gains of business 52,40,000\n"
    f = facts(read(client, post(client, "3cd.txt", audit)))
    assert f["accounts_audited"]["status"] == "found" and f["business_income"]["status"] == "found"
    r = itr(client, taxpayer_type="individual", total_income=5240000, business_income=True, accounts_audited=True)
    assert r["form"] == "ITR-3" and r["due_date_category"] == "audit"


def test_another_users_upload_is_not_readable(client):
    uid = post(client, "form16.txt", FORM16.encode())
    assert client.post("/api/tax/itr-from-uploads", json={"upload_ids": ["0" * 32]}).status_code == 404
    assert client.post("/api/tax/itr-from-uploads", json={"upload_ids": ["../etc"]}).status_code in (400, 422)
    client.post("/api/auth/logout")
    from tests.conftest import register  # a second account
    register(client, email="other@example.com")
    assert client.post("/api/tax/itr-from-uploads", json={"upload_ids": [uid]}).status_code == 404
