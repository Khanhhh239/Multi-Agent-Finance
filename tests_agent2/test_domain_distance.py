"""Domain distance estimator on controlled distributions (synthetic test doubles)."""
import numpy as np
import pandas as pd
import pytest

from agent2.domain_distance import comparable_columns, domain_distance

COLS = [f"f{i}" for i in range(12)] + ["u_entity_r", "week", "t"]


def frame(seed, shift=0., n=1500):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(shift, 1, size=(n, len(COLS))), columns=COLS)


def test_same_distribution_is_near_chance_and_shifted_is_flagged():
    same = domain_distance(frame(1), frame(2), COLS)
    far = domain_distance(frame(1), frame(3, shift=3.), COLS)
    assert same["auc"] < .6 and same["distance"] == "below the warning level"
    assert far["auc"] > .95 and far["distance"] == "large" and "rules" in far["advice"]
    assert not any(c.startswith("u_") for c in comparable_columns(COLS)) and "week" not in comparable_columns(COLS)
    assert same["labels_read"] is False


def test_refuses_too_few_columns_or_rows():
    with pytest.raises(ValueError, match="comparable columns"):
        domain_distance(frame(1), frame(2), COLS[:5])
    with pytest.raises(ValueError, match="rows per side"):
        domain_distance(frame(1, n=100), frame(2, n=100), COLS)
