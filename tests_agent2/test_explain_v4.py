from agent2.explain_check import check
from agent2.explain_v4 import V4_REASONS, observations, rule_observations, entity_observations
import json
from agent2.feats_v4 import V4_FEATURES


def test_every_existing_feature_has_a_supported_template():
    assert set(V4_REASONS) == set(V4_FEATURES)
    row = {name: 2 for name in V4_FEATURES}
    explanations = observations(row)
    assert len(explanations) == 15
    assert all(check(x["text"], x["evidence"])["ok"] for x in explanations)


def test_modified_number_fails_and_percent_rounding_is_supported():
    reason = observations({"self_approved_advance_ratio": .253})[0]
    assert "25%" in reason["text"]
    assert check(reason["text"], reason["evidence"])["ok"]
    assert not check(reason["text"].replace("25%", "97%"), reason["evidence"])["ok"]


def test_days_until_due_are_not_called_overdue():
    reason = observations({"writeoff_overdue_days": -12})[0]
    assert "còn 12 ngày" in reason["text"]
    assert check(reason["text"], reason["evidence"])["ok"]


def test_zero_and_missing_evidence_do_not_generate_claims():
    assert observations({}) == []
    assert observations({"payee_not_on_master": 0, "receipt_days_late": float("nan")}) == []


def test_fallback_ratios_are_not_reported_as_observed_percentages():
    reason = observations({"return_vs_recent_sales": 10})[0]
    assert "%" not in reason["text"]


def test_rule_counts_and_windows_use_the_rule_evidence():
    evidence = {"A1": {"count": 4, "window_days": 7, "total_vnd": 1000, "approval_limit_vnd": 800}}
    reason = rule_observations({"rule_ids": "A1", "rule_evidence_json": json.dumps(evidence)})[0]
    assert "4 khoản" in reason["text"] and "7 ngày" in reason["text"]
    assert check(reason["text"], reason["evidence"])["ok"]


def test_baseline_percent_is_derived_from_measured_log_ratio():
    reason = entity_observations({"price_logratio": .6931471805599453}, {"price_logratio": 5})[0]
    assert "100%" in reason["text"]
    assert check(reason["text"], reason["evidence"])["ok"]
