"""Company ML adapters. Every score is larger for a more unusual observation.

ECOD uses training-only empirical CDFs following Li et al. (IEEE TKDE 2022, Eq. 7):
  - Skewness-guided tail selection uses `< 0` for left tail, `> 0` for right tail,
    and `np.maximum(left, right)` when `skew_ == 0` (fixing the `<= 0` + `>= 0`
    double-penalty bug on symmetric features).
  - Sums across features FIRST for `(O_left, O_right, O_auto)` and THEN applies
    `np.maximum.reduce([O_left, O_right, O_auto])` (fixing the elementwise max
    bug that rendered `skew_` mathematically redundant).
  - Excludes `missing:<col>` indicator columns and degenerate zero-variance flags
    so missing optional fields never trigger 99.9th-percentile false-fraud spikes.

The autoencoder is a deterministic `MLPRegressor` bottleneck with `shuffle=True`
and fixed `random_state` (preventing chronological batch bias), masking `missing:*`
and imputed coordinates in MSE, and providing per-feature squared reconstruction
error attributions (`top_contributing_features`).
"""
import warnings

import numpy as np
from scipy.stats import skew
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import ConvergenceWarning
from sklearn.neighbors import LocalOutlierFactor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .method_preprocess import infer_missing_indicator_layout

ALGORITHMS = {
    'isolation_forest': 'Isolation Forest',
    'autoencoder': 'Autoencoder',
    'ecod': 'ECOD',
    'lof': 'Local Outlier Factor (LOF)',
}


def catalog():
    return [dict(id=key, label=label, installed=True, requires_labels=False) for key, label in ALGORITHMS.items()]


def matrix(value):
    x = np.asarray(value, dtype=np.float64)
    if x.ndim != 2 or not len(x) or not x.shape[1] or not np.isfinite(x).all():
        raise ValueError('Ma trận ML cần đủ cột và chỉ chứa số hữu hạn.')
    return x


class FrozenECOD:
    """Frozen-reference Empirical Cumulative-distribution Outlier Detection (Li et al., TKDE 2022)."""

    def __init__(self, *, feature_names=None):
        self.feature_names = tuple(feature_names) if feature_names is not None else None

    def fit(self, x, *, feature_names=None):
        x = matrix(x)
        names = feature_names if feature_names is not None else getattr(self, 'feature_names', None)
        self.feature_names_ = tuple(names) if names is not None else None
        self.reference_ = np.sort(x, axis=0)
        missing_mask, _ = infer_missing_indicator_layout(x, feature_names=names)
        self.missing_mask_ = missing_mask
        span = self.reference_[-1, :] - self.reference_[0, :]
        self.zero_var_mask_ = span <= 1e-12
        self.active_mask_ = ~(self.missing_mask_ | self.zero_var_mask_)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            raw_skew = np.nan_to_num(skew(x, axis=0), nan=0.0, posinf=0.0, neginf=0.0)
        self.skew_ = np.where(np.abs(raw_skew) <= 1e-12, 0.0, np.sign(raw_skew))
        return self

    def _tail_matrices(self, x):
        x = matrix(x)
        n, width = self.reference_.shape
        if x.shape[1] != width:
            raise ValueError('Số feature không khớp model ECOD.')
        p_left = np.empty_like(x)
        p_right = np.empty_like(x)
        floor = 1.0 / (n + 1.0)
        for j in range(width):
            reference = self.reference_[:, j]
            p_left[:, j] = np.searchsorted(reference, x[:, j], side='right') / n
            p_right[:, j] = (n - np.searchsorted(reference, x[:, j], side='left')) / n
        u_left = -np.log(np.maximum(p_left, floor))
        u_right = -np.log(np.maximum(p_right, floor))
        u_auto = np.where(
            self.skew_ < 0.0,
            u_left,
            np.where(self.skew_ > 0.0, u_right, np.maximum(u_left, u_right)),
        )
        active = getattr(self, 'active_mask_', None)
        if active is not None and not np.all(active):
            u_left = np.where(active, u_left, 0.0)
            u_right = np.where(active, u_right, 0.0)
            u_auto = np.where(active, u_auto, 0.0)
        return u_left, u_right, u_auto

    def score(self, x):
        u_left, u_right, u_auto = self._tail_matrices(x)
        # Li et al. (IEEE TKDE 2022, Eq. 7): sum across features FIRST, then max across 3 tail vectors.
        o_left = u_left.sum(axis=1)
        o_right = u_right.sum(axis=1)
        o_auto = u_auto.sum(axis=1)
        return np.maximum.reduce([o_left, o_right, o_auto])


class CompanyEstimator:
    def __init__(self, algorithm, *, feature_names=None, random_state=42):
        if algorithm not in ALGORITHMS:
            raise ValueError('Thuật toán ML không được hỗ trợ.')
        self.algorithm = algorithm
        self.feature_names = tuple(feature_names) if feature_names is not None else None
        self.random_state = int(random_state)

    def fit(self, x, *, feature_names=None):
        x = matrix(x)
        if len(x) < 5:
            raise ValueError('Cần ít nhất 5 dòng train trước khi huấn luyện.')
        self.width_ = x.shape[1]
        names = feature_names if feature_names is not None else getattr(self, 'feature_names', None)
        if names is not None and len(names) != self.width_:
            raise ValueError('feature_names không khớp số cột của ma trận.')
        self.feature_names_ = tuple(names) if names is not None else tuple(f'feature_{j}' for j in range(self.width_))

        missing_mask, paired_map = infer_missing_indicator_layout(x, feature_names=names)
        self.missing_mask_ = missing_mask
        self.paired_missing_map_ = paired_map
        non_missing_cols = np.flatnonzero(~missing_mask)
        if len(non_missing_cols) == 0:
            non_missing_cols = np.arange(self.width_, dtype=int)
        self.active_cols_ = non_missing_cols

        x_eff = x[:, self.active_cols_] if self.algorithm in {'autoencoder', 'lof', 'isolation_forest'} else x
        self.scaler_ = StandardScaler().fit(x_eff) if self.algorithm in {'autoencoder', 'lof'} else None
        z = self.scaler_.transform(x_eff) if self.scaler_ is not None else x_eff

        if self.algorithm == 'isolation_forest':
            self.model_ = IsolationForest(
                n_estimators=100,
                max_samples=min(2048, len(z)),
                random_state=self.random_state,
                n_jobs=1,
            ).fit(z)
        elif self.algorithm == 'lof':
            self.model_ = LocalOutlierFactor(
                n_neighbors=min(20, len(z) - 1),
                novelty=True,
                n_jobs=1,
            ).fit(z)
        elif self.algorithm == 'autoencoder':
            eff_w = z.shape[1]
            middle = max(1, min(8, eff_w // 2))
            mb_size = min(32, max(4, len(z) // 2)) if len(z) >= 8 else len(z)
            self.model_ = MLPRegressor(
                hidden_layer_sizes=(min(32, eff_w), middle, min(32, eff_w)),
                activation='tanh',
                max_iter=200,
                batch_size=mb_size,
                random_state=self.random_state,
                shuffle=True,
                early_stopping=False,
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', ConvergenceWarning)
                self.model_.fit(z, z if eff_w > 1 else z.ravel())
            self.converged_ = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
        elif self.algorithm == 'ecod':
            self.model_ = FrozenECOD(feature_names=names).fit(x, feature_names=names)
        return self

    def _autoencoder_squared_errors(self, x):
        active_cols = getattr(self, 'active_cols_', np.arange(self.width_, dtype=int))
        paired_map = getattr(self, 'paired_missing_map_', {})
        x_eff = x[:, active_cols]
        z = self.scaler_.transform(x_eff) if self.scaler_ is not None else x_eff
        reconstructed = np.asarray(self.model_.predict(z), dtype=float).reshape(z.shape)
        sq_active = (z - reconstructed) ** 2

        obs_mask = np.ones_like(sq_active, dtype=bool)
        for pos, orig_col in enumerate(active_cols):
            miss_col = paired_map.get(int(orig_col))
            if miss_col is not None:
                obs_mask[:, pos] = x[:, miss_col] < 0.5

        masked_sq = np.where(obs_mask, sq_active, 0.0)
        denom = np.maximum(obs_mask.sum(axis=1), 1)
        row_mse = masked_sq.sum(axis=1) / denom

        full_sq = np.zeros((len(x), self.width_), dtype=float)
        full_sq[:, active_cols] = masked_sq
        return row_mse, full_sq

    def score(self, x):
        x = matrix(x)
        if x.shape[1] != self.width_:
            raise ValueError('Số feature không khớp phiên bản ML.')
        active_cols = getattr(self, 'active_cols_', np.arange(self.width_, dtype=int))
        if self.algorithm in {'isolation_forest', 'lof'}:
            x_eff = x[:, active_cols]
            z = self.scaler_.transform(x_eff) if self.scaler_ is not None else x_eff
            scores = -self.model_.score_samples(z)
        elif self.algorithm == 'autoencoder':
            scores, _ = self._autoencoder_squared_errors(x)
        elif self.algorithm == 'ecod':
            scores = self.model_.score(x)
        else:
            raise ValueError('Thuật toán không thuộc bộ ML không nhãn được giữ lại.')
        scores = np.asarray(scores, dtype=float)
        if scores.shape != (len(x),) or not np.isfinite(scores).all():
            raise ValueError('Model trả về điểm không hợp lệ.')
        return scores

    def score_with_attributions(self, x, *, feature_names=None, top_k: int = 5) -> dict:
        """Compute anomaly scores and per-feature attributions (`top_contributing_features`)."""
        x = matrix(x)
        if x.shape[1] != self.width_:
            raise ValueError('Số feature không khớp phiên bản ML.')
        names = (
            tuple(str(c) for c in feature_names)
            if feature_names is not None
            else getattr(self, 'feature_names_', tuple(f'feature_{j}' for j in range(self.width_)))
        )
        if len(names) != self.width_:
            raise ValueError('feature_names không khớp số cột của model.')
        k = max(1, min(int(top_k), self.width_))

        if self.algorithm == 'autoencoder':
            scores, err_matrix = self._autoencoder_squared_errors(x)
            attr_key = 'squared_error'
        elif self.algorithm == 'ecod':
            u_left, u_right, u_auto = self.model_._tail_matrices(x)
            totals = np.stack([u_left.sum(axis=1), u_right.sum(axis=1), u_auto.sum(axis=1)], axis=1)
            winner = np.argmax(totals, axis=1)
            scores = totals[np.arange(len(x)), winner]
            err_matrix = np.where(
                (winner == 0)[:, None],
                u_left,
                np.where((winner == 1)[:, None], u_right, u_auto),
            )
            attr_key = 'tail_neg_log_prob'
        else:
            scores = self.score(x)
            err_matrix = np.zeros((len(x), self.width_), dtype=float)
            attr_key = 'squared_error'

        top_features_per_row = []
        for row_idx in range(len(x)):
            row_errs = err_matrix[row_idx]
            total = float(row_errs.sum())
            ordered = sorted(range(self.width_), key=lambda j: (-float(row_errs[j]), j))
            row_items = []
            for j in ordered[:k]:
                val = float(row_errs[j])
                if val <= 0.0 and row_items:
                    continue
                item = {
                    'feature': names[j],
                    'column_index': int(j),
                    'squared_error': val,
                    'share_of_total_error': float(val / total) if total > 0.0 else 0.0,
                }
                if attr_key != 'squared_error':
                    item[attr_key] = val
                row_items.append(item)
            top_features_per_row.append(row_items)

        return {
            'algorithm': self.algorithm,
            'scores': np.asarray(scores, dtype=float),
            'feature_squared_errors': err_matrix,
            'top_contributing_features': top_features_per_row,
        }

    explain = score_with_attributions
