"""Income tax AY 2026-27: known answers worked by hand from the slab tables and sections cited in the module."""

import datetime as dt

import pytest

from app.finance import FinanceInputError
from app.finance.incometax import EntityIncome, IndividualIncome, TaxpayerProfile, due_dates, entity_tax, individual_tax, select_itr


def test_new_regime_rebate_and_marginal_relief():
    # 12,75,000 salary - 75,000 standard deduction = 12,00,000: tax 60,000 fully rebated
    r = individual_tax(IndividualIncome(salary=1_275_000))
    assert r["new"]["total_income"] == 1_200_000 and r["new"]["slab_tax"] == 60_000 and r["new"]["total_tax"] == 0
    # 13,00,000 salary -> 12,25,000: slab tax 63,750, limited to the 25,000 above 12 lakh, plus 4% cess
    r = individual_tax(IndividualIncome(salary=1_300_000))
    assert r["new"]["slab_tax"] == 63_750 and r["new"]["rebate_87a"] == 38_750 and r["new"]["total_tax"] == 26_000


def test_old_regime_deduction_caps():
    r = individual_tax(IndividualIncome(salary=1_000_000, deductions_old={"80C": 200_000}))
    old = r["old"]
    assert old["deductions"]["80C"] == 150_000 and old["slab_income"] == 800_000
    assert old["slab_tax"] == 72_500 and old["total_tax"] == 75_400
    assert any("80C is limited" in n for n in old["notes"])
    assert r["new"]["total_tax"] == 0 and r["better_regime"] == "new"


def test_senior_exemption_and_old_rebate():
    r = individual_tax(IndividualIncome(age="80_plus", other_sources=900_000))
    assert r["old"]["slab_tax"] == 80_000  # nil to 5L, 20% on 4L
    r = individual_tax(IndividualIncome(other_sources=500_000))
    assert r["old"]["slab_tax"] == 12_500 and r["old"]["rebate_87a"] == 12_500 and r["old"]["total_tax"] == 0


def test_special_rate_gains_use_unexhausted_exemption_and_get_no_new_rebate():
    r = individual_tax(IndividualIncome(other_sources=200_000, stcg_111a=500_000))
    new = r["new"]
    assert new["special_rate_tax"]["111A"]["exemption_used"] == 200_000
    assert new["special_rate_tax"]["111A"]["tax"] == 60_000 and new["rebate_87a"] == 0 and new["total_tax"] == 62_400
    # 112A: first 1.25 lakh exempt, 12.5% above
    r = individual_tax(IndividualIncome(salary=2_000_000, ltcg_112a=325_000))
    assert r["new"]["special_rate_tax"]["112A"]["tax"] == pytest.approx(25_000)
    # non-residents cannot use the unexhausted exemption
    r = individual_tax(IndividualIncome(resident=False, stcg_111a=300_000))
    assert r["new"]["special_rate_tax"]["111A"]["tax"] == 60_000


def test_rebate_threshold_reading_is_switchable():
    inc = dict(other_sources=1_000_000, ltcg_112a=400_000)
    counted = individual_tax(IndividualIncome(**inc))["new"]
    excluded = individual_tax(IndividualIncome(**inc, count_special_income_for_rebate=False))["new"]
    assert counted["rebate_87a"] == 0 and excluded["rebate_87a"] == 40_000  # slab tax on 10L is 40,000


def test_surcharge_marginal_relief_new_regime():
    r = individual_tax(IndividualIncome(business=5_010_000))["new"]
    assert r["slab_tax"] == 1_083_000 and r["surcharge_rate"] == 0.10
    assert r["surcharge"] == pytest.approx(7_000) and r["marginal_relief"] == pytest.approx(101_300)
    assert r["total_tax"] == 1_133_600


def test_house_property_loss_rules():
    r = individual_tax(IndividualIncome(salary=1_500_000, house_property=-300_000))
    assert r["old"]["gross_slab_income"] == 1_500_000 - 50_000 - 200_000
    assert r["new"]["gross_slab_income"] == 1_500_000 - 75_000


def test_new_regime_capped_surcharge_and_inputs():
    r = individual_tax(IndividualIncome(business=60_000_000))
    assert r["new"]["surcharge_rate"] == 0.25 and r["old"]["surcharge_rate"] == 0.37
    with pytest.raises(FinanceInputError):
        individual_tax(IndividualIncome(salary=-1))
    with pytest.raises(FinanceInputError):
        individual_tax(IndividualIncome(taxpayer_type="company"))


def test_itr_selection():
    assert select_itr(TaxpayerProfile(total_income=900_000, salary_or_pension=True, house_properties=2))["form"] == "ITR-1"
    r = select_itr(TaxpayerProfile(total_income=900_000, salary_or_pension=True, stcg=True))
    assert r["form"] == "ITR-2" and "short-term" in r["simpler_forms_excluded"][0]["why"][0]
    assert select_itr(TaxpayerProfile(total_income=6_000_000, salary_or_pension=True))["form"] == "ITR-2"
    assert select_itr(TaxpayerProfile(total_income=900_000, business_income=True, presumptive="44ADA"))["form"] == "ITR-4"
    r = select_itr(TaxpayerProfile(total_income=900_000, business_income=True, presumptive="44ADA", director=True))
    assert r["form"] == "ITR-3" and r["due_date_category"] == "business_no_audit"
    assert select_itr(TaxpayerProfile(taxpayer_type="huf", total_income=900_000, business_income=True, presumptive="44ADA"))["form"] == "ITR-3"
    assert select_itr(TaxpayerProfile(total_income=900_000, partner_remuneration=True))["form"] == "ITR-3"
    assert select_itr(TaxpayerProfile(taxpayer_type="firm", total_income=900_000, business_income=True, presumptive="44AD"))["form"] == "ITR-4"
    assert select_itr(TaxpayerProfile(taxpayer_type="llp", total_income=900_000, business_income=True, presumptive="44AD"))["form"] == "ITR-5"
    assert select_itr(TaxpayerProfile(taxpayer_type="company", total_income=1))["form"] == "ITR-6"
    assert select_itr(TaxpayerProfile(taxpayer_type="company", claims_section_11=True))["form"] == "ITR-7"
    assert select_itr(TaxpayerProfile(taxpayer_type="huf", total_income=500_000))["form"] == "ITR-2"
    assert select_itr(TaxpayerProfile(residential_status="non_resident", total_income=500_000))["form"] == "ITR-2"


def test_entity_tax():
    r = entity_tax(EntityIncome(entity="company", total_income=100_000_000, turnover_fy_2023_24=3_000_000_000))
    normal, baa = r["options"][0], r["options"][1]
    assert normal["tax"] == 25_000_000 and normal["surcharge_rate"] == 0.07 and normal["total_tax"] == 27_820_000
    assert baa["total_tax"] == 25_168_000 and r["lowest"] == "115BAA"
    firm = entity_tax(EntityIncome(entity="firm", total_income=10_100_000))["options"][0]
    assert firm["marginal_relief"] == pytest.approx(293_600) and firm["surcharge"] == pytest.approx(70_000)
    mat = entity_tax(EntityIncome(entity="company", total_income=1_000_000, turnover_fy_2023_24=1, book_profit=10_000_000))["options"][0]
    assert "MAT" in mat["label"] and mat["mat_credit"] > 0
    with pytest.raises(FinanceInputError):
        entity_tax(EntityIncome(entity="company", total_income=1))


def test_due_dates_fee_and_interest():
    r = due_dates("no_business", dt.date(2026, 9, 1), total_income=900_000, tax_unpaid=10_000)
    late = r["late_filing"]
    assert late["late"] and late["fee_234f"] == 5_000 and late["interest_months"] == 2 and late["interest_234a"] == 200
    assert due_dates("no_business", dt.date(2026, 7, 31), total_income=900_000)["late_filing"]["late"] is False
    # 234F applies only above the basic exemption of the taxpayer's regime and age
    assert due_dates("no_business", dt.date(2026, 8, 5), total_income=400_000)["late_filing"]["fee_234f"] == 0
    assert due_dates("no_business", dt.date(2026, 8, 5), total_income=450_000)["late_filing"]["fee_234f"] == 1_000
    assert due_dates("no_business", dt.date(2026, 8, 5), total_income=300_000, regime="old")["late_filing"]["fee_234f"] == 1_000
    assert due_dates("no_business", dt.date(2026, 8, 5), total_income=450_000, regime="old", age="80_plus")["late_filing"]["fee_234f"] == 0
    # Rule 119A: 234A interest on unpaid tax rounded down to a multiple of 100
    assert due_dates("no_business", dt.date(2026, 8, 20), total_income=900_000, tax_unpaid=10_050)["late_filing"]["interest_234a"] == 100
    assert due_dates("audit", dt.date(2027, 1, 5), total_income=1)["late_filing"]["allowed"] is False



# Independent hand computations (tax audit, 22 Oct 2026). Income is entered as "other sources" so no
# standard deduction applies; expected values are worked from the slab tables, surcharge rules and 4% cess.
@pytest.mark.parametrize("regime,income,expected", [
    ("new", 2_400_000, 312_000),        # 20k + 40k + 60k + 80k + 1L = 3,00,000 x 1.04
    ("new", 5_000_000, 1_123_200),      # 10,80,000 x 1.04
    ("new", 5_000_010, 1_123_210),      # surcharge marginal relief at 50 lakh
    ("new", 10_000_010, 2_951_530),     # marginal relief at 1 crore (10% -> 15%)
    ("new", 20_000_010, 6_673_690),     # marginal relief at 2 crore (15% -> 25%)
    ("new", 50_000_010, 18_954_000),    # 25% cap in the new regime
    ("new", 60_000_000, 22_854_000),
    ("old", 50_000_010, 19_256_260),    # marginal relief at 5 crore (25% -> 37%)
    ("old", 60_000_000, 25_379_250),
    ("new", 2_400_015, 312_010),        # s.288A: total income 24,00,020 -> slab tax 3,00,006 -> 3,12,006.24 -> 3,12,010
])
def test_known_answers(regime, income, expected):
    assert individual_tax(IndividualIncome(other_sources=income))[regime]["total_tax"] == expected


def test_senior_and_non_resident_old_regime():
    assert individual_tax(IndividualIncome(age="60_to_79", other_sources=1_000_000))["old"]["total_tax"] == 114_400
    assert individual_tax(IndividualIncome(age="80_plus", other_sources=1_000_000))["old"]["total_tax"] == 104_000
    assert individual_tax(IndividualIncome(age="60_to_79", resident=False, other_sources=500_000))["old"]["total_tax"] == 13_000


def test_enhanced_surcharge_excludes_capital_gains_and_dividends():
    # slab 1.5 cr + 111A 1 cr: income excluding gains is below 2 cr, so 15% (not 25%) applies
    r = individual_tax(IndividualIncome(other_sources=15_000_000, stcg_111a=10_000_000))
    assert r["old"]["surcharge_rate"] == 0.15 and r["old"]["total_tax"] == 7_549_750   # (43,12,500 + 20,00,000) x 1.15 x 1.04
    assert r["new"]["total_tax"] == 7_271_680                                          # (40,80,000 + 20,00,000) x 1.15 x 1.04
    # slab 3 cr + 112 gains 3 cr: 25% on slab tax, 15% cap on the gains (old regime)
    r = individual_tax(IndividualIncome(other_sources=30_000_000, ltcg_112=30_000_000))
    assert r["old"]["surcharge_rate"] == 0.25 and r["old"]["total_tax"] == 15_941_250
    # dividends of 3 cr alone: 15%, not 25%
    r = individual_tax(IndividualIncome(dividends=30_000_000))
    assert r["old"]["surcharge_rate"] == 0.15 and r["old"]["total_tax"] == 10_539_750    # (1,12,500 + 30% x 2.9 cr = 88,12,500) x 1.15 x 1.04


def test_deduction_caps_80cce_80ccd2_80tta():
    r = individual_tax(IndividualIncome(salary=2_000_000, other_sources=4_000, deductions_old={"80C": 150_000, "80CCC": 100_000, "80TTA": 10_000}))
    d = r["old"]["deductions"]
    assert d["80C"] + d.get("80CCC", 0) == 150_000 and d["80TTA"] == 4_000
    r = individual_tax(IndividualIncome(salary=1_200_000, employer_nps_80ccd2=1_000_000))
    assert r["new"]["deductions"]["80CCD(2)"] == pytest.approx(168_000) and r["old"]["deductions"]["80CCD(2)"] == pytest.approx(120_000)


def test_entity_rounding_amt_surcharge_and_audit_due_date():
    r = entity_tax(EntityIncome(entity="cooperative", total_income=1, adjusted_total_income_amt=50_000_000))
    assert r["options"][0]["amt"]["total"] == 8_346_000      # 75,00,000 x 1.07 x 1.04
    assert entity_tax(EntityIncome(entity="firm", total_income=1_000_004))["total_income"] == 1_000_000
    p = TaxpayerProfile(total_income=50_000_000, business_income=True, accounts_audited=True)
    assert select_itr(p)["due_date_category"] == "audit"
    assert "ruleset" in select_itr(p) and individual_tax(IndividualIncome())["ruleset"]["id"] == "IN-ITA1961-AY2026-27"


def test_other_assessment_years_are_refused(client):
    assert client.post("/api/tax/individual", json={"salary": 1, "assessment_year": "2025-26"}).status_code == 422
