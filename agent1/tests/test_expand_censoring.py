"""Hồi quy cho lỗi khai triển hazard (Sprint 1, 20/10/2026).

Dữ liệu: thời gian trả hình học với hazard tuần h thật đã biết; kiểm duyệt hành chính ngẫu nhiên (cắt giữa tuần).
Với khai triển đúng, tỷ lệ y=1 trong các hàng (i, k) ≈ h. Bản cũ (giữ sự kiện trong tuần bị cắt, bỏ không-sự-kiện) thổi phồng.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models import t1  # noqa: E402
from agent1.models.features import FEATURES  # noqa: E402


def _frame(n=20000, h=0.2, seed=0):
    rng = np.random.default_rng(seed)
    week = rng.geometric(h, n)                       # tuần trả 1, 2, ...
    day_in_week = rng.integers(1, 8, n)
    rem = 7 * (week - 1) + day_in_week               # số ngày còn lại thật
    obs = rng.uniform(1, 60, n)                      # cắt hành chính bất kỳ, thường giữa tuần
    df = pd.DataFrame({c: 0.0 for c in FEATURES}, index=range(n))
    df["cutoff"] = pd.Timestamp("2024-01-01")
    df["days_to_due"] = 10.0
    df["remaining"] = rem.astype(float)
    df["obs_window"] = obs
    df["event"] = (rem <= obs).astype(int)
    df["time_obs"] = np.minimum(rem, obs)
    return df


def _empirical_hazard(df):
    X, y, _ = t1.expand(df, True)
    k = X[:, len(FEATURES)]
    return np.array([y[k == kk].mean() for kk in range(1, 6)])


def test_full_week_expand_is_unbiased():
    old = t1.FULL_WEEK_ONLY
    try:
        t1.FULL_WEEK_ONLY = True
        hz = _empirical_hazard(_frame())
        assert np.all(np.abs(hz - 0.2) < 0.02), hz
    finally:
        t1.FULL_WEEK_ONLY = old


def test_legacy_expand_inflates_hazard():
    old = t1.FULL_WEEK_ONLY
    try:
        t1.FULL_WEEK_ONLY = False
        hz = _empirical_hazard(_frame())
        assert hz[1:].mean() > 0.21, hz   # thiên lệch dương (~8% ở cắt đều 1–60 ngày; lớn hơn khi dữ liệu ngắn)
    finally:
        t1.FULL_WEEK_ONLY = old


def test_hazard_lr_clips_extrapolation():
    X = np.random.default_rng(1).normal(size=(500, 3))
    m = t1.HazardLR.__new__(t1.HazardLR)
    m.feats = ["a", "b", "c"]
    m._prep(X, fit=True)
    Z = m._prep(X * 1000)
    assert np.abs(Z[:, :3]).max() <= t1.Z_CLIP + 1e-9
