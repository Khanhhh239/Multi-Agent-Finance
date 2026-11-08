"""Company ML adapters. Every score is larger for a more unusual observation.

ECOD uses training-only empirical CDFs (a frozen-reference inference variant).
The autoencoder is a deterministic sklearn MLP reconstruction bottleneck.
"""
from importlib.util import find_spec
import warnings

import numpy as np
from scipy.stats import skew
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import ConvergenceWarning
from sklearn.neighbors import LocalOutlierFactor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

ALGORITHMS = {
    'isolation_forest': 'Isolation Forest', 'autoencoder': 'Autoencoder',
    'ecod': 'ECOD', 'lof': 'Local Outlier Factor (LOF)', 'catboost': 'CatBoost',
    'bag_injection': 'Túi phương pháp (chọn theo tiêm gian lận)',
}


def catalog():
    return [dict(id=key, label=label, installed=key != 'catboost' or find_spec('catboost') is not None,
                 requires_labels=key == 'catboost') for key, label in ALGORITHMS.items()]


def matrix(value):
    x = np.asarray(value, dtype=np.float64)
    if x.ndim != 2 or not len(x) or not x.shape[1] or not np.isfinite(x).all():
        raise ValueError('Ma trận ML cần đủ cột và chỉ chứa số hữu hạn.')
    return x


class FrozenECOD:
    def fit(self, x):
        x = matrix(x)
        self.reference_ = np.sort(x, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            self.skew_ = np.sign(np.nan_to_num(skew(x, axis=0)))
        return self

    def score(self, x):
        x = matrix(x)
        n, width = self.reference_.shape
        if x.shape[1] != width:
            raise ValueError('Số feature không khớp model ECOD.')
        left = np.empty_like(x); right = np.empty_like(x)
        floor = 1 / (n + 1)
        for j in range(width):
            reference = self.reference_[:, j]
            left[:, j] = np.searchsorted(reference, x[:, j], side='right') / n
            right[:, j] = (n - np.searchsorted(reference, x[:, j], side='left')) / n
        left = -np.log(np.maximum(left, floor))
        right = -np.log(np.maximum(right, floor))
        adjusted = np.where(self.skew_ <= 0, left, 0) + np.where(self.skew_ >= 0, right, 0)
        return np.maximum(np.maximum(left, right), adjusted).sum(axis=1)


class CompanyEstimator:
    def __init__(self, algorithm):
        if algorithm not in ALGORITHMS:
            raise ValueError('Thuật toán ML không được hỗ trợ.')
        self.algorithm = algorithm

    def fit(self, x, y=None, columns=None):
        x = matrix(x)
        if self.algorithm == 'bag_injection':      # chooses among label-free methods by injecting patterns into this company's rows
            from .bag_of_methods import BagOfMethods
            self.width_ = x.shape[1]
            self.model_ = BagOfMethods().fit(x, columns)
            self.diagnostics_ = self.model_.diagnostics_
            return self
        if len(x) < 5:
            raise ValueError('Cần ít nhất 5 dòng train trước khi huấn luyện.')
        self.width_ = x.shape[1]
        self.scaler_ = StandardScaler().fit(x) if self.algorithm in {'autoencoder', 'lof'} else None
        z = self.scaler_.transform(x) if self.scaler_ is not None else x
        if self.algorithm == 'isolation_forest':
            self.model_ = IsolationForest(n_estimators=100, max_samples=min(2048, len(x)),
                                          random_state=42, n_jobs=1).fit(z)
        elif self.algorithm == 'lof':
            self.model_ = LocalOutlierFactor(n_neighbors=min(20, len(x)-1), novelty=True, n_jobs=1).fit(z)
        elif self.algorithm == 'autoencoder':
            middle = max(1, min(8, self.width_ // 2))
            self.model_ = MLPRegressor(hidden_layer_sizes=(min(32, self.width_), middle, min(32, self.width_)),
                activation='tanh', max_iter=200, random_state=42, shuffle=False, early_stopping=False)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', ConvergenceWarning)
                self.model_.fit(z, z if self.width_ > 1 else z.ravel())
            self.converged_ = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
        elif self.algorithm == 'ecod':
            self.model_ = FrozenECOD().fit(z)
        else:
            if y is None or set(np.asarray(y).tolist()) != {0, 1} or len(y) != len(x):
                raise ValueError('CatBoost cần nhãn 0 và 1 đã được rà cho mọi dòng train.')
            try:
                from catboost import CatBoostClassifier
            except ImportError as exc:
                raise ValueError('Chưa cài CatBoost; cài requirements-company-ml.txt trong môi trường máy chủ.') from exc
            self.model_ = CatBoostClassifier(iterations=100, depth=5, random_seed=42, thread_count=1,
                verbose=False, allow_writing_files=False, loss_function='Logloss').fit(z, y)
        return self

    def score(self, x):
        x = matrix(x)
        if x.shape[1] != self.width_:
            raise ValueError('Số feature không khớp phiên bản ML.')
        if self.algorithm == 'bag_injection':
            return np.asarray(self.model_.score(x), dtype=float)
        z = self.scaler_.transform(x) if self.scaler_ is not None else x
        if self.algorithm in {'isolation_forest', 'lof'}:
            scores = -self.model_.score_samples(z)
        elif self.algorithm == 'autoencoder':
            reconstructed = np.asarray(self.model_.predict(z)).reshape(z.shape)
            scores = np.mean((z-reconstructed)**2, axis=1)
        elif self.algorithm == 'ecod':
            scores = self.model_.score(z)
        else:
            scores = self.model_.predict_proba(z)[:, 1]
        scores = np.asarray(scores, dtype=float)
        if scores.shape != (len(x),) or not np.isfinite(scores).all():
            raise ValueError('Model trả về điểm không hợp lệ.')
        return scores
