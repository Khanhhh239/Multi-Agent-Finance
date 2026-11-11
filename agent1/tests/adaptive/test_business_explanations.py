"""Evidence must agree with serving inputs, not merely sound plausible."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.business_explanations import HistoryEvidence, review_factors
from agent1.adaptive.methods import features


@pytest.fixture
def history():
    rows = []
    for i in range(24):
        due = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append(
            {
                "invoice_id": f"P{i}",
                "customer_id": "C1",
                "amount": 100_000,
                "issue_date": due - pd.Timedelta(days=30),
                "due_date": due,
                "settled": due + pd.Timedelta(days=24 if i < 20 else 0),
                "known_at": due - pd.Timedelta(days=30),
                "settled_known_at": due + pd.Timedelta(days=24 if i < 20 else 0),
            }
        )
    # Paid before issuance, but posted afterwards: cannot support a reason.
    rows.append(
        dict(
            rows[0],
            invoice_id="LATE_POSTED",
            settled_known_at=pd.Timestamp("2025-04-01"),
        )
    )
    # Same-day settlement is not an issuance-time observation.
    rows.append(
        dict(rows[0], invoice_id="SAME_DAY", settled=pd.Timestamp("2025-03-01"))
    )
    return pd.DataFrame(rows)


def target():
    return pd.DataFrame(
        [
            {
                "invoice_id": "OPEN",
                "customer_id": "C1",
                "amount": 72_000_000,
                "issue_date": pd.Timestamp("2025-03-01"),
                "due_date": pd.Timestamp("2025-04-15"),
            }
        ]
    )


def factor(key="customer_delay_days", value=24, effect=-4):
    return {
        "feature": key,
        "value": value,
        "value_unit": "ngày",
        "contribution_pp": effect,
        "direction": "decrease" if effect < 0 else "increase",
        "stability": {
            "status": "stable",
            "reasons": [],
            "min_contribution_pp": effect - 0.1,
            "max_contribution_pp": effect + 0.1,
        },
    }


def test_history_evidence_excludes_late_posting_and_same_day_and_matches_actual_inputs(
    history,
):
    invoice = target()
    prepared = features(invoice, history)[0]
    evidence = HistoryEvidence(history).for_invoice(invoice.iloc[0], prepared)
    customer = evidence["customer_delay_days"]
    assert customer["count"] == 24
    assert customer["late_count"] == 20
    assert customer["on_time_count"] == 4
    assert customer["early_count"] == 0
    assert customer["prepared_median_days"] == 24
    assert prepared[2] == 24
    assert np.expm1(prepared[4]) == pytest.approx(24)
    assert HistoryEvidence(history).for_invoice(invoice.iloc[0], prepared + 1) is None


def test_evidence_and_direction_are_independent_no_invented_payment_quality(history):
    invoice = target().iloc[0]
    evidence = HistoryEvidence(history).for_invoice(
        invoice, features(target(), history)[0]
    )
    for effect in (-4, 4):
        f = factor(effect=effect)
        review_factors(
            [f], invoice, pd.Timestamp("2025-05-01"), [evidence, evidence], True
        )
        assert f["business_review"]["status"] == "eligible"
        assert f["business_review"]["evidence"]["late_count"] == 20
        assert f["direction"] == ("decrease" if effect < 0 else "increase")


@pytest.mark.parametrize(
    "failure",
    ["mismatch", "missing", "small_history", "unstable", "small_effect", "not_checked"],
)
def test_no_business_reason_when_evidence_or_model_checks_fail(history, failure):
    invoice = target().iloc[0]
    evidence = HistoryEvidence(history).for_invoice(
        invoice, features(target(), history)[0]
    )
    other = deepcopy(evidence)
    f = factor()
    checked = True
    if failure == "mismatch":
        other["customer_delay_days"]["source_hash"] = "different-history"
    elif failure == "missing":
        other = None
    elif failure == "small_history":
        evidence["customer_delay_days"]["count"] = 9
        other = deepcopy(evidence)
    elif failure == "unstable":
        f["stability"]["status"] = "unstable"
    elif failure == "small_effect":
        f = factor(effect=-0.8)
    else:
        checked = False
    review_factors([f], invoice, pd.Timestamp("2025-05-01"), [evidence, other], checked)
    assert f["business_review"]["status"] == "withheld"
    assert "evidence" not in f["business_review"]


def test_term_and_history_count_are_context_even_when_large_stable_effects():
    factors = [factor("term_days", 45, -21), factor("customer_history_count", 67, -4)]
    review_factors(factors, target().iloc[0], pd.Timestamp("2025-05-01"), [], True)
    assert all(f["business_review"]["status"] == "context_only" for f in factors)


def test_amount_needs_material_effect_and_gets_no_affordability_story():
    f = factor("amount", 72_000_000, -2)
    f["value_unit"] = "VND"
    review_factors([f], target().iloc[0], pd.Timestamp("2025-05-01"), [], True)
    assert f["business_review"]["status"] == "eligible"
    assert "evidence" not in f["business_review"]
