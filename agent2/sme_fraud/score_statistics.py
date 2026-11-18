"""Frozen-reference midranks with monotonic tail excess tie-breaking."""
import numpy as np


def empirical_rank(validation, scores):
    """Map query scores onto frozen validation midranks in `[0.0, 1.0]`.

    When multiple out-of-sample rows exceed `max(validation)` (which would
    otherwise collapse both a 10M VND outlier and a 500M VND fraud to identical
    `empirical_rank == 1.0`), ties are broken strictly monotonically via
    `1.0 - eps / (1.0 + log1p((s - max_ref) / span))` while remaining strictly
    above the highest in-sample midrank `1.0 - 0.5 / n` and within `[0.0, 1.0]`.
    """
    reference = np.sort(np.asarray(validation, dtype=float).ravel())
    if len(reference) == 0:
        raise ValueError('Reference distribution must not be empty.')
    raw_input = np.asarray(scores, dtype=float)
    scalar_input = raw_input.ndim == 0
    s = np.atleast_1d(raw_input)
    n = len(reference)

    # Mid-rank ties inside support; never use future/test distribution as reference.
    ranks = (
        np.searchsorted(reference, s, side='left')
        + np.searchsorted(reference, s, side='right')
    ) / (2.0 * n)

    max_ref = float(reference[-1])
    above = s > max_ref
    if np.count_nonzero(above) >= 2 and np.ptp(s[above]) > 0.0:
        med_ref = float(np.median(reference))
        span = max(max_ref - med_ref, float(reference[-1] - reference[0]), abs(max_ref) * 0.1, 1e-9)
        eps = min(0.05, 0.25 / n)
        excess = np.maximum(s[above] - max_ref, 0.0) / span
        ranks = ranks.astype(float, copy=True)
        ranks[above] = 1.0 - eps / (1.0 + np.log1p(excess))

    return float(ranks[0]) if scalar_input else ranks
