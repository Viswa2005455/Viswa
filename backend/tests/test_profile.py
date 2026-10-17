"""Company profile (dashboard metrics) built from an imported Screener company."""

import pytest

from app.files.screener import parse_screener
from app.finance.profile import build

from .screener_fixture import screener_bytes


def company():
    r = parse_screener(screener_bytes())
    items = {l["key"]: l["values"] for l in r["lines"] if l["key"]}
    items.update(r["market"])
    return r["periods"], items


def test_profile_metrics_match_formulas():
    periods, items = company()
    p = build(periods, items)
    s = p.series
    assert s["revenue_growth"][-1] == pytest.approx(255324 / 240893 - 1)
    eq = lambda i: items["share_capital"][i] + items["retained_earnings"][i]  # noqa: E731
    assert s["roe"][-1] == pytest.approx(48553 / ((eq(3) + eq(4)) / 2))
    assert s["market_cap"][-1] == pytest.approx(3600 * 361.8)
    assert s["pe"][-1] == pytest.approx(3600 * 361.8 / 48553)
    assert s["eps"][-1] == pytest.approx(48553 / 361.8)
    assert s["payout_ratio"][-1] == pytest.approx(45000 / 48553)
    assert s["roe"][0] is None and s["revenue_growth"][0] is None  # first year has no prior
    assert s["free_cash_flow"] == [None] * 5  # Screener has no CapEx line: missing, not zero
    assert p.cagr["revenue_3y"]["value"] == pytest.approx((255324 / 191754) ** (1 / 3) - 1)
    assert p.scores["altman_z2"]["value"] is None  # needs current assets/liabilities
    assert any("ROE" in h for h in p.highlights)


def test_profile_endpoint(client):
    periods, items = company()
    r = client.post("/api/analysis/profile", json={"periods": periods, "items": items})
    assert r.status_code == 200, r.text
    assert r.json()["metrics"]["roe"]["unit"] == "%"
