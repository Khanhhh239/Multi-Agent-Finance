"""Verify genuine tree continuation and cross-family sample/weight parity."""

import pickle

import numpy as np
import pytest
from agent1.adaptive.landmark_features import LandmarkHazard
from experiments.t1_compact.global_local_families import (
    continue_tree,
    fingerprint,
    mix_training,
    tree_count,
)
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier


@pytest.mark.parametrize("family", ["lightgbm", "xgboost"])
def test_continuation_adds_trees_preserves_global_and_serializes(family):
    rng = np.random.default_rng(42)
    x = rng.normal(size=(600, 19))
    y = (x[:, 0] + rng.normal(size=600) > 0).astype(int)
    options = {"n_estimators": 8, "learning_rate": 0.05, "n_jobs": 1, "random_state": 42}
    classifier = (
        LGBMClassifier(**options, verbosity=-1, min_child_samples=10)
        if family == "lightgbm"
        else XGBClassifier(**options, max_depth=2)
    )
    classifier.fit(x, y)
    reference = LandmarkHazard(classifier, family)
    before = pickle.dumps(reference, protocol=pickle.HIGHEST_PROTOCOL)
    arrays = (x[100:], y[100:], np.ones(500))
    replay = (x[:100], y[:100], np.ones(100))
    adapted, trace = continue_tree(
        reference, arrays, replay, learning_rate=0.02, rounds=4
    )
    assert tree_count(adapted) == 12
    assert trace["rounds_added"] == 4
    assert trace["old_trees_unchanged"]
    assert pickle.dumps(reference, protocol=pickle.HIGHEST_PROTOCOL) == before
    assert not np.allclose(reference.predict_hazard(x), adapted.predict_hazard(x))
    restored = pickle.loads(pickle.dumps(adapted))
    np.testing.assert_array_equal(restored.predict_hazard(x), adapted.predict_hazard(x))


def test_replay_is_weight_mass_and_all_families_receive_identical_rows():
    local = (
        np.arange(76).reshape(4, 19),
        np.array([0, 1, 0, 1]),
        np.array([1.0, 2.0, 3.0, 4.0]),
    )
    replay = (np.arange(38).reshape(2, 19), np.array([0, 1]), np.array([2.0, 1.0]))
    x, y, w = mix_training(local, replay, 0.30)
    np.testing.assert_array_equal(x[:4], local[0])
    np.testing.assert_array_equal(y[4:], replay[1])
    assert w[:4].sum() / w.sum() == pytest.approx(0.70)
    assert w[4:].sum() / w.sum() == pytest.approx(0.30)
    assert fingerprint((x, y, w)) == fingerprint(mix_training(local, replay, 0.30))
