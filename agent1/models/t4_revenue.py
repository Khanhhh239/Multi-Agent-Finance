"""T4 — doanh thu mới chưa lập hoá đơn: dự báo phân vị đa chân trời (1..13 tuần) cho chuỗi doanh thu tuần.

Mô hình chính: LightGBM phân vị TOÀN CỤC, trực tiếp đa chân trời (horizon là đặc trưng), chuẩn hoá theo quy mô
(chia trung bình 13 tuần gần nhất -> bất biến đơn vị VND/GBP, học chung nhiều công ty -> chuyển miền tốt),
biến lịch của tuần đích (Tết, Giáng sinh, số ngày làm việc). Mốc: naive theo mùa (52 tuần), trung bình 13 tuần
(+ phân vị phần dư thực nghiệm), Chronos-Bolt zero-shot (mô hình nền tảng, nếu cài được).
"""
from __future__ import annotations

import numpy as np

from ..threads import NT
import pandas as pd
import lightgbm as lgb

from .. import calendar_vn as cal

H = 13
QS = (0.1, 0.5, 0.9)
NLAG = 13


def _cal_feats(weeks: pd.DatetimeIndex, vn: bool):
    woy = weeks.isocalendar().week.values.astype(int)
    tet = np.zeros(len(weeks))
    dtt = np.zeros(len(weeks))
    if vn:
        for i, w in enumerate(weeks):
            d = cal.days_to_tet(w + pd.Timedelta(days=3))
            dtt[i] = np.clip(d, -60, 60)
            tet[i] = any(cal.in_tet_break(w + pd.Timedelta(days=j)) for j in range(7))
    xmas = ((weeks.month == 12) & (weeks.day >= 20)) | ((weeks.month == 1) & (weeks.day <= 3))
    return woy, weeks.month.values, tet, dtt, xmas.astype(float)


def make_rows(y: np.ndarray, weeks: pd.DatetimeIndex, vn: bool, origins, with_target=True):
    woy, mon, tet, dtt, xmas = _cal_feats(weeks, vn)
    n = len(y)
    X, Y, meta = [], [], []
    for t in origins:
        if t < NLAG + 4:
            continue
        s = y[t - 12:t + 1].mean() + 1e-9
        lags = y[t - NLAG + 1:t + 1][::-1] / s
        r4 = y[t - 3:t + 1].mean() / s
        r26 = y[max(0, t - 25):t + 1].mean() / s
        zero_share = np.mean(y[t - 12:t + 1] == 0)
        for h in range(1, H + 1):
            j = t + h
            if with_target and j >= n:
                break
            jj = min(j, n - 1) if with_target else j
            if not with_target and j >= len(woy):
                break
            sl = y[j - 52] / s if j - 52 >= 0 and j - 52 <= t else np.nan
            sl1 = y[j - 53] / s if j - 53 >= 0 and j - 53 <= t else np.nan
            X.append(np.r_[lags, r4, r26, zero_share, h, sl, sl1, woy[jj], mon[jj], tet[jj], dtt[jj], xmas[jj],
                           np.log1p(s)])
            Y.append(y[j] / s if with_target else np.nan)
            meta.append((t, h, s))
    return np.array(X, dtype="float32"), np.array(Y, dtype="float32"), np.array(meta)


FEATS = [f"lag{i}" for i in range(NLAG)] + ["r4", "r26", "zero_share", "h", "slag52", "slag53", "woy", "month", "tet",
                                             "days_to_tet", "xmas", "log_scale"]


class GlobalQuantileLGBM:
    def __init__(self, rounds=500):
        self.rounds, self.m = rounds, {}

    def fit(self, X, Y):
        for q in QS:
            p = dict(objective="quantile", alpha=q, learning_rate=0.04, num_leaves=31, min_data_in_leaf=50,
                     feature_fraction=0.85, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, seed=2, num_threads=NT)
            self.m[q] = lgb.train(p, lgb.Dataset(X, Y, feature_name=FEATS), self.rounds)
        return self

    def predict(self, X):
        return np.sort(np.column_stack([self.m[q].predict(X) for q in QS]), axis=1).clip(0, None)


def baseline_rows(y, meta, kind):
    """Dự báo điểm của mốc + phân vị từ phần dư lịch sử cùng chân trời (tính trong mẫu, không nhìn tương lai)."""
    out = np.zeros((len(meta), 3))
    for i, (t, h, s) in enumerate(meta):
        t, h = int(t), int(h)
        hist_t = np.arange(max(NLAG + 4, t - 104), t - h + 1)
        def point(tt):
            if kind == "snaive" and tt + h - 52 >= 0:
                return y[tt + h - 52]
            return y[max(0, tt - 12):tt + 1].mean()
        f = point(t)
        res = np.array([y[tt + h] - point(tt) for tt in hist_t]) if len(hist_t) > 8 else np.array([0.0])
        qs = np.quantile(res, QS)
        out[i] = np.clip(f + qs, 0, None)
    return out


def chronos_predict(series_list, horizon=H, model_id="amazon/chronos-bolt-small"):
    """Chronos-Bolt zero-shot: trả về list mảng (horizon x 3) phân vị 0.1/0.5/0.9; None nếu không chạy được."""
    try:
        import torch
        from chronos import BaseChronosPipeline
        torch.set_num_threads(min(NT,4))
    except Exception:  # noqa: BLE001
        return None
    pipe = BaseChronosPipeline.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32)
    out = []
    B = 64
    for i in range(0, len(series_list), B):
        ctx = [torch.tensor(s[-512:], dtype=torch.float32) for s in series_list[i:i + B]]
        q, _ = pipe.predict_quantiles(ctx, prediction_length=horizon, quantile_levels=list(QS))
        out.extend([np.clip(x.numpy(), 0, None) for x in q])
    return out


def spl(y_true, Q, scale):
    """Scaled pinball (kiểu M5): trung bình pinball 3 phân vị / thang naive trong mẫu."""
    d = y_true[:, None] - Q
    pl = np.maximum(np.array(QS) * d, (np.array(QS) - 1) * d).mean(1)
    return pl / np.maximum(scale, 1e-9)
