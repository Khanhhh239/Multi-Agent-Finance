"""Dải số dư công bố = copula-t + ACI (GO_NO_GO_SYNTHETIC_ONLY.md mục 4b).

Copula-t gốc hẹp (cov80 0,62–0,72 trên tgt/tgt2); ACI cập nhật mức alpha theo từng chân trời bằng số dư thật đã lộ diện
và đưa độ phủ về 0,75–0,77. Trạng thái phải được giữ qua các lần dự báo của cùng doanh nghiệp (store kind 'aci_state').
Chỉ dùng số dư doanh nghiệp tự khai ở các lần dự báo trước — không nhìn tương lai.
"""
import numpy as np
import pandas as pd

from agent1.models.t6_cash import ACI, K

READY_WEEKS = 8          # cần >= 8 tuần lộ diện trước khi tin độ phủ (bậc 0 "bóng")
MATCH_DAYS = 3           # số dư quan sát trong [mốc, mốc + 3 ngày] được dùng làm số dư thật của tuần k
KEEP_DAYS = 130


def empty_state():
    return dict(a=[0.2] * K, pending=[], balances={}, matured_weeks=[])


def update(state, cutoff, balance):
    """Ghi số dư quan sát tại cutoff, cập nhật ACI bằng các dự báo cũ đã tới hạn. Trả về (state mới, ACI)."""
    state = dict(empty_state(), **(state or {}))
    T = pd.Timestamp(cutoff).normalize()
    balances = {pd.Timestamp(d): float(v) for d, v in state["balances"].items()}
    balances[T] = float(balance)
    aci = ACI(); aci.a = np.asarray(state["a"], float)
    still, matured = [], set(state["matured_weeks"])
    for made, k, lo, hi in state["pending"]:
        target = pd.Timestamp(made) + pd.Timedelta(days=7 * (int(k) + 1))
        seen = sorted(d for d in balances if target <= d <= target + pd.Timedelta(days=MATCH_DAYS))
        if seen:
            y = balances[seen[0]]
            aci.update(int(k), not (lo <= y <= hi))
            matured.add(str(pd.Timestamp(made).to_period("W-MON").start_time.date()))
        elif target + pd.Timedelta(days=MATCH_DAYS) >= T:
            still.append([made, k, lo, hi])        # chưa tới hạn hoặc còn chờ quan sát
    keep = T - pd.Timedelta(days=KEEP_DAYS)
    state.update(a=aci.a.tolist(), pending=still, matured_weeks=sorted(matured),
                 balances={str(d.date()): v for d, v in balances.items() if d >= keep})
    return state, aci


def band(state, aci, cutoff, samples):
    """Dải P10/P50/P90 theo ACI; ghi các khoảng mới vào pending để cập nhật ở lần sau."""
    T = str(pd.Timestamp(cutoff).normalize().date())
    rows = []
    for k in range(K):
        lo, hi = aci.interval(samples[:, k], k)
        rows.append(dict(week=k + 1, P10=float(lo), P50=float(np.median(samples[:, k])), P90=float(hi)))
        state["pending"].append([T, k, float(lo), float(hi)])
    weeks = len(state["matured_weeks"])
    meta = dict(band_method="copula-t+ACI", aci_matured_weeks=weeks, aci_ready=weeks >= READY_WEEKS,
                band_note=None if weeks >= READY_WEEKS else
                f"Độ phủ dải chưa kiểm chứng: mới có {weeks}/{READY_WEEKS} tuần số dư đã lộ diện để hiệu chỉnh")
    return rows, meta
