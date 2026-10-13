from pathlib import Path

import pytest

from src.rule_engine.zen_engine import ZenTaxRuleEngine


MODEL = Path(__file__).parents[1] / "config" / "zen" / "LUAT67_ARTICLE9_v1.json"


def complete_checks(**overrides):
    checks = {
        "input_complete": True,
        "is_business_related": True,
        "has_legal_invoice_documents": True,
        "is_administrative_penalty": False,
        "is_reimbursed_from_other_source": False,
        "provision_compliant": True,
        "depreciation_compliant": True,
        "accrual_compliant": True,
        "is_disallowed_owner_salary": False,
        "is_founder_remuneration": False,
        "founder_directly_manages": True,
        "employee_expense_unpaid": False,
        "employee_expense_has_documents": True,
        "interest_for_missing_charter_capital": False,
        "interest_already_capitalized": False,
        "non_credit_interest_exceeds_civil_code_limit": False,
        "vat_input_already_deducted": False,
        "is_corporate_income_tax": False,
        "corresponds_to_taxable_revenue": True,
        "article9_1b_exception": False,
        "is_sponsorship": False,
        "sponsorship_allowed_under_1_b5": False,
        "is_capex_creating_fixed_asset": False,
        "is_direct_equity_reduction_cost": False,
        "requires_government_detail": False,
    }
    checks.update(overrides)
    return {"checks": checks}


def test_clean_transaction_passes():
    result = ZenTaxRuleEngine(MODEL).evaluate(complete_checks(), "2025-10-01")
    assert result["verdict"] == "PASS"
    assert result["hits"] == []


def test_multiple_violations_are_collected_and_fail():
    context = complete_checks(
        is_business_related=False,
        is_administrative_penalty=True,
    )
    result = ZenTaxRuleEngine(MODEL).evaluate(context, "2026-01-15")
    assert result["verdict"] == "FAIL"
    assert {hit["rule_id"] for hit in result["hits"]} == {
        "CIT67-A9-1A",
        "CIT67-A9-2B",
    }


def test_incomplete_input_is_review():
    engine = ZenTaxRuleEngine(MODEL)
    result = engine.evaluate(
        complete_checks(input_complete=False), "2026-01-15"
    )
    assert result["verdict"] == "REVIEW"
    assert result["hits"][0]["reason_code"] == "MISSING_REQUIRED_FACTS"


def test_rule_set_is_not_used_before_effective_date():
    result = ZenTaxRuleEngine(MODEL).evaluate(complete_checks(), "2025-09-30")
    assert result["verdict"] == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    ("overrides", "expected_rule"),
    [
        ({"has_legal_invoice_documents": False}, "CIT67-A9-1C"),
        ({"is_reimbursed_from_other_source": True}, "CIT67-A9-2C"),
        ({"provision_compliant": False}, "CIT67-A9-2E"),
        ({"depreciation_compliant": False}, "CIT67-A9-2F"),
        ({"accrual_compliant": False}, "CIT67-A9-2G"),
        ({"is_disallowed_owner_salary": True}, "CIT67-A9-2H-OWNER"),
        (
            {"is_founder_remuneration": True, "founder_directly_manages": False},
            "CIT67-A9-2H-FOUNDER",
        ),
        ({"employee_expense_unpaid": True}, "CIT67-A9-2H-UNPAID"),
        ({"employee_expense_has_documents": False}, "CIT67-A9-2H-NODOC"),
        ({"interest_for_missing_charter_capital": True}, "CIT67-A9-2I-CAPITAL"),
        ({"interest_already_capitalized": True}, "CIT67-A9-2I-CAPITALIZED"),
        (
            {"non_credit_interest_exceeds_civil_code_limit": True},
            "CIT67-A9-2I-NONCREDIT",
        ),
        ({"vat_input_already_deducted": True}, "CIT67-A9-2L-VAT"),
        ({"is_corporate_income_tax": True}, "CIT67-A9-2L-CIT"),
        (
            {"corresponds_to_taxable_revenue": False, "article9_1b_exception": False},
            "CIT67-A9-2M",
        ),
        (
            {"is_sponsorship": True, "sponsorship_allowed_under_1_b5": False},
            "CIT67-A9-2N",
        ),
        ({"is_capex_creating_fixed_asset": True}, "CIT67-A9-2O-CAPEX"),
        ({"is_direct_equity_reduction_cost": True}, "CIT67-A9-2O-EQUITY"),
    ],
)
def test_each_article9_failure_rule(overrides, expected_rule):
    result = ZenTaxRuleEngine(MODEL).evaluate(
        complete_checks(**overrides), "2026-01-15"
    )
    assert result["verdict"] == "FAIL"
    assert expected_rule in {hit["rule_id"] for hit in result["hits"]}


def test_government_detail_is_review():
    result = ZenTaxRuleEngine(MODEL).evaluate(
        complete_checks(requires_government_detail=True), "2026-01-15"
    )
    assert result["verdict"] == "REVIEW"
    assert result["hits"][0]["rule_id"] == "CIT67-A9-DETAIL"
