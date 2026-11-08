#!/usr/bin/env python3
"""Kiểm tra: ẩn danh HMAC ở bước nạp có làm T9 (ghép sao kê) kém đi không?
Chạy T9 v2 (cấu hình đã chọn trên nguồn) trên cùng dữ liệu tgt3, cửa sổ 2024-07 → 2025-06: một lần với tên/mã gốc, một lần đã ẩn danh
bằng đúng hàm của bước nạp (`agent1_service.ingest.privacy.pseudonymize_row`). Đầu ra: outputs/pilot/privacy_t9_parity.csv
Đây là kiểm tra kỹ thuật (không chọn tham số); tgt3 đã dùng cho T9 nên chỉ so tương đối hai lần chạy.
"""
import json
import secrets
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT  # noqa: E402
from agent1.models.t9_fast import fast_source  # noqa: E402
from agent1_service.ingest.privacy import pseudonymize_row  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from run_t9 import evaluate  # noqa: E402
from t9_guard import hazard_prior, prepare  # noqa: E402
from t9_v2 import links_for  # noqa: E402


def pseudo_frame(df, key):
    return pd.DataFrame([pseudonymize_row(r, key) for r in df.to_dict("records")], index=df.index)


def main():
    v2 = json.loads((OUT / "t9/v2/choice.json").read_text(encoding="utf-8"))
    cfg = dict(cap=v2["cap"], hazard=v2["hazard"], fifo=v2["fifo"])
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    model, label_end = hazard_prior()
    bank, inv, cust, pay = load_observed("tgt3", "2024-07-01", "2025-06-29")
    key = secrets.token_bytes(32)
    rows = []
    for label, (b, i, c) in {"tên/mã gốc": (bank, inv, cust),
                             "đã ẩn danh HMAC": (pseudo_frame(bank, key), pseudo_frame(inv, key), pseudo_frame(cust, key))}.items():
        links = links_for(source, prepare(source, b, i, c, model, label_end), cfg)
        m = evaluate(label, links, b, i, pay)
        m.update(variant=label, auto_txn_coverage=links.txn_id.nunique() / len(b), measurement_version="privacy-t9-parity-v1")
        rows.append(m)
        print(label, {k: round(m[k], 4) for k in ("link_precision", "link_recall", "link_f1", "auto_txn_coverage", "pay_date_MAE_est_days")}, flush=True)
    (OUT / "pilot").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "pilot" / "privacy_t9_parity.csv", index=False)


if __name__ == "__main__":
    main()
