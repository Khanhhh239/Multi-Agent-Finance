"""Mô phỏng hàng chờ duyệt của kế toán cho T9 (chiến lược mũi B1, docs/05_Coding_Agent_Plan/CHIEN_LUOC_TIEP_THEO_2026-10-24.md).

Giao dịch vào hàng chờ = tiền vào mà T9 tự động chưa phân bổ hết (còn dư > TOL).
Mỗi tuần, mỗi doanh nghiệp, kế toán duyệt tối đa `per_week` giao dịch trong số đang chờ (kể cả tồn từ tuần trước),
theo thứ tự ưu tiên của chính sách. Duyệt một giao dịch = biết đúng giao dịch đó trả những hoá đơn nào (lấy từ bảng
thanh toán thật — người duyệt hoàn hảo, nên kết quả là CẬN TRÊN cho người thật). Liên kết T9 của giao dịch đã duyệt được thay
bằng liên kết đúng. Giao dịch không phải thanh toán của khách (lãi, nội bộ...) vẫn tốn một lượt duyệt.

Chỉ dùng thông tin có tại thời điểm duyệt: giao dịch chỉ vào hàng chờ từ tuần nó xuất hiện.
"""
import numpy as np
import pandas as pd

TOL = 25_000.0
POLICIES = ("random", "leftover")


def queued_transactions(links, bank):
    inflow = bank[(bank.get("direction", "in") == "in") & (bank.amount > 0)].copy()
    used = links.groupby("txn_id").amount.sum() if len(links) else pd.Series(dtype=float)
    inflow["leftover"] = inflow.amount - inflow.txn_id.map(used).fillna(0.0)
    return inflow[inflow.leftover > TOL]


def simulate_review(links, bank, truth, per_week, policy="leftover", seed=7):
    """Trả về (liên kết sau duyệt, thống kê). truth: bảng thanh toán thật (txn_id, invoice_id, amount, pay_date_true)."""
    if policy not in POLICIES:
        raise ValueError(f"policy phải thuộc {POLICIES}")
    q = queued_transactions(links, bank)
    if per_week <= 0 or q.empty:
        return links.copy(), dict(n_queued=len(q), n_reviewed=0, share_reviewed=0.0)
    rng = np.random.default_rng(seed)
    q = q.assign(week=q.value_date.dt.to_period("W-SUN").dt.start_time,
                 score=rng.random(len(q)) if policy == "random" else q.leftover)
    reviewed = []
    for _, g in q.groupby("firm_id"):
        pending = pd.DataFrame(columns=g.columns)
        for _, wk in g.sort_values("week").groupby("week", sort=True):
            pending = pd.concat([pending, wk]) if len(pending) else wk
            take = pending.nlargest(per_week, "score")
            reviewed.extend(take.txn_id.tolist())
            pending = pending.drop(take.index)
    reviewed = set(reviewed)
    true_links = truth[truth.txn_id.isin(reviewed)].rename(columns={"pay_date_true": "est_pay_date"})
    true_links = true_links.assign(kind="reviewed", method="human_review", confidence=1.0)
    keep = links[~links.txn_id.isin(reviewed)]
    out = pd.concat([keep, true_links[[c for c in links.columns if c in true_links.columns]]], ignore_index=True)
    return out, dict(n_queued=len(q), n_reviewed=len(reviewed), share_reviewed=len(reviewed) / max(len(q), 1))
