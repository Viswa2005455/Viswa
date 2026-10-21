"""Peer comparison."""

import pytest

from app.finance import FinanceInputError
from app.finance.peers import CompanyIn, compare

P = ["FY24", "FY25"]


def company(name, scale=1.0, **override):
    items = {
        "revenue": [1000 * scale, 1200 * scale], "cogs": [600 * scale, 700 * scale], "operating_income": [150 * scale, 200 * scale],
        "depreciation_amortization": [50 * scale, 60 * scale], "net_income": [100 * scale, 140 * scale],
        "total_assets": [1000 * scale, 1100 * scale], "total_equity": [500 * scale, 580 * scale], "total_debt": [300 * scale, 290 * scale],
        "receivables": [150 * scale, 180 * scale], "interest_expense": [20 * scale, 15 * scale],
        "operating_cash_flow": [90 * scale, 120 * scale], "capex": [-40 * scale, -50 * scale],
    }
    items.update(override)
    return CompanyIn(name, P, {k: v for k, v in items.items() if v is not None})


def row(rep, key):
    return next(r for r in rep.rows if r.key == key)


def test_metrics_match_formulas():
    rep = compare([company("A"), company("B", 2.0)])
    roe = row(rep, "roe")
    assert roe.values[0] == pytest.approx(140 / ((500 + 580) / 2))
    assert row(rep, "revenue_growth").values[0] == pytest.approx(0.2)
    assert row(rep, "receivable_days").values[0] == pytest.approx((150 + 180) / 2 / 1200 * 365)
    assert row(rep, "debt_equity").values[0] == pytest.approx(290 / 580)
    assert row(rep, "fcf_margin").values[0] == pytest.approx((120 - 50) / 1200)
    # identical ratios at double the size: tie on ratios, revenue is not ranked (neutral)
    assert roe.ranks == [1, 1]
    assert row(rep, "revenue").ranks == [None, None]


def test_ranking_direction_and_missing_is_not_zero():
    a = company("A")
    b = company("B", total_debt=[100, 50])          # less debt -> better D/E
    c = company("C", receivables=None)              # no receivables -> DSO missing, not ranked
    rep = compare([a, b, c])
    de = row(rep, "debt_equity")
    assert de.ranks[1] == 1 and de.ranks[0] == 2
    dso = row(rep, "receivable_days")
    assert dso.values[2] is None and dso.ranks[2] is None
    assert any("different numbers of metrics" in w for w in rep.warnings)


def test_valuation_needs_market_data_and_is_labelled():
    a = company("A", share_price=[10, 20], shares_outstanding=[100, 100])
    b = company("B", share_price=[10, 30], shares_outstanding=[100, 100])
    rep = compare([a, b])
    pe = row(rep, "pe")
    assert pe.values == [pytest.approx(2000 / 140), pytest.approx(3000 / 140)]
    assert pe.ranks == [1, 2] and any("not a buy or sell signal" in n for n in pe.notes)
    assert all(r.key != "ev_ebitda" or r.values[0] is None for r in rep.rows)  # no cash line -> no EV


def test_validation_and_period_warning():
    with pytest.raises(FinanceInputError):
        compare([company("A")])
    with pytest.raises(FinanceInputError):
        compare([company("A"), company("a")])
    other = CompanyIn("B", ["FY23", "FY24"], company("B").items)
    assert any("Latest periods differ" in w for w in compare([company("A"), other]).warnings)


def test_peers_endpoint(client):
    body = {"companies": [{"name": c.name, "periods": c.periods, "items": c.items} for c in (company("TCS"), company("Infosys", 0.7))]}
    r = client.post("/api/analysis/peers", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["companies"] == ["TCS", "Infosys"]
    assert client.post("/api/analysis/peers", json={"companies": body["companies"][:1]}).status_code == 422
