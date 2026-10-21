#!/usr/bin/env python3
"""Bộ đích niêm phong thứ hai `tgt2` (40 công ty). Đăng ký trước: docs/03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md.

Khác `tgt` ở: seed, số công ty (14 -> 40, để có đủ sự kiện thiếu hụt tiền cho G13), cơ cấu ngành lệch nữa,
hành vi khách khác tiền nghiệm theo HƯỚNG KHÁC với tgt (trễ ngắn hơn nhưng nhiều tranh chấp, ghi sổ theo ngày).
Mục đích: kiểm tra luồng ĐÃ ĐÓNG BĂNG đúng một lần. Không dùng để chọn tham số, ngưỡng hay kiến trúc.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.paths import SYNTH  # noqa: E402
from agent1.synth.world import WorldConfig, generate  # noqa: E402


def main():
    base = json.loads((SYNTH / "tgt" / "config.json").read_text(encoding="utf-8"))
    cfg = WorldConfig(
        name="tgt2", seed=20261021, n_firms=40,
        industry_mix={"steel_metals": .10, "textile_clothing": .15, "plastic_rubber": .15,
                      "wholesale": .30, "food_processing": .15, "services": .15},
        posting_mode_p=(0.55, 0.30, 0.15), late_scale=0.9, dispute_scale=2.0,
        n_cust_median=45.0, revenue_median=15e9, memo_invoice_no_p=(1.2, 3.5),
        ontime_shift=base["ontime_shift"], pd_mult=base["pd_mult"], write_xml=0, cod_mult=1.8)
    generate(cfg, verbose=False)
    (SYNTH / "tgt2" / "SEALED.txt").write_text(
        "tgt2 niêm phong 21/10/2026: dùng đúng một lần cho luồng đã đóng băng; cấm chọn tham số trên bộ này.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
