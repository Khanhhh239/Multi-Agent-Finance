"""Bounded tenant adaptation of a pretrained eighteen-feature distribution.

Transformers remain frozen during continuation. Replay limits forgetting; all
choices require past validation, and an independent past audit may reject them.
No test outcomes or raw tenant histories are stored in the global artifact.
"""
from copy import deepcopy
import time

import numpy as np

from .landmark_features import LandmarkHazard, LandmarkEnsemble


def continue_neural(reference, local_x, local_y, local_weights, replay, *, epochs,
                    learning_rate=.0001, replay_fraction=.30):
    if not isinstance(reference, LandmarkHazard) or not reference.name.startswith("neural"):
        raise ValueError("Continuation needs a fitted Neural landmark model")
    if type(epochs) is not int or epochs < 1 or not 0 <= replay_fraction < 1:
        raise ValueError("Invalid continuation budget")
    estimator = deepcopy(reference.booster)
    classifier = estimator.steps[-1][1]
    classifier.set_params(learning_rate_init=learning_rate)
    # sklearn's fitted Adam optimizer retains its old rate unless updated too.
    if hasattr(classifier, "_optimizer"):
        classifier._optimizer.learning_rate_init = learning_rate
        classifier._optimizer.learning_rate = learning_rate
    rx, ry, rw = replay
    local_weights = np.asarray(local_weights, float)
    rw = np.asarray(rw, float)
    x = np.concatenate([local_x, rx])
    y = np.concatenate([local_y, ry])
    weights = np.concatenate([(1-replay_fraction)*local_weights/local_weights.sum(),
                               replay_fraction*rw/rw.sum()]) * len(y)
    transformed = estimator[:-1].transform(x)
    for _ in range(epochs):
        classifier.partial_fit(transformed, y, sample_weight=weights)
    return LandmarkHazard(estimator, reference.name)


def pool(global_model, adapted, weight):
    if weight == 0:
        return global_model
    if weight == 1:
        return adapted
    return LandmarkEnsemble([global_model, adapted], [1-weight, weight])


def continue_tree(reference, local_x, local_y, local_weights, replay, *, rounds,
                  learning_rate, replay_fraction=.30):
    """Append boosting rounds to a copied global; never fit a scratch local tree."""
    if reference.name not in ("lightgbm", "xgboost") or type(rounds) is not int or rounds < 1 or not 0 < learning_rate <= 1 or not 0 <= replay_fraction < 1:
        raise ValueError("Cấu hình học tiếp cây T1 không hợp lệ")
    rx, ry, rw = replay
    x, y = np.concatenate([local_x, rx]), np.concatenate([local_y, ry])
    weights = np.concatenate([(1-replay_fraction)*local_weights/local_weights.sum(), replay_fraction*rw/rw.sum()]) * len(y)
    estimator = deepcopy(reference.booster)
    estimator.set_params(n_estimators=rounds, learning_rate=learning_rate, n_jobs=2)
    started = time.perf_counter()
    if reference.name == "lightgbm":
        base = reference.booster.booster_
        count = base.current_iteration()
        old = base.dump_model()["tree_info"]
        estimator.fit(x, y, sample_weight=weights, init_model=base)
        fitted = estimator.booster_
        added = fitted.current_iteration() - count
        unchanged = fitted.dump_model()["tree_info"][:count] == old
        prefix = fitted.predict(x[:128], num_iteration=count, num_threads=1)
    else:
        base = reference.booster.get_booster()
        count = base.num_boosted_rounds()
        old = base.get_dump(dump_format="json")
        estimator.fit(x, y, sample_weight=weights, xgb_model=base)
        fitted = estimator.get_booster()
        added = fitted.num_boosted_rounds() - count
        unchanged = fitted.get_dump(dump_format="json")[:count] == old
        prefix = fitted.inplace_predict(x[:128], iteration_range=(0, count))
    if added != rounds or not unchanged:
        raise ValueError("Học tiếp T1 không giữ nguyên các cây global")
    np.testing.assert_allclose(prefix, reference.predict_hazard(x[:128]), atol=1e-7, rtol=1e-6)
    return LandmarkHazard(estimator, reference.name), {"rounds_added": added, "global_rounds": count, "old_trees_unchanged": True, "training_seconds": time.perf_counter()-started}
