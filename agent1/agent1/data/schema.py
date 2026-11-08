"""T0 — lược đồ chuẩn + cổng chất lượng cho hoá đơn đầu ra (từ XML hoá đơn điện tử hoặc sổ ERP).

Kiểm tra (không cần học máy): trường bắt buộc, MST hợp lệ (chữ số kiểm tra), ngày hợp lý (hạn >= ngày lập,
không ở tương lai), cộng tiền (trước thuế + thuế = tổng, dung sai 1.000đ), thuế suất hợp lệ, trùng khoá
(MST bán + ký hiệu + số), tiền tệ. Trả về bảng lỗi theo dòng để báo cáo tỷ lệ khớp sổ (N6).
"""
from __future__ import annotations

import pandas as pd

from ..synth.names import valid_mst

REQUIRED = ["seller_mst", "buyer_mst", "symbol", "invoice_no", "issue_date", "amount_net", "vat", "amount_gross", "currency"]
VALID_VAT = {0.0, 0.05, 0.08, 0.10}


def quality_gate(df: pd.DataFrame, today=None) -> pd.DataFrame:
    today = pd.Timestamp(today or pd.Timestamp.today().normalize())
    d = df.copy()
    d["issue_date"] = pd.to_datetime(d["issue_date"], errors="coerce")
    d["due_date"] = pd.to_datetime(d.get("due_date"), errors="coerce")
    errs = pd.DataFrame(index=d.index)
    for c in REQUIRED:
        errs[f"missing_{c}"] = d[c].isna() | (d[c].astype(str).str.strip() == "")
    errs["bad_seller_mst"] = ~d["seller_mst"].astype(str).map(valid_mst)
    errs["bad_buyer_mst"] = ~d["buyer_mst"].astype(str).map(valid_mst)
    errs["bad_issue_date"] = d["issue_date"].isna() | (d["issue_date"] > today) | (d["issue_date"] < "2010-01-01")
    errs["due_before_issue"] = d["due_date"].notna() & (d["due_date"] < d["issue_date"])
    errs["sum_mismatch"] = (d["amount_net"] + d["vat"] - d["amount_gross"]).abs() > 1000
    rate = (d["vat"] / d["amount_net"]).round(2)
    errs["bad_vat_rate"] = ~rate.isin(VALID_VAT)
    errs["negative_amount"] = d["amount_gross"] <= 0
    errs["duplicate_key"] = d.duplicated(["seller_mst", "symbol", "invoice_no"], keep="first")
    errs["bad_currency"] = ~d["currency"].isin(["VND", "USD", "EUR", "JPY", "CNY"])
    errs["any_error"] = errs.any(axis=1)
    return errs


def inject_errors(df: pd.DataFrame, rate=0.05, seed=0) -> tuple[pd.DataFrame, pd.Series]:
    """Chèn lỗi có nhãn (để đo độ nhạy của cổng chất lượng)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    d = df.copy().reset_index(drop=True)
    kinds = rng.choice(["mst", "date", "sum", "dup", "missing", "due"], len(d))
    hit = rng.random(len(d)) < rate
    truth = pd.Series(hit, index=d.index)
    for i in np.nonzero(hit)[0]:
        k = kinds[i]
        if k == "mst":
            m = str(d.at[i, "buyer_mst"])
            d.at[i, "buyer_mst"] = m[:9] + str((int(m[9]) + 1) % 10)
        elif k == "date":
            d.at[i, "issue_date"] = "2099-01-01"
        elif k == "sum":
            d.at[i, "vat"] = d.at[i, "vat"] + 50_000
        elif k == "dup" and i > 0:
            for c in ("seller_mst", "symbol", "invoice_no"):
                d.at[i, c] = d.at[i - 1, c]
        elif k == "missing":
            d.at[i, "buyer_mst"] = None
        else:
            d.at[i, "due_date"] = (pd.Timestamp(d.at[i, "issue_date"]) - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    return d, truth
