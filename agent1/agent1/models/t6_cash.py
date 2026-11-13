"""T6 — tổng hợp Monte Carlo số dư tiền 13 tuần + sốc chung đuôi dày + hiệu chỉnh conformal thích ứng (ACI).

Mỗi đường mô phỏng:
  * thu từ hoá đơn đang mở: tuần trả rút từ phân phối T1 (DH-GBM), tương quan giữa các hoá đơn qua copula
    Student-t một nhân tố (sốc thanh khoản chung — Atradius: 47% trễ do thanh khoản của khách);
  * doanh thu mới (T4, phân vị) -> thu theo nhân lag (kernel) học từ lịch sử thu tiền của chính công ty;
  * chi biết trước (T5: lương, BHXH, thuế, thuê, vay, NCC đã nhận HĐ) + chi bất thường (Poisson phức hợp học
    từ lịch sử capex);
  * số dư đầu kỳ thật tại điểm cắt.
ACI (Gibbs & Candès 2021): mức phân vị dùng để cắt khoảng từ mẫu MC được cập nhật trực tuyến theo sai số
đã lộ diện (trễ k tuần), gộp theo chân trời — bảo đảm độ phủ dài hạn dưới trôi phân phối.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm, t as student_t

K = 13
DEFAULT_NU = 4  # Giả định hiện hành; chưa ước lượng từ SEC.


def collection_kernel(inv_hist: pd.DataFrame, T, label_col="paid_date_true", weeks=K + 4):
    """P(thu ở tuần d sau tuần lập) từ HĐ lập trong 365 ngày trước T và đã quan sát được tới T."""
    T = pd.Timestamp(T)
    h = inv_hist[(inv_hist["issue_date"] >= T - pd.Timedelta(days=365)) & (inv_hist["issue_date"] <= T - pd.Timedelta(days=7 * weeks))]
    if len(h) < 30:
        k = np.zeros(weeks)
        k[6] = 1.0
        return k
    known_date = h[label_col].where(h[label_col] <= T)
    d = ((known_date - h["issue_date"]).dt.days // 7).fillna(999).clip(upper=999).values
    w = h["amount_gross"].values
    k = np.array([w[d == j].sum() for j in range(weeks)]) / w.sum()
    return k


def simulate(open_df, P, B0, known_out, rev_q, kernel, capex_rate, capex_sizes, n=1000, rho=0.15, nu=DEFAULT_NU, seed=0,
             rev_corr=0.7, rho_customer=0.,
             payment_shift=None, force_week=None,draw_cap=None,draw_target=None,draw_weeks=None):
    """Trả về mảng mẫu số dư cuối tuần (n x K) và dòng ròng (n x K)."""
    # Dòng RNG riêng giữ CRN giữa các kịch bản dù số bước mô phỏng thay đổi.
    streams = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(4)]
    rng, rev_rng, _, cap_rng = streams
    amt = open_df["amount_open"].values
    m = len(amt)
    P = np.asarray(P, float)
    known_out = np.asarray(known_out, float)
    if P.shape != (m, K) or not np.isfinite(P).all() or (P < 0).any() or (P.sum(1) > 1 + 1e-6).any():
        raise ValueError('PMF không hợp lệ')
    if known_out.shape != (K,) or not np.isfinite(known_out).all():
        raise ValueError('known_out phải có 13 tuần hữu hạn')
    if not 0 <= rho <= 1 or not 0 <= rho_customer <= 1 - rho or nu <= 2:
        raise ValueError('Tham số copula không hợp lệ')
    if not np.isfinite(amt).all() or (amt < 0).any() or n < 1:
        raise ValueError('Tiền mở hoặc số đường không hợp lệ')
    g = rng.standard_normal(n)
    t_scale = np.sqrt(rng.chisquare(nu, n) / nu)
    # --- thu từ HĐ mở: copula t một nhân tố
    if m:
        F = np.cumsum(P, axis=1)                                     # CDF tuần 1..K (phần dư = sau K)
        e = rng.standard_normal((n, m))
        latent = np.sqrt(rho) * g[:, None] + np.sqrt(1 - rho - rho_customer) * e
        if rho_customer:
            codes, unique = pd.factorize(open_df['customer_id'])
            latent += np.sqrt(rho_customer) * rng.standard_normal((n, len(unique)))[:, codes]
        # t-CDF của biến Student-t mới cho biên Uniform(0,1).
        # Mốc rho=0 dùng độc lập thực sự, không chia chung biến chi-square.
        u = student_t.cdf(latent / t_scale[:, None], nu) if rho + rho_customer > 0 else norm.cdf(e)
        wk = np.empty((n, m), dtype=np.int16)
        for j in range(m):
            wk[:, j] = np.searchsorted(F[j], u[:, j], side="left")    # 0..K-1, K = ngoài chân trời
        if payment_shift is not None:
            shift = np.broadcast_to(np.asarray(payment_shift, int), (m,))
            wk = np.where(wk < K, np.clip(wk + shift[None, :], 0, K), K)
        if force_week is not None:
            forced = np.broadcast_to(np.asarray(force_week, int), (m,))
            wk = np.where(forced[None, :] >= 0, forced[None, :], wk)
        inflow = np.zeros((n, K))
        for k in range(K):
            inflow[:, k] = ((wk == k) * amt[None, :]).sum(1)
    else:
        inflow = np.zeros((n, K))
    # --- doanh thu mới (lập HĐ ở tuần j) -> thu theo kernel
    if rev_q is not None:
        z = rev_corr * (-g)[:, None] + np.sqrt(1 - rev_corr ** 2) * rev_rng.standard_normal((n, K))
        v = norm.cdf(z)
        q10, q50, q90 = rev_q[:, 0], rev_q[:, 1], rev_q[:, 2]
        R = np.where(v < 0.5, q10 + (q50 - q10) * (v - 0.1) / 0.4, q50 + (q90 - q50) * (v - 0.5) / 0.4)
        R = np.clip(R, 0, None)
        for j in range(K):
            for d in range(K - j):
                inflow[:, j + d] += R[:, j] * kernel[d] if d < len(kernel) else 0
    # --- chi
    out = np.tile(known_out[None, :], (n, 1))
    if capex_rate > 0 and len(capex_sizes):
        cnt = cap_rng.poisson(capex_rate, (n, K))
        for k in range(K):
            mask = cnt[:, k] > 0
            if mask.any():
                out[mask, k] += np.array([cap_rng.choice(capex_sizes, c).sum() for c in cnt[mask, k]])
    net = inflow - out
    if draw_cap is not None and draw_target is not None and draw_weeks is not None:
        if draw_target<0 or draw_cap<draw_target:
            raise ValueError('Ngưỡng rút vốn không hợp lệ')
        mask=np.asarray(draw_weeks,bool)
        if mask.shape!=(K,):raise ValueError('draw_weeks cần 13 cờ')
        bal=np.empty((n,K));running=np.full(n,float(B0))
        for k in range(K):
            running=running+net[:,k]
            draw=np.maximum(running-draw_target,0.) if mask[k] else np.zeros(n)
            draw=np.where(running>draw_cap,draw,0.)
            net[:,k]-=draw;running-=draw;bal[:,k]=running
    else:
        bal = B0 + np.cumsum(net, axis=1)
    return bal, net


class ACI:
    """Conformal thích ứng gộp theo chân trời; alpha mục tiêu 0.2 (khoảng 80%)."""

    def __init__(self, alpha=0.2, gamma=0.01):
        self.alpha, self.gamma = alpha, gamma
        self.a = np.full(K, alpha)

    def interval(self, samples, k):
        a = float(np.clip(self.a[k], 0.005, 0.6))
        return np.quantile(samples, a / 2), np.quantile(samples, 1 - a / 2)

    def update(self, k, miss):
        self.a[k] = np.clip(self.a[k] + self.gamma * (self.alpha - float(miss)), .005, .6)
