import pandas as pd
import pytest

from analysis.benchmark_t1_v6_final_vs_khanh import validate_pair


def anchors():
    return pd.DataFrame({
        "world": ["W", "W"], "invoice_id": ["I1", "I2"],
        "firm_id": ["F1", "F2"], "cutoff": pd.to_datetime(["2024-07-01"] * 2),
        "time_days": [21, 390], "cause": [1, 2], "obs_days": [500, 500],
        "amount_open": [100., 200.],
    })


def test_accepts_identical_fully_observed_paired_anchors():
    validate_pair(anchors(), anchors())


@pytest.mark.parametrize("column,value", [
    ("invoice_id", "another_invoice"), ("firm_id", "another_tenant"),
    ("cause", 2), ("time_days", 22), ("amount_open", 101.), ("obs_days", 100),
])
def test_rejects_comparison_contaminated_by_anchor_or_outcome_change(column, value):
    original = anchors()
    changed = original.copy()
    changed.loc[0, column] = value
    with pytest.raises(ValueError):
        validate_pair(changed, original)


def test_rejects_silent_prediction_reordering():
    original = anchors()
    with pytest.raises(ValueError):
        validate_pair(original.iloc[::-1].reset_index(drop=True), original)
