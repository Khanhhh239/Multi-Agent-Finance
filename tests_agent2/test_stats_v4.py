import numpy as np
import pandas as pd
import pytest

from agent2.stats_v4 import paired_bootstrap


def sample():
    return pd.DataFrame({"company_id": ["a"] * 6, "case_id": ["x", "x", "y", "y", "", ""],
                         "is_fraud": [1, 1, 1, 1, 0, 0]})


def test_identical_alerts_have_zero_difference():
    a = np.array([1, 0, 0, 1, 1, 0], dtype=bool)
    r = paired_bootstrap(sample(), a, a, reps=100)
    for key in ("recall_delta", "case_recall_delta"):
        assert r[key] == {"estimate": 0.0, "ci95": [0.0, 0.0]}


def test_strictly_better_alerts_have_positive_interval():
    r = paired_bootstrap(sample(), [1, 1, 1, 1, 0, 0], [0] * 6, reps=100)
    for key in ("recall_delta", "case_recall_delta"):
        assert r[key] == {"estimate": 1.0, "ci95": [1.0, 1.0]}


def test_cases_are_clustered_and_scoped_by_company():
    te = pd.DataFrame({"company_id": ["a", "a", "b"], "case_id": ["x"] * 3, "is_fraud": [1] * 3})
    r = paired_bootstrap(te, [1, 0, 0], [0, 0, 1], reps=100)
    assert r["cases"] == 2
    assert r["recall_delta"]["estimate"] == 0
    assert r["case_recall_delta"]["estimate"] == 0
    assert r == paired_bootstrap(te, [1, 0, 0], [0, 0, 1], reps=100)


def test_invalid_shape_rejected():
    with pytest.raises(ValueError, match="align"):
        paired_bootstrap(sample(), [True], [False])
