"""T7 — phát hiện điểm gãy hành vi trả tiền (trực tuyến) trên phần dư chuẩn hoá của số ngày trễ.

Phần dư z_t = (trễ_t - kỳ vọng theo lịch sử khách) / độ phân tán bền (MAD), tính tuần tự không nhìn tương lai.
Bộ phát hiện: CUSUM một phía (Page 1954), Page–Hinkley, BOCPD (Adams & MacKay 2007, Gauss phương sai biết),
mốc ngây thơ (trung bình 5 phần dư gần nhất > ngưỡng ngày).
"""
from __future__ import annotations

import numpy as np


def residual_stream(delays: np.ndarray, warmup=8, floor=3.0, method="pit", window=40):
    """Phần dư tuần tự, chỉ dùng quan sát TRƯỚC t.
    method='pit': u = hạng thực nghiệm (làm trơn) của trễ_t trong cửa sổ quá khứ, z = Phi^-1(u) — bền với phân
    phối hai đỉnh (đúng hạn / trễ) và đuôi dài; method='mad': (trễ - trung vị)/MAD (bản cũ, để đối chứng)."""
    from scipy.stats import norm
    z = np.full(len(delays), np.nan)
    raw = np.full(len(delays), np.nan)
    for t in range(warmup, len(delays)):
        past = delays[max(0, t - window):t]
        med = np.median(past)
        raw[t] = delays[t] - med
        if method == "pit":
            u = (np.sum(past < delays[t]) + 0.5 * np.sum(past == delays[t]) + 0.5) / (len(past) + 1)
            z[t] = norm.ppf(u)
        else:
            mad = 1.4826 * np.median(np.abs(past - med))
            z[t] = raw[t] / max(mad, floor)
    return z, raw


def cusum(z, k=0.5, h=5.0):
    s, alarms = 0.0, []
    for t, v in enumerate(z):
        if np.isnan(v):
            continue
        s = max(0.0, s + min(v, 6.0) - k)
        if s > h:
            alarms.append(t)
            s = 0.0
    return alarms


def page_hinkley(z, delta=0.5, lam=6.0, alpha=0.95):
    mean, m, mmin, n, alarms = 0.0, 0.0, 0.0, 0, []
    for t, v in enumerate(z):
        if np.isnan(v):
            continue
        v = min(v, 6.0)
        n += 1
        mean = mean + (v - mean) / n if n < 30 else alpha * mean + (1 - alpha) * v
        m += v - mean - delta
        mmin = min(mmin, m)
        if m - mmin > lam:
            alarms.append(t)
            mean, m, mmin, n = 0.0, 0.0, 0.0, 0
    return alarms


def bocpd(z, hazard=1 / 60, mu0=0.0, kappa0=1.0, sigma=1.0, thr=0.5, short=3, rmax=200):
    """BOCPD Gauss (phương sai biết = 1 sau chuẩn hoá), tiền nghiệm liên hợp cho trung bình.
    Báo động khi khối xác suất của run-length <= `short` vượt `thr` (sau khi đã ổn định)."""
    R = np.array([1.0])
    mu = np.array([mu0])
    kap = np.array([kappa0])
    alarms, last = [], -10
    for t, v in enumerate(z):
        if np.isnan(v):
            continue
        v = float(np.clip(v, -6, 6))
        var = sigma ** 2 * (1 + 1 / kap)
        pred = np.exp(-0.5 * (v - mu) ** 2 / var) / np.sqrt(2 * np.pi * var)
        growth = R * pred * (1 - hazard)
        cp = (R * pred * hazard).sum()
        R = np.r_[cp, growth]
        R = R / R.sum()
        mu = np.r_[mu0, (kap * mu + v) / (kap + 1)]
        kap = np.r_[kappa0, kap + 1]
        if len(R) > rmax:
            R, mu, kap = R[:rmax], mu[:rmax], kap[:rmax]
            R = R / R.sum()
        # chỉ báo động khi đoạn mới có trung bình dương (chậm hơn), tránh báo khi khách trả nhanh lên
        if t - last > 5 and R[1:short + 1].sum() > thr and mu[1:short + 1].mean() > 0.8:
            alarms.append(t)
            last = t
    return alarms


def naive(raw, win=5, thr_days=10.0):
    alarms, last = [], -10
    for t in range(win, len(raw)):
        w = raw[t - win + 1:t + 1]
        if np.isnan(w).any():
            continue
        if w.mean() > thr_days and t - last > win:
            alarms.append(t)
            last = t
    return alarms


GRIDS = {  # tham số ngưỡng được chọn trên miền nguồn theo báo giả mục tiêu
    "CUSUM": [dict(k=k, h=h) for k in (0.25, 0.5, 0.75) for h in (3, 4, 5, 6, 8, 10)],
    "Page-Hinkley": [dict(delta=d, lam=l) for d in (0.1, 0.25, 0.5) for l in (3, 4, 6, 8, 10, 14)],
    "BOCPD": [dict(hazard=hz, thr=th) for hz in (1 / 30, 1 / 60, 1 / 120) for th in (0.3, 0.5, 0.7, 0.85)],
    "Naive mean5>Xd": [dict(thr_days=x) for x in (5, 8, 10, 15, 20, 30)],
}


def run_detector(name, z, raw, **kw):
    if name == "CUSUM":
        return cusum(z, **kw)
    if name == "Page-Hinkley":
        return page_hinkley(z, **kw)
    if name == "BOCPD":
        return bocpd(z, **kw)
    return naive(raw, **kw)
