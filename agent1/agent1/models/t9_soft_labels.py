"""Nhãn MỀM cho hoá đơn T9 bỏ sót: phân bổ phần tiền dư của giao dịch đã biết khách theo thứ tự hạn sớm nhất.

Vì sao: G13 cần ĐỘ PHỦ nhãn hơn độ chính xác từng nhãn (docs/03_Evaluation/G13_E2E_T9V2_PREREG.md mục 5-6).
T9 tự động chỉ ghép khi chắc chắn hoá đơn nào; phần còn lại vào hàng chờ và hoá đơn thiếu nhãn. Ở đây: biết KHÁCH (mô hình gán khách rất tự tin)
mà chưa biết HOÁ ĐƠN ⇒ gán FIFO theo hạn, nhãn là ngày giao dịch. Hoá đơn có thể bị hoán đổi trong cùng khách; ngày tiền về của khách vẫn gần đúng.
Nhãn mềm KHÔNG thay liên kết T9 (không vào precision/recall của G15); chỉ bổ sung nhãn ngày trả cho T1.
Chỉ dùng thông tin có tại ngày giao dịch (as-of): hoá đơn đã phát hành ≤ ngày giao dịch.
"""
import numpy as np
import pandas as pd

TOL = 25_000.0


def soft_fifo_labels(links, bank, invoices, assignments, min_confidence=0.5):
    """Trả về Series (index = invoice_id, giá trị = ngày ước lượng) CHỈ cho hoá đơn chưa có nhãn từ liên kết T9 và nay được tất toán bằng phần tiền dư.

    links: liên kết T9 (txn_id, invoice_id, amount, est_pay_date)
    bank: giao dịch (txn_id, firm_id, value_date, amount, direction)
    invoices: (invoice_id, customer_id, issue_date, due_date, amount_gross)
    assignments: (txn_id, customer_id, confidence) — khách mô hình đoán cho từng giao dịch
    """
    paid_by_link = links.groupby("invoice_id").amount.sum() if len(links) else pd.Series(dtype=float)
    used_by_txn = links.groupby("txn_id").amount.sum() if len(links) else pd.Series(dtype=float)
    gross = invoices.set_index("invoice_id").amount_gross
    remaining = (gross - paid_by_link.reindex(gross.index).fillna(0.0)).clip(lower=0)
    labelled_by_link = set(links.invoice_id) if len(links) else set()
    inflow = bank[(bank.get("direction", "in") == "in") & (bank.amount > 0)]
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
                   else np.full(len(g), np.datetime64("NaT"), dtype="datetime64[ns]")) for k, g in by_customer.items()}
    for txn in inflow.sort_values(["value_date", "txn_id"]).itertuples(index=False):
        if txn.txn_id not in a.index:
            continue
        row = a.loc[txn.txn_id]
        if float(row[conf_col]) < min_confidence:
            continue
        key = (txn.firm_id, row["customer_id"])
        if key not in state:
            continue
        leftover = float(txn.amount) - float(used_by_txn.get(txn.txn_id, 0.0))
        if leftover <= TOL:
            continue
        rem, date = state[key], np.datetime64(txn.value_date, "ns")
        for i in np.flatnonzero((issued[key] <= date) & (rem > TOL) & ~(cleared[key] < date)):
            take = min(rem[i], leftover)
            rem[i] -= take; leftover -= take
            if rem[i] <= TOL and ids[key][i] not in labelled_by_link and ids[key][i] not in out:
                out[ids[key][i]] = pd.Timestamp(txn.value_date)
            if leftover <= TOL:
                break
    return pd.Series(out, dtype="datetime64[ns]")
