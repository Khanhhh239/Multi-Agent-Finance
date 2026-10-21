#!/usr/bin/env python3
"""G13 bước 1 — backtest T6 trên NGUỒN (src) để chọn chính sách cảnh báo mà không nhìn tgt.

Cùng pipeline với E2E (`run_t6.main`): T1 học trên src trước O (kiểm duyệt tại O), tinh chỉnh 12 tháng, mô phỏng copula-t,
52 tuần kiểm tra bắt đầu từ O. Nhãn = số dư thật của src (oracle). Ghi vào outputs/g13/src_backtest/.
Lưu ý: src là miền trong-phân-phối với mô hình nguồn ⇒ xác suất trên src có thể hiệu chỉnh tốt hơn tgt; đây chính là
câu hỏi chuyển miền mà bước 3 (áp chính sách đóng băng lên tgt) kiểm tra.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from agent1.paths import OUT  # noqa: E402
import run_t6  # noqa: E402

if __name__ == "__main__":
    run_t6.main(target_world="src", evaluation_world="src", result_dir=OUT / "g13" / "src_backtest",
                source_budget=40000, n_weeks=52, label_mode="oracle_bank")
