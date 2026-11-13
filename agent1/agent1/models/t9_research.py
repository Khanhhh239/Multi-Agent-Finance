"""T9 research: review queues and soft FIFO labels for unallocated receipts.

Mô phỏng hàng chờ duyệt của kế toán cho T9 (chiến lược mũi B1, docs/05_Coding_Agent_Plan/CHIEN_LUOC_TIEP_THEO_2026-10-24.md).

Giao dịch vào hàng chờ = tiền vào mà T9 tự động chưa phân bổ hết (còn dư > TOL).
Mỗi tuần, mỗi doanh nghiệp, kế toán duyệt tối đa `per_week` giao dịch trong số đang chờ (kể cả tồn từ tuần trước),
theo thứ tự ưu tiên của chính sách. Duyệt một giao dịch = biết đúng giao dịch đó trả những hoá đơn nào (lấy từ bảng
thanh toán thật — người duyệt hoàn hảo, nên kết quả là CẬN TRÊN cho người thật). Liên kết T9 của giao dịch đã duyệt được thay
bằng liên kết đúng. Giao dịch không phải thanh toán của khách (lãi, nội bộ...) vẫn tốn một lượt duyệt.

Chỉ dùng thông tin có tại thời điểm duyệt: giao dịch chỉ vào hàng chờ từ tuần nó xuất hiện.

Nhãn MỀM cho hoá đơn T9 bỏ sót: phân bổ phần tiền dư của giao dịch đã biết khách theo thứ tự hạn sớm nhất.

Vì sao: G13 cần ĐỘ PHỦ nhãn hơn độ chính xác từng nhãn (docs/03_Evaluation/G13_E2E_T9V2_PREREG.md mục 5-6).
T9 tự động chỉ ghép khi chắc chắn hoá đơn nào; phần còn lại vào hàng chờ và hoá đơn thiếu nhãn. Ở đây: biết KHÁCH (mô hình gán khách rất tự tin)
mà chưa biết HOÁ ĐƠN ⇒ gán FIFO theo hạn, nhãn là ngày giao dịch. Hoá đơn có thể bị hoán đổi trong cùng khách; ngày tiền về của khách vẫn gần đúng.
Nhãn mềm KHÔNG thay liên kết T9 (không vào precision/recall của G15); chỉ bổ sung nhãn ngày trả cho T1.
Chỉ dùng thông tin có tại ngày giao dịch (as-of): hoá đơn đã phát hành ≤ ngày giao dịch.
"""
import numpy as np
import pandas as pd

from .t9_recon import TOL

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


def soft_fifo_labels(links, bank, invoices, assignments, min_confidence=0.5):
    """Trả về Series (index = invoice_id, giá trị = ngày ước lượng) CHỈ cho hoá đơn chưa có nhãn từ liên kết T9 và nay được tất toán bằng phần tiền dư.

    links: liên kết T9 (txn_id, invoice_id, amount, est_pay_date)
    bank: giao dịch (txn_id, firm_id, value_date, amount, direction)
    invoices: (invoice_id, customer_id, issue_date, due_date, amount_gross)
    assignments: (txn_id, customer_id, confidence) — khách mô hình đoán cho từng giao dịch
    """
    paid_by_link = links.groupby("invoice_id").amount.sum() if len(links) else pd.Series(dtype=float)
    gross = invoices.set_index("invoice_id").amount_gross
    remaining = (gross - paid_by_link.reindex(gross.index).fillna(0.0)).clip(lower=0)
    labelled_by_link = set(links.invoice_id) if len(links) else set()
    inflow = queued_transactions(links, bank)
    a = assignments.set_index("txn_id") if len(assignments) else pd.DataFrame(columns=["customer_id", "confidence"])
    conf_col = "confidence" if "confidence" in a else "p"
    out = {}
    inv = invoices.assign(_rem=invoices.invoice_id.map(remaining).to_numpy()).sort_values(["due_date", "invoice_id"])
    by_customer = {k: g for k, g in inv.groupby(["firm_id", "customer_id"])}
    state = {k: g["_rem"].to_numpy().copy() for k, g in by_customer.items()}
    ids = {k: g["invoice_id"].to_numpy() for k, g in by_customer.items()}
    issued = {k: g["issue_date"].to_numpy(dtype="datetime64[ns]") for k, g in by_customer.items()}
    # Sổ cái của DN ghi tất toán sớm hơn ngày giao dịch ⇒ hoá đơn đã đóng, không nhận tiền dư (cùng quy tắc as-of của T9 chính).
    cleared = {k: (g["ledger_clear_date"].to_numpy(dtype="datetime64[ns]") if "ledger_clear_date" in g
                   else np.full(len(g), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")) for k, g in by_customer.items()}
    for txn in inflow.sort_values(["value_date", "txn_id"]).itertuples(index=False):
        if txn.txn_id not in a.index:
            continue
        row = a.loc[txn.txn_id]
        if float(row[conf_col]) < min_confidence:
            continue
        key = (txn.firm_id, row["customer_id"])
        if key not in state:
            continue
        leftover = float(txn.leftover)
        rem, date = state[key], np.datetime64(txn.value_date, "ns")
        for i in np.flatnonzero((issued[key] <= date) & (rem > TOL) & ~(cleared[key] < date)):
            take = min(rem[i], leftover)
            rem[i] -= take; leftover -= take
            if rem[i] <= TOL and ids[key][i] not in labelled_by_link and ids[key][i] not in out:
                out[ids[key][i]] = pd.Timestamp(txn.value_date)
            if leftover <= TOL:
                break
    return pd.Series(out, dtype="datetime64[ns]")
