"""Retained label-free statistical primitives; no injection selector or alert policy."""
import numpy as np
from sklearn.covariance import OAS
from sklearn.linear_model import Ridge


class RobustZ:
    """Sum of the largest robust z-scores (median/MAD with a floor), a simple probabilistic rule layer."""
    def fit(self, x):
        self.med_ = np.median(x, axis=0)
        mad = np.median(np.abs(x - self.med_), axis=0) * 1.4826
        self.scale_ = np.maximum(mad, np.maximum(.1 * x.std(axis=0), 1e-3))
        return self

    def score(self, x):
        z = np.minimum(np.abs(x - self.med_) / self.scale_, 10.)
        return np.sort(z, axis=1)[:, -5:].sum(axis=1)


class TailExceedance:
    """Dynamic-threshold analogue: columns beyond the company's own 1st/99th percentile, weighted by the excess."""
    def fit(self, x):
        self.lo_, self.hi_ = np.percentile(x, 1, axis=0), np.percentile(x, 99, axis=0)
        self.scale_ = np.maximum(x.std(axis=0), 1e-3)
        return self

    def score(self, x):
        above = np.maximum(x - self.hi_, 0) / self.scale_
        below = np.maximum(self.lo_ - x, 0) / self.scale_
        return np.log1p(above + below).sum(axis=1)


class ShrunkMahalanobis:
    """Squared Mahalanobis distance with a shrinkage covariance (joint unusualness of many features)."""
    def fit(self, x):
        self.mean_, self.std_ = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
        self.cov_ = OAS().fit((x - self.mean_) / self.std_)
        return self

    def score(self, x):
        return self.cov_.mahalanobis((x - self.mean_) / self.std_)


class MaskedField:
    """Self-supervised: predict the most variable columns from the rest; surprise is the standardised residual."""
    def __init__(self, targets=12):
        self.targets = targets

    def fit(self, x):
        self.mean_, self.std_ = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
        z = (x - self.mean_) / self.std_
        spread = np.asarray([len(np.unique(x[:, j])) for j in range(x.shape[1])])
        eligible = np.flatnonzero(spread > 5)
        self.cols_ = eligible[np.argsort(-x.std(axis=0)[eligible])][:self.targets]
        self.models_, self.scales_ = [], []
        for j in self.cols_:
            rest = np.delete(z, j, axis=1)
            model = Ridge(alpha=5.).fit(rest, z[:, j])
            residual = z[:, j] - model.predict(rest)
            self.models_.append(model)
            self.scales_.append(max(np.median(np.abs(residual)) * 1.4826, .05))
        return self

    def score(self, x):
        z = (x - self.mean_) / self.std_
        surprises = []
        for j, model, scale in zip(self.cols_, self.models_, self.scales_):
            surprises.append(np.minimum(np.abs(z[:, j] - model.predict(np.delete(z, j, axis=1))) / scale, 12.))
        if not surprises:
            return np.zeros(len(x))
        return np.sort(np.stack(surprises, axis=1), axis=1)[:, -3:].mean(axis=1)


class Reference:
    """Tail-probability scale of one method from out-of-sample real validation scores."""
    def __init__(self, scores):
        self.sorted_ = np.sort(np.asarray(scores, dtype=float))
        self.n_ = len(self.sorted_)
        median = np.median(self.sorted_)
        self.top_ = self.sorted_[-1]
        self.span_ = max(np.percentile(self.sorted_, 99) - median, 1e-9)

    def surprise(self, scores):
        s = np.asarray(scores, dtype=float)
        tail = 1 - np.searchsorted(self.sorted_, s, side='right') / self.n_
        base = -np.log(np.maximum(tail, 1 / (self.n_ + 1)))
        return base + np.log1p(np.maximum(s - self.top_, 0) / self.span_)


def combine(surprises, members, kind):
    stack = np.stack([surprises[m] for m in members], axis=0)
    return stack.max(axis=0) if kind == 'max' else stack.mean(axis=0)
