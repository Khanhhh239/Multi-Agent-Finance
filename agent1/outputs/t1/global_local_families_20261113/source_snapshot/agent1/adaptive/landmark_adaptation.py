"""Bounded tenant adaptation of a pretrained eighteen-feature distribution.

Transformers remain frozen during continuation. Replay limits forgetting; all
choices require past validation, and an independent past audit may reject them.
No test outcomes or raw tenant histories are stored in the global artifact.
"""
from copy import deepcopy

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
