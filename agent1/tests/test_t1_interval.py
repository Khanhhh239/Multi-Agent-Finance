import numpy as np
import pandas as pd
import pytest
from agent1.models.features import FEATURES
from agent1.models.t1 import HazardGBM


def examples():
    df = pd.DataFrame(np.zeros((40, len(FEATURES))), columns=FEATURES)
    df['cutoff'] = pd.Timestamp('2024-01-01')
    df['top1'], df['top2'] = np.nan, np.nan
    df['age_days'] = np.tile([1., 30.], 20)
    return df


def test_interval_em_handles_right_censoring_and_probability_mass():
    df = examples()
    left = np.tile([1., 28.], 20)
    right = np.tile([7., np.inf], 20)
    m = HazardGBM(dict(num_leaves=7, min_data_in_leaf=2), rounds=25).fit_interval(df, left, right)
    h = m.hazards(df)
    assert h.shape == (40, 13) and np.isfinite(h).all()
    assert h[0, 0] > h[1, 0]  # Nhãn trả tuần đầu so với sống sót ít nhất 4 tuần.


def test_interval_rejects_impossible_bounds():
    with pytest.raises(ValueError):
        HazardGBM().fit_interval(examples(), np.ones(40), np.zeros(40))
