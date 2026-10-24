"""Domain distance between a real company's features and the synthetic development features (Pha E, step E4.2).

A classifier is trained to tell the two apart with cross-validation. An AUC above 0.9 (the registered warning level)
means real data look very different from what the supervised model learned on, so the pre-trained score may not
transfer: run rules and entity deviations only and treat any v6 score as unreliable. This tool never reads labels.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

WARNING_AUC = .9
EXCLUDED_PREFIXES = ("u_",)          # unsupervised signals are calibrated per scope (world or company), not comparable


def comparable_columns(columns):
    return [c for c in columns if not c.startswith(EXCLUDED_PREFIXES) and c not in ("week", "t")]


def domain_distance(real, reference, columns, seed=0, folds=5, max_rows=20_000):
    cols = [c for c in comparable_columns(columns) if c in real.columns and c in reference.columns]
    if len(cols) < 10:
        raise ValueError(f"only {len(cols)} comparable columns; refusing to estimate")
    n = min(len(real), len(reference), max_rows)
    if n < 200:
        raise ValueError(f"only {n} rows per side; need at least 200")
    rng = np.random.default_rng(seed)
    a = real[cols].iloc[rng.choice(len(real), n, replace=False)].to_numpy(dtype=np.float32)
    b = reference[cols].iloc[rng.choice(len(reference), n, replace=False)].to_numpy(dtype=np.float32)
    x, y = np.vstack([a, b]), np.r_[np.ones(n), np.zeros(n)]
    scores, gain = np.zeros(len(y)), np.zeros(len(cols))
    params = dict(objective="binary", num_leaves=15, learning_rate=.1, min_child_samples=20, subsample=.8, subsample_freq=1,
                  colsample_bytree=.8, seed=seed, verbosity=-1, num_threads=4)
    for train, test in StratifiedKFold(folds, shuffle=True, random_state=seed).split(x, y):
        model = lgb.train(params, lgb.Dataset(x[train], label=y[train]), 100)
        scores[test] = model.predict(x[test])
        gain += model.feature_importance("gain")
    auc = float(roc_auc_score(y, scores))
    top = [cols[i] for i in np.argsort(-gain)[:10]]
    verdict = ("large" if auc > WARNING_AUC else "below the warning level")
    advice = ("Real data look very different from the synthetic training worlds: run rules and entity deviations only; "
              "do not rely on the v6 secondary score." if auc > WARNING_AUC else
              "No domain-distance warning. This does not show the model transfers; it only fails to rule it out.")
    return {"auc": auc, "rows_per_side": int(n), "columns_used": len(cols), "top_distinguishing_columns": top,
            "warning_level": WARNING_AUC, "distance": verdict, "advice": advice, "labels_read": False}
