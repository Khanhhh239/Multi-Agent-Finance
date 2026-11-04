import os
import pytest
from hypothesis import given, strategies as st
from src.rule_engine.rules_loader import RulesLoader
from src.rule_engine.engine import RuleEngine

# Direct path to the rules folder
RULES_DIR = "d:/financial/agent3_tax_compliance/config/rules"

@pytest.fixture
def engine():
    loader = RulesLoader(rules_dir=RULES_DIR)
    return RuleEngine(loader)

def test_load_rules(engine):
    active_rules = engine.rules_loader.load_rules("2026-07-19")
    assert len(active_rules) == 12

def test_rcash_20m_trigger(engine):
    # Over 20M and paid by cash -> FAIL
    txn = {
        "amount": 25000000,
        "payment_method": "cash",
        "entry_type": "expense"
    }
    result = engine.evaluate(txn, "2026-07-19")
    assert result["verdict"] == "FAIL"
    rule_ids = [hit["rule_id"] for hit in result["hits"]]
    assert "R-CASH-20M" in rule_ids

def test_rcash_20m_not_trigger(engine):
    # Under 20M paid by cash -> PASS
    txn1 = {
        "amount": 15000000,
        "payment_method": "cash",
        "entry_type": "expense"
    }
    result1 = engine.evaluate(txn1, "2026-07-19")
    assert "R-CASH-20M" not in [hit["rule_id"] for hit in result1["hits"]]

    # Over 20M paid by bank transfer -> PASS
    txn2 = {
        "amount": 25000000,
        "payment_method": "bank_transfer",
        "entry_type": "expense"
    }
    result2 = engine.evaluate(txn2, "2026-07-19")
    assert "R-CASH-20M" not in [hit["rule_id"] for hit in result2["hits"]]

def test_rwelfare_cap_trigger(engine):
    txn = {
        "category": "welfare",
        "welfare_ytd_spent_with_current": 120000000,
        "avg_monthly_salary": 100000000
    }
    result = engine.evaluate(txn, "2026-07-19")
    assert result["verdict"] == "FAIL"
    assert any(hit["rule_id"] == "R-WELFARE-CAP" for hit in result["hits"])

def test_rcar_16b_trigger(engine):
    txn = {
        "asset_type": "car_under_9_seats",
        "original_cost": 1800000000
    }
    result = engine.evaluate(txn, "2026-07-19")
    assert result["verdict"] == "FAIL"
    assert any(hit["rule_id"] == "R-CAR-1.6B" for hit in result["hits"])

def test_rvendor_risk_trigger(engine):
    txn = {
        "vendor_in_high_risk_list": True
    }
    result = engine.evaluate(txn, "2026-07-19")
    assert result["verdict"] == "REVIEW"
    assert any(hit["rule_id"] == "R-VENDOR-RISK" for hit in result["hits"])

# Property-based test using Hypothesis to ensure the engine is crash-free
@given(
    amount=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
    payment_method=st.sampled_from(["cash", "bank_transfer", "credit_card", "other"]),
    category=st.sampled_from(["welfare", "commission", "outsourced_service", "office_supplies", "other"]),
    original_cost=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
    vendor_in_high_risk_list=st.booleans(),
    welfare_ytd_spent_with_current=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
    avg_monthly_salary=st.floats(min_value=1, max_value=1e10, allow_nan=False, allow_infinity=False)
)
def test_engine_robustness(amount, payment_method, category, original_cost, vendor_in_high_risk_list, welfare_ytd_spent_with_current, avg_monthly_salary):
    loader = RulesLoader(rules_dir=RULES_DIR)
    engine = RuleEngine(loader)
    txn = {
        "amount": amount,
        "payment_method": payment_method,
        "category": category,
        "original_cost": original_cost,
        "vendor_in_high_risk_list": vendor_in_high_risk_list,
        "welfare_ytd_spent_with_current": welfare_ytd_spent_with_current,
        "avg_monthly_salary": avg_monthly_salary,
        "entry_type": "expense",
        "asset_type": "car_under_9_seats" if original_cost > 0 else "other"
    }
    # Verify execution completes without throwing exceptions
    result = engine.evaluate(txn, "2026-07-19")
    assert "verdict" in result
    assert result["verdict"] in ["FAIL", "REVIEW", "PASS"]
