"""Chỉ số T11: đo phân phối chứ không chỉ điểm (pinball, độ phủ, interval score, CRPS, Brier/IBS, ECE, C-index, WAPE)."""
from __future__ import annotations

import numpy as np


def pinball(y, q, alpha):
    d = np.asarray(y, float) - np.asarray(q, float)
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def coverage(y, lo, hi):
    y = np.asarray(y, float)
    return float(np.mean((y >= lo) & (y <= hi)))


def interval_score(y, lo, hi, alpha=0.2):
    """Winkler / interval score (Gneiting & Raftery 2007) cho khoảng trung tâm (1-alpha)."""
    y, lo, hi = (np.asarray(v, float) for v in (y, lo, hi))
    return float(np.mean((hi - lo) + 2 / alpha * (lo - y) * (y < lo) + 2 / alpha * (y - hi) * (y > hi)))


def crps_from_quantiles(y, Q, alphas):
    """CRPS ≈ 2 * trung bình pinball trên lưới phân vị dày."""
    return float(2 * np.mean([pinball(y, Q[:, i], a) for i, a in enumerate(alphas)]))


def crps_samples(y, S):
    """CRPS thực nghiệm từ mẫu Monte Carlo: E|X-y| - 0.5 E|X-X'| (S: n x m)."""
    y = np.asarray(y, float)[:, None]
    S = np.sort(np.asarray(S, float), axis=1)
    m = S.shape[1]
    t1 = np.mean(np.abs(S - y), axis=1)
    i = np.arange(1, m + 1)
    t2 = np.sum((2 * i - m - 1) * S, axis=1) / (m * m)
    return float(np.mean(t1 - t2))


def brier(y, p):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def logloss(y, p, eps=1e-6):
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(y, p, bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(e)


def ibs_weekly(rem_days, cdf, weeks=13):
    """Integrated Brier score trên lưới tuần: cdf[:, k-1] = P(trả trong <= 7k ngày). Nhãn đầy đủ (không kiểm duyệt)."""
    rem = np.asarray(rem_days, float)
    out = []
    for k in range(1, weeks + 1):
        out.append(np.mean(((rem <= 7 * k).astype(float) - cdf[:, k - 1]) ** 2))
    return float(np.mean(out)), np.array(out)


def c_index(time, event, risk, n_pairs=400_000, seed=0):
    """Harrell C (lấy mẫu cặp). risk cao = trả SỚM hơn (dùng -expected_time)."""
    rng = np.random.default_rng(seed)
    t, e, r = (np.asarray(v, float) for v in (time, event, risk))
    n = len(t)
    i = rng.integers(0, n, n_pairs)
    j = rng.integers(0, n, n_pairs)
    ok = (t[i] < t[j]) & (e[i] == 1)
    if not ok.any():
        return np.nan
    ri, rj = r[i][ok], r[j][ok]
    return float(np.mean((ri > rj) + 0.5 * (ri == rj)))


def wape(actual, pred):
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    return float(np.sum(np.abs(a - p)) / max(np.sum(np.abs(a)), 1e-9))


def bootstrap_ci(fn, *arrays, n=300, seed=0, groups=None):
    """CI 95% bằng bootstrap (theo cụm nếu có groups, ví dụ cụm = công ty)."""
    rng = np.random.default_rng(seed)
    arrays = [np.asarray(a) for a in arrays]
    vals = []
    if groups is None:
        N = len(arrays[0])
        for _ in range(n):
            ix = rng.integers(0, N, N)
            vals.append(fn(*[a[ix] for a in arrays]))
    else:
        groups = np.asarray(groups)
        ug = np.unique(groups)
        pos = {g: np.nonzero(groups == g)[0] for g in ug}
        for _ in range(n):
            pick = rng.choice(ug, len(ug))
            ix = np.concatenate([pos[g] for g in pick])
            vals.append(fn(*[a[ix] for a in arrays]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))
