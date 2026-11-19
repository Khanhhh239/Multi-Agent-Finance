"""Guard the statistical denominators used by the retrospective diagnosis."""
import numpy as np
import pandas as pd

from analysis.diagnose_t1_v6 import independent_labels, risk_counts, weekly_comparison


def test_risk_counts_exclude_partial_censor_week_and_every_terminal_cause():
    # Paid at day 7 leaves before week 2; censor at day 10 contributes only week 1.
    # A known event at day 9 in an incomplete admin week must also be excluded.
    table = risk_counts(np.array([7, 14, 21, 10, 9]),
                        np.array([30, 30, 30, 10, 10]),
                        np.array([1, 2, 3, 0, 1]))
    assert table.risk_n.head(4).tolist() == [5, 2, 1, 0]
    assert table.n_paid.sum() == 1
    assert table.n_writeoff.sum() == 1
    assert table.n_credit_note.sum() == 1
    assert table.n_open.sum() == 5


def test_weekly_hazard_averages_predictions_on_observed_risk_only():
    frame = pd.DataFrame({"time_days": [7, 14, 10], "obs_days": [30, 30, 10], "cause": [1, 2, 0]})
    h = np.tile([.5, .4, .1, 0], (3, 53, 1))
    # A closed invoice's high week-2 forecast must not enter the risk-set mean.
    h[0, 1] = [.01, .98, .01, 0]
    table = pd.DataFrame(weekly_comparison(frame, h, "example"))
    paid = table[(table.week == 2) & (table.cause == "paid")].iloc[0]
    wo = table[(table.week == 2) & (table.cause == "writeoff")].iloc[0]
    assert paid.risk_n == 1
    assert paid.predicted_hazard_on_observed_risk == .4
    assert paid.observed_hazard == 0
    assert wo.observed_hazard == 1
    # Model survivor mass is a distinct quantity, never the empirical denominator.
    assert wo.model_risk_n == 1.5


def test_independent_labels_align_repeated_invoice_anchors_and_admin_end():
    raw = pd.DataFrame({"invoice_id": ["a", "b", "c"],
                        "closed_date_true": pd.to_datetime(["2024-01-15", "2025-01-01", None]),
                        "closure_type": ["paid_after_credit_note", "writeoff", "open"]})
    frame = pd.DataFrame({"invoice_id": ["b", "a", "a", "c"],
                          "cutoff": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-08", "2024-01-01"])})
    times, obs, causes, _ = independent_labels(frame, raw, "2024-12-31")
    assert causes.tolist() == [0, 1, 1, 0]
    assert times.tolist() == [365, 14, 7, 365]
    assert obs.tolist() == [365, 365, 358, 365]
