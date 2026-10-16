"""Descriptive distribution monitoring; does not change the alert policy."""
import numpy as np


def population_stability(reference, current, bins=10, smoothing=.5):
    if bins < 2 or smoothing <= 0:
        raise ValueError("bins must be at least two and smoothing positive")
    ref, cur = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    ref, cur = ref[np.isfinite(ref)], cur[np.isfinite(cur)]
    if not len(ref) or not len(cur):
        return None
    if ref.min() == ref.max():
        value = ref[0]
        margin = max(abs(value) * 1e-6, 1e-6)
        edges = [-np.inf, value - margin, value + margin, np.inf]
    else:
        edges = np.r_[-np.inf, np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)[1:-1])), np.inf]
    p = np.histogram(ref, edges)[0].astype(float) + smoothing
    q = np.histogram(cur, edges)[0].astype(float) + smoothing
    p, q = p / p.sum(), q / q.sum()
    return float(np.sum((q - p) * np.log(q / p)))
