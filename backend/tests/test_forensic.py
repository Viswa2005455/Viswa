"""Red-flag screens: known-answer checks against the published formulas."""

import pytest

from app.finance import FinanceInputError
from app.finance.forensic import analyse

PERIODS = ["FY24", "FY25"]


def base_items(**override):
    items = {
        "revenue": [1000, 1200], "cogs": [600, 750], "receivables": [100, 180], "current_assets": [400, 500],
        "ppe": [500, 520], "total_assets": [1000, 1150], "depreciation_amortization": [50, 50], "sga": [100, 130],
        "current_liabilities": [200, 250], "long_term_debt": [200, 220], "net_income": [100, 130],
        "operating_cash_flow": [120, 90], "retained_earnings": [300, 380], "operating_income": [150, 190],
        "total_equity": [600, 680], "inventory": [80, 90], "shares_outstanding": [100, 100],
    }
    items.update(override)
    return {k: v for k, v in items.items() if v is not None}


def test_beneish_eight_variable_matches_formula():
    r = analyse(PERIODS, base_items()).beneish
    dsri = (180 / 1200) / (100 / 1000)
    gmi = (400 / 1000) / (450 / 1200)
    aqi = (1 - 1020 / 1150) / (1 - 900 / 1000)
    sgi = 1.2
    depi = (50 / 550) / (50 / 570)
    sgai = (130 / 1200) / (100 / 1000)
    lvgi = (470 / 1150) / (400 / 1000)
    tata = (130 - 90) / 1150
    m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai
         + 4.679 * tata - 0.327 * lvgi)
    assert r.status == "ok" and r.model.startswith("8-variable")
    assert r.value == pytest.approx(m)
    assert r.verdict == "flag"  # about -1.61, above -1.78
    comps = {c.key: c.value for c in r.components}
    assert comps["DSRI"] == pytest.approx(1.5) and comps["TATA"] == pytest.approx(tata)


def test_beneish_falls_back_to_five_variable_model_without_sga():
    r = analyse(PERIODS, base_items(sga=None)).beneish
    assert r.status == "ok" and r.model.startswith("5-variable")
    assert any("5-variable" in n for n in r.notes)
    assert "SG&A (t)" in r.missing


def test_beneish_missing_inputs_are_not_zero():
    r = analyse(PERIODS, base_items(receivables=None)).beneish
    assert r.status == "missing" and r.value is None
    dsri = next(c for c in r.components if c.key == "DSRI")
    assert dsri.value is None and "Receivables (t)" in dsri.missing


def test_altman_z_double_prime_and_original_needs_market_data():
    z2, z = analyse(PERIODS, base_items()).altman
    x1, x2, x3, x4 = (500 - 250) / 1150, 380 / 1150, 190 / 1150, 680 / (1150 - 680)
    assert z2.status == "ok"
    assert z2.value == pytest.approx(6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4)
    assert z2.verdict == "safe"
    assert z.status == "missing" and "Market capitalisation" in z.missing
    _, z = analyse(PERIODS, base_items(share_price=[20, 25])).altman
    x4m = 25 * 100 / 470
    assert z.status == "ok"
    assert z.value == pytest.approx(1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4m + 1.0 * 1200 / 1150)


def test_derived_totals_are_labelled():
    items = base_items(total_equity=None, share_capital=[100, 100])
    rep = analyse(PERIODS, items)
    assert any("Total equity = share capital + reserves" in n for n in rep.derived)
    assert any("Total liabilities = total assets" in n for n in rep.derived)


def test_piotroski_scores_and_reports_untested():
    p = analyse(PERIODS, base_items()).piotroski
    results = {c.name: c.result for c in p.criteria}
    assert results["Profitable"] == "pass"
    assert results["Earnings backed by cash"] == "fail"  # CFO 90 < NI 130
    assert results["No new shares issued"] == "pass"
    assert p.tested == 9 and p.score == sum(r == "pass" for r in results.values())
    assert any("year-end total assets" in n for n in p.notes)
    p2 = analyse(PERIODS, base_items(shares_outstanding=None)).piotroski
    assert p2.tested == 8 and "could not be tested" in p2.verdict_text


def test_piotroski_uses_beginning_assets_with_three_periods():
    items = {k: [v[0]] + v for k, v in base_items().items()}
    p = analyse(["FY23", "FY24", "FY25"], items).piotroski
    assert p.notes == []


def test_cash_quality_flags():
    flags = analyse(PERIODS, base_items()).flags
    titles = [f.title for f in flags]
    assert "Receivables growing faster than sales" in titles  # +80% vs +20%
    assert "Profits are not turning into cash" not in titles  # 210 / 230 = 91%
    flags = analyse(PERIODS, base_items(operating_cash_flow=[50, -10], other_income=[5, 60], pretax_income=[120, 150],
                                        interest_expense=[10, 150])).flags
    titles = [f.title for f in flags]
    assert {"Profits are not turning into cash", "Profit with negative operating cash flow",
            "Large share of profit from other income", "Low interest cover"} <= set(titles)
    assert flags[0].severity == "high"


def test_validation():
    with pytest.raises(FinanceInputError):
        analyse(["FY25"], {"revenue": [1]})
    with pytest.raises(FinanceInputError):
        analyse(PERIODS, {"made_up": [1, 2]})
    with pytest.raises(FinanceInputError):
        analyse(PERIODS, {"revenue": [1]})


def test_accepts_every_statement_item():
    from app.finance.statements import STANDARD_ITEMS

    items = {k: [1.0, 2.0] for k in STANDARD_ITEMS}
    assert analyse(PERIODS, items).beneish is not None


def test_forensic_endpoint(client):
    r = client.post("/api/analysis/forensic", json={"periods": PERIODS, "items": base_items()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["beneish"]["status"] == "ok" and len(body["altman"]) == 2
    assert client.post("/api/analysis/forensic", json={"periods": ["FY25"], "items": {}}).status_code == 422


def test_forensic_requires_sign_in(anon_client):
    assert anon_client.post("/api/analysis/forensic", json={"periods": PERIODS, "items": {}}).status_code == 401


def test_beneish_undefined_component_is_explained():
    # prior year: current assets + PPE = total assets, so AQI's denominator is zero
    r = analyse(PERIODS, base_items(current_assets=[500, 500])).beneish
    assert r.status == "missing" and "AQI" in r.verdict_text and "denominator is zero" in r.verdict_text
