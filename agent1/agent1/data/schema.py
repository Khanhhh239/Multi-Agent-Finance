"""T0 — lược đồ chuẩn + cổng chất lượng cho hoá đơn đầu ra (từ XML hoá đơn điện tử hoặc sổ ERP).

Kiểm tra (không cần học máy): trường bắt buộc, MST hợp lệ (chữ số kiểm tra), ngày hợp lý (hạn >= ngày lập,
không ở tương lai), cộng tiền (trước thuế + thuế = tổng, dung sai 1.000đ), thuế suất hợp lệ, trùng khoá
(MST bán + ký hiệu + số), tiền tệ. Trả về bảng lỗi theo dòng để báo cáo tỷ lệ khớp sổ (N6).
"""
from __future__ import annotations

import re

import pandas as pd

from ..synth.names import valid_mst

REQUIRED = ["seller_mst", "buyer_mst", "symbol", "invoice_no", "issue_date", "amount_net", "vat", "amount_gross", "currency"]
VALID_VAT = {0.0, 0.05, 0.08, 0.10}
VALID_VAT_LABELS = {"0%", "5%", "8%", "10%", "KCT", "KKKNT"}
_KHAC_VAT_RE = re.compile(r"^KHAC\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*%?$", re.IGNORECASE)


def _valid_single_vat_label(token: str) -> bool:
    s = token.strip().upper().replace(" ", "")
    if not s:
        return True
    if s in VALID_VAT_LABELS:
        return True
    if s in {"KHONGCHIUTHUE", "KHONGKEKHAI", "KHAC:KCT", "KHAC:KKKNT"}:
        return True
    khac = _KHAC_VAT_RE.fullmatch(s)
    if khac:
        pct = float(khac.group(1).replace(",", "."))
        return 0.0 <= pct <= 10.0
    if s.endswith("%"):
        try:
            pct = float(s[:-1].replace(",", "."))
        except ValueError:
            return False
        return round(pct / 100.0, 4) in VALID_VAT
    try:
        num = float(s.replace(",", "."))
    except ValueError:
        return False
    if num in {0.0, 5.0, 8.0, 10.0}:
        return True
    return round(num, 4) in VALID_VAT


def _valid_vat_labels(value) -> bool:
    if value is None or isinstance(value, bool):
        return value is None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return True
        return round(float(value), 4) in VALID_VAT
    if isinstance(value, (list, tuple, set)):
        return all(_valid_single_vat_label(str(item)) for item in value)
    if pd.isna(value):
        return True
    text = str(value).strip()
    if not text:
        return True
    return all(_valid_single_vat_label(part) for part in re.split(r"[;,|]", text) if part.strip())


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
    net = pd.to_numeric(d["amount_net"], errors="coerce")
    vat = pd.to_numeric(d["vat"], errors="coerce")
    gross = pd.to_numeric(d["amount_gross"], errors="coerce")
    errs["sum_mismatch"] = net.isna() | vat.isna() | gross.isna() | ((net + vat - gross).abs() > 1000)
    # Hỗ trợ hoá đơn nhiều mức thuế suất (0%, 5%, 8% theo NĐ 174/2024 & NĐ 180/2024, 10%, KCT, KKKNT):
    # tổng VAT hợp lệ thuộc bao lồi [0%, 10%] của tổng tiền trước thuế (cộng dung sai làm tròn dòng).
    vat_tol = (0.005 * net.abs()).clip(lower=0.02, upper=1000.0)
    bad_vat = net.isna() | vat.isna() | (net <= 0) | (vat < -1e-9) | (vat > 0.10 * net + vat_tol)
    if "vat_rates" in d.columns:
        bad_vat = bad_vat | ~d["vat_rates"].map(_valid_vat_labels)
    if "vat_rate" in d.columns:
        bad_vat = bad_vat | ~d["vat_rate"].map(_valid_vat_labels)
    errs["bad_vat_rate"] = bad_vat
    errs["negative_amount"] = gross.isna() | (gross <= 0)
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
            m = str(d.at[i, "buyer_mst"]).strip()
            digits = "".join(ch for ch in m if ch.isdigit())
            if len(digits) == 12:
                d.at[i, "buyer_mst"] = "000" + digits[3:]
            elif len(digits) >= 10:
                d.at[i, "buyer_mst"] = digits[:9] + str((int(digits[9]) + 1) % 10) + m[10:]
            else:
                d.at[i, "buyer_mst"] = "0000000000"
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
