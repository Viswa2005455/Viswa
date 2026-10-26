"""Tax audit (s.44AB) applicability, ledger cash checks and the Form 3CB / 3CD draft.

Every expected number below is worked by hand in the comment next to it."""

import datetime as dt
import io

import pytest
from openpyxl import Workbook

from app.finance import FinanceInputError
from app.finance.taxaudit import AuditProfile, applicability, due, ledger_checks
from app.files.ledger import read_ledger

CR, L = 10_000_000, 100_000


def app(**kw):
    return applicability(AuditProfile(**kw))


# ---------------------------------------------------------------- applicability
def test_business_cash_test_moves_the_limit_between_1_and_10_crore():
    # ₹8 crore turnover, cash receipts 3% and cash payments 4% → both ≤ 5% → limit ₹10 crore → no audit
    a = app(business_turnover=8 * CR, cash_receipts=3, total_receipts=100, cash_payments=4, total_payments=100)
    assert a["required"] is False and a["form"] is None
    # cash payments 6% > 5% → limit stays ₹1 crore → audit under 44AB(a), Form 3CB for an individual
    a = app(business_turnover=8 * CR, cash_receipts=3, total_receipts=100, cash_payments=6, total_payments=100)
    assert a["required"] is True and a["clauses"] == ["44AB(a)"] and a["form"] == "3CB"
    # s.271B: lower of 0.5% × ₹8 crore = ₹4,00,000 and ₹1,50,000
    assert a["penalty_271b"] == 150_000
    # ₹1.5 crore with no cash figures: cannot decide, and says which figures are missing
    a = app(business_turnover=1.5 * CR)
    assert a["required"] is None and {"cash_receipts", "total_payments"} <= set(a["missing"])
    # small business: ₹90 lakh → no audit; ₹12 crore → audit whatever the cash share
    assert app(business_turnover=90 * L)["required"] is False
    assert app(business_turnover=12 * CR, cash_receipts=0, total_receipts=1, cash_payments=0, total_payments=1)["required"] is True


def test_44ad_proviso_uses_the_2_or_3_crore_limit():
    # 44AD, ₹2.5 crore, cash receipts 4% → 44AD limit ₹3 crore → covered by the proviso → no audit
    a = app(business_turnover=2.5 * CR, presumptive="44AD", cash_receipts=4, total_receipts=100, cash_payments=1, total_payments=100)
    assert a["required"] is False
    # cash receipts 6% → 44AD limit ₹2 crore → 44AD not available → clause (a): ₹2.5 crore with a cash share > 5% → audit
    a = app(business_turnover=2.5 * CR, presumptive="44AD", cash_receipts=6, total_receipts=100, cash_payments=1, total_payments=100)
    assert a["required"] is True and a["clauses"] == ["44AB(a)"]
    # an LLP cannot use 44AD at all
    a = app(taxpayer_type="llp", business_turnover=1.5 * CR, presumptive="44AD", cash_receipts=6, total_receipts=100,
            cash_payments=6, total_payments=100)
    assert a["required"] is True


def test_profession_and_presumptive_clauses():
    assert app(activity="profession", professional_receipts=60 * L)["clauses"] == ["44AB(b)"]  # ₹60 lakh > ₹50 lakh
    assert app(activity="profession", professional_receipts=45 * L)["required"] is False
    # 44ADA, profit below 50%: new-regime exemption is ₹4,00,000
    base = dict(activity="profession", professional_receipts=40 * L, presumptive="44ADA", profit_below_presumptive=True)
    assert app(**base, total_income=3.5 * L)["required"] is False
    assert app(**base, total_income=5 * L)["clauses"] == ["44AB(d)"]
    # old regime, below 60: exemption ₹2,50,000 → ₹3,50,000 is above it
    assert app(**base, total_income=3.5 * L, regime="old")["clauses"] == ["44AB(d)"]
    # 44AD(4): a firm has no basic exemption, so any positive income triggers clause (e)
    assert app(taxpayer_type="firm", business_turnover=50 * L, opted_out_of_44ad=True, total_income=10_000)["clauses"] == ["44AB(e)"]
    # 44AE claiming lower profits → clause (c)
    assert app(business_turnover=40 * L, presumptive="44AE", profit_below_presumptive=True)["clauses"] == ["44AB(c)"]
    # lower 44AD profit alone (no 44AD(4)) does not trigger clause (e)
    assert app(business_turnover=80 * L, presumptive="44AD", profit_below_presumptive=True, total_income=9 * L)["required"] is False


def test_company_gets_form_3ca_and_bad_inputs_are_refused():
    a = app(taxpayer_type="company", business_turnover=20 * CR)
    assert a["form"] == "3CA" and a["forms"] == "Form 3CA + Form 3CD"
    with pytest.raises(FinanceInputError):
        app(business_turnover=10, cash_receipts=20, total_receipts=10)


def test_due_dates_from_circular_07_2026():
    assert due(dt.date(2026, 10, 26))["report_overdue"] is True
    d = due(dt.date(2026, 10, 1))
    assert d["report_overdue"] is False and d["report_due"] == "2026-10-21" and d["itr_due"] == "2026-11-21"


# ---------------------------------------------------------------- ledger
LEDGER = """Date,Party,Account head,Narration,Mode,Receipt,Payment,GSTIN
05-04-2025,Ravi Transport,Freight,Lorry hire to Pune,Cash,,32000,
05-04-2025,Office Mart,Office expenses,Stationery,Cash,,6000,27AAPFU0939F1ZV
05-04-2025,Office Mart,Office expenses,Printer ink,Cash,,5500,27AAPFU0939F1ZV
09-04-2025,Anil Mehta,Unsecured loan,Loan received,Cash,50000,,
10-04-2025,Sharma Traders,Sales,Counter sale,Cash,120000,,
10-04-2025,Sharma Traders,Sales,Counter sale,Cash,90000,,
11-04-2025,Bank,Contra,Cash deposited into bank,Cash,,100000,
12-04-2025,Bharat Steel,Purchases,Invoice 118,NEFT,,240000,27AABCB1234C1Z5
15-04-2025,Kiran Exports,Sales,Invoice 22,RTGS,500000,,
20-04-2025,GST Department,Rates and taxes,GST late fee,Net banking,,2000,
30-04-2025,Anil Mehta,Unsecured loan,Loan repaid,Cash,,25000,
,,,Closing balance,,,,
"""


def test_ledger_cash_checks_by_hand():
    lg = read_ledger("cashbook.csv", LEDGER.encode())
    assert lg and lg["mode_source"] == "column" and len(lg["rows"]) == 11 and lg["skipped"] == 1
    out = ledger_checks(lg["rows"], "cashbook.csv")
    assert out["contra_excluded"] == 1  # "Cash deposited into bank" is not a payment
    # cash receipts 1,20,000 + 90,000 + 50,000 = 2,60,000; cash payments 32,000 + 6,000 + 5,500 + 25,000 = 68,500
    assert out["cash_receipts"] == 260_000 and out["cash_payments"] == 68_500
    # totals add the bank rows: receipts 2,60,000 + 5,00,000; payments 68,500 + 2,40,000 + 2,000
    assert out["total_receipts"] == 760_000 and out["total_payments"] == 310_500 and out["totals_complete"]
    # 40A(3): Office Mart 6,000 + 5,500 = 11,500 > 10,000 in one day; freight 32,000 ≤ 35,000 (goods carriage limit)
    assert [(x["party"], x["amount"], x["limit"]) for x in out["s40a3"]] == [("Office Mart", 11_500, 10_000)]
    assert out["s40a3"][0]["working"] == "₹6,000 + ₹5,500 = ₹11,500 in cash on 2025-04-05 > ₹10,000"
    assert out["s40a3"][0]["refs"] == ["Data!A3", "Data!A4"]
    assert [x["amount"] for x in out["s269ss"]] == [50_000]   # loan accepted in cash ≥ 20,000
    assert [x["amount"] for x in out["s269t"]] == [25_000]    # loan repaid in cash ≥ 20,000
    assert [x["amount"] for x in out["s269st"]] == [210_000]  # 1,20,000 + 90,000 from Sharma Traders in a day ≥ 2,00,000
    assert [h["head"] for h in out["c21a"]] == ["Penalty or fine"]  # the GST late fee, for review
    # clause 44: expenses 32,000 + 6,000 + 5,500 + 2,40,000 + 2,000 = 2,85,500; with a GSTIN 2,51,500
    assert out["c44"] == {"total": 285_500, "registered": 251_500, "unregistered": 34_000}


def test_cash_book_without_mode_column_is_all_cash():
    text = "Date,Particulars,Receipt,Payment\n01-05-2025,Rent,,15000\n02-05-2025,Sales,8000,\n"
    lg = read_ledger("Cash Book FY26.csv", text.encode())
    assert lg["mode_source"] == "cash book" and all(r["cash"] for r in lg["rows"])
    out = ledger_checks(lg["rows"], "Cash Book FY26.csv")
    assert out["cash_payments"] == 15_000 and not out["totals_complete"] and out["s40a3"][0]["amount"] == 15_000
    # a bank statement without a mode column: cash is unknown, so nothing is flagged
    lg = read_ledger("bank.csv", text.encode())
    assert ledger_checks(lg["rows"], "bank.csv")["cash_known"] is False


# ---------------------------------------------------------------- API
def upload(client, name: str, data: bytes) -> str:
    r = client.post("/api/uploads", files=[("files", (name, data))])
    res = r.json()["results"][0]
    assert res["ok"], res
    return res["upload"]["id"]


def pl_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Financials"
    for row in [["Sharma & Sons — GSTIN: 27ABCFS1234K1Z5", None, None],
                ["Particulars", "FY2025", "FY2026"],
                ["Revenue from operations", 90_000_000, 120_000_000],
                ["Cost of goods sold", 63_000_000, 86_400_000],
                ["Profit before tax", 4_500_000, 5_400_000],
                ["Inventories", 15_000_000, 18_000_000],
                ["GST payable", 380_000, 420_000],
                ["TDS payable", 60_000, 80_000],
                ["Provision for bonus", 200_000, 250_000]]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def by_no(out):
    return {c["no"]: c for c in out["clauses"]}


def test_api_builds_the_draft_from_books(client):
    pl = upload(client, "accounts.xlsx", pl_workbook())
    cb = upload(client, "cashbook.csv", LEDGER.encode())
    r = client.post("/api/tax/audit", json={"taxpayer_type": "firm", "name": "Sharma & Sons", "pan": "ABCFS1234K",
                                            "upload_ids": [pl, cb]})
    assert r.status_code == 200, r.text
    out = r.json()
    a = out["applicability"]
    # turnover ₹12 crore read from the P&L (> ₹10 crore) → audit under clause (a), Form 3CB for a firm
    assert a["required"] is True and a["clauses"] == ["44AB(a)"] and a["form"] == "3CB"
    assert out["inputs_from_files"][0] == {"field": "business_turnover", "value": 120_000_000, "source": "accounts.xlsx › Financials › C3"}
    c = by_no(out)
    assert c["8"]["answer"] == "Clause (a) of section 44AB"
    assert c["3"]["answer"] == "XXXFX####K"  # masked
    assert c["4"]["answer"] == "Yes — GST: 27XXXFX####K1Z5" and c["4"]["evidence"][0]["where"] == "Financials!A1"
    rows40 = {x["metric"]: x for x in c["40"]["rows"]}
    # GP: (12,00,00,000 − 8,64,00,000) ÷ 12,00,00,000 = 28.00%; last year (9 − 6.3) ÷ 9 = 30.00%
    assert rows40["Gross profit / turnover — This year"]["result"] == "28.00%"
    assert rows40["Gross profit / turnover — Last year"]["result"] == "30.00%"
    # NP: 54,00,000 ÷ 12,00,00,000 = 4.50%; stock 1,80,00,000 ÷ 12,00,00,000 = 15.00%
    assert rows40["Net profit / turnover — This year"]["result"] == "4.50%"
    assert rows40["Stock-in-trade / turnover — This year"]["result"] == "15.00%"
    assert rows40["Net profit / turnover — This year"]["source"] == "accounts.xlsx › Financials › C5"
    # 43B: GST payable and bonus, not TDS
    assert [x["metric"] for x in c["26"]["rows"]] == ["GST payable", "Provision for bonus"]
    assert c["21"]["status"] == "review" and c["21"]["rows"][0]["source"] == "cashbook.csv › Data!A3, Data!A4"
    assert len(c["31"]["rows"]) == 3
    assert c["28"]["status"] == "omitted" and c["36"]["status"] == "not_applicable"
    assert c["34"]["status"] == "needs_input" and c["34"]["needed"]
    # auditor fields are never filled in
    assert out["report_3cb"]["applies"] and "UDIN" in out["report_3cb"]["auditor_fields"]
    text = str(out)
    assert "ABCFS1234K" not in text and "27ABCFS1234K1Z5" not in text
    assert sum(out["counts"].values()) == len(out["clauses"])

    d = client.post("/api/tax/audit/draft.docx", json={"taxpayer_type": "firm", "upload_ids": [pl, cb]})
    assert d.status_code == 200 and d.content[:2] == b"PK"
    assert "wordprocessingml" in d.headers["content-type"]


def test_api_without_files_and_access_control(client):
    out = client.post("/api/tax/audit", json={"activity": "profession", "professional_receipts": 6_000_000}).json()
    assert out["applicability"]["clauses"] == ["44AB(b)"] and by_no(out)["40"]["status"] == "needs_input"
    assert client.post("/api/tax/audit", json={"pan": "BADPAN"}).status_code == 422
    assert client.post("/api/tax/audit", json={"upload_ids": ["0" * 32]}).status_code == 404
    assert client.get("/api/tax/audit/ledger-template").text.startswith("Date,Party")
    uid = upload(client, "cashbook.csv", LEDGER.encode())
    client.post("/api/auth/logout")
    from tests.conftest import register
    register(client, email="other-audit@example.com")
    assert client.post("/api/tax/audit", json={"upload_ids": [uid]}).status_code == 404
