"""Private whitelist extension with exactly the original v6 risk-set rules."""
from __future__ import annotations

import numpy as np

from agent1.models import t1
from experiments.t1_competing_v6.core import WEEKS, validate_hazards, week_matrix as original_matrix
from experiments.t1_competing_v6.features import V6_FEATURES
from experiments.t1_credit_context.practical import PRACTICAL_CONTEXT_FEATURES
from .ledger import BEHAVIOR_FEATURES


ARMS = {
    "v6": list(V6_FEATURES),
    "industry": list(V6_FEATURES) + PRACTICAL_CONTEXT_FEATURES,
    "behavior": list(V6_FEATURES) + BEHAVIOR_FEATURES,
    "both": list(V6_FEATURES) + PRACTICAL_CONTEXT_FEATURES + BEHAVIOR_FEATURES,
}


def week_matrix(frame, week, features):
    if features not in ARMS.values():
        raise ValueError("Only four locked ablation feature sets are accepted")
    base = original_matrix(frame, week, V6_FEATURES)
    extra = features[len(V6_FEATURES):]
    if not extra:
        return base
    n = len(V6_FEATURES)
    return np.hstack([base[:, :n], frame[extra].to_numpy(np.float32), base[:, n:]])


def expand_weekly(frame, features):
    matrices, labels = [], []
    times, obs, causes = (frame[n].to_numpy(int) for n in ("time_days", "obs_days", "cause"))
    for week in range(1, WEEKS + 1):
        left, right = 7 * (week - 1), 7 * week
        keep = (times > left) & (obs >= right)
        if keep.any():
            matrices.append(week_matrix(frame.loc[keep], week, features))
            labels.append(np.where(times[keep] <= right, causes[keep], 0).astype(np.int8))
    if not matrices:
        raise ValueError("No fully observed risk rows")
    return np.vstack(matrices), np.concatenate(labels)


def predict_hazards(model, frame, features, active):
    if model.feature_name() != features + t1.WEEK_FEATS:
        raise ValueError("Model input feature order mismatch")
    result = np.zeros((len(frame), WEEKS, 4), np.float32)
    for week in range(1, WEEKS + 1):
        probability = model.predict(week_matrix(frame, week, features), num_threads=4)
        result[:, week - 1, active] = probability
    return validate_hazards(result)
