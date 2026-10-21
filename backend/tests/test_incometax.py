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
    assert due_dates("no_business", dt.date(2026, 8, 5), total_income=400_000)["late_filing"]["fee_234f"] == 1_000
    assert due_dates("audit", dt.date(2027, 1, 5), total_income=1)["late_filing"]["allowed"] is False
