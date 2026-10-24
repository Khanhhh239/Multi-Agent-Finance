"""Deployable v6 model: the registered S2 configuration trained on all twenty development worlds (dữ liệu tổng hợp).

Configuration (results/v6/v6_frozen.json): L4-FB-PU, w = 0.1, h = 0.5, negative fraction 0.1, 400 fixed trees, two leaf
settings chosen by validation AP, five seeds averaged. `train_final` produces a bundle; `V6Scorer` scores a feature
frame produced by the operational pipeline. The score is a SECONDARY ranking shown beside the primary one: it never
changes which rows are alerted, and it is not a fraud probability. Sealed v6 result for this configuration:
mean recall 64.5 percent at three alerts per company-week, which is why nothing is promised from it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np

from . import screen_v5 as S
from .base_v5 import observed_labels, predict_sequences

SEEDS = (0, 1, 2, 3, 4)


class _Pool(S.SourcePool):
    def fit_booster(self, weight, seed, hn):
        y, sample = observed_labels(self.meta, None, self.balanced, weight, hn)
        self.dataset.set_label(y)
        self.dataset.set_weight(sample * self.meta.factor.to_numpy(dtype=np.float32))
        yv, _ = observed_labels(self.valid_meta, None, False, weight)
        params = dict(objective='binary', learning_rate=S.LR, min_child_samples=10, subsample=.8, subsample_freq=1,
                      colsample_bytree=.6, reg_lambda=2., scale_pos_weight=max(1., (len(y) - y.sum()) / y.sum()) ** .5,
                      seed=seed, num_threads=S.THREADS, verbosity=-1)
        from sklearn.metrics import average_precision_score
        best = (-1., None, None)
        for leaves in S.LEAVES:
            model = lgb.train(dict(params, num_leaves=leaves), self.dataset, num_boost_round=S.ROUNDS)
            ap = float(average_precision_score(yv, predict_sequences(model, self.valid)))
            if ap > best[0]:
                best = (ap, model, leaves)
        return best[1], best[2], best[0]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 22), b''):
            h.update(block)
    return h.hexdigest()


def make_bundle(boosters, columns, meta):
    return {'schema_version': 1, 'kind': 'v6-secondary-score', 'columns': list(columns),
            'boosters': [b.model_to_string() for b in boosters], 'data_origin': 'dữ liệu tổng hợp',
            'not_a_fraud_probability': True, **meta}


def save_bundle(bundle, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path, compress=3)
    return sha256_file(path)


def train_final(matrices, out_path, w=.1, hn=.5, fraction=.1, seeds=SEEDS, threads=6):
    """Train on all twenty development worlds; the reference test split is only a placeholder for the pool's target."""
    S.THREADS = threads
    matrices = Path(matrices)
    pool = _Pool(0, matrices, 'L4-FB-PU', fraction, target_dir=matrices / 's1001')
    columns = [c for c in S._load(matrices / 's1001' / 'manifest.json')['columns']]
    boosters, leaves, aps = [], [], []
    for seed in seeds:
        booster, n_leaves, ap = pool.fit_booster(w, seed, hn)
        boosters.append(booster)
        leaves.append(n_leaves)
        aps.append(ap)
    meta = {'candidate': 'L4-FB-PU', 'w': w, 'h': hn, 'fraction': fraction, 'seeds': list(seeds), 'leaves': leaves,
            'validation_ap': aps, 'trained_on_worlds': list(S.WORLDS), 'source_rows': int(pool.rows)}
    return save_bundle(make_bundle(boosters, columns, meta), out_path), meta


class V6Scorer:
    def __init__(self, bundle):
        if bundle.get('kind') != 'v6-secondary-score':
            raise ValueError('not a v6 secondary-score bundle')
        self.columns = list(bundle['columns'])
        self.meta = {k: v for k, v in bundle.items() if k not in ('boosters', 'columns')}
        self.boosters = [lgb.Booster(model_str=s) for s in bundle['boosters']]

    @classmethod
    def load(cls, path, expected_sha256=None):
        path = Path(path)
        digest = sha256_file(path)
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError('v6 model checksum differs from configuration')
        scorer = cls(joblib.load(path))
        scorer.sha256 = digest
        return scorer

    def score(self, frame):
        missing = [c for c in self.columns if c not in frame.columns]
        if missing:
            raise ValueError(f'frame lacks {len(missing)} model columns, e.g. {missing[:3]}')
        x = frame[self.columns].to_numpy(dtype=np.float32)
        return np.mean([b.predict(x, num_threads=2) for b in self.boosters], axis=0)

    @staticmethod
    def percentile(scores):
        """Share of the week's rows that score lower: 0.99 means the row is in the top one percent."""
        order = scores.argsort(kind='stable').argsort(kind='stable')
        return order / max(1, len(scores) - 1)
