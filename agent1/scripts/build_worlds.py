#!/usr/bin/env python3
"""T12 — hiệu chỉnh máy phát theo Atradius VN 2025 rồi dựng các thế giới cho domain adaptation.

Thế giới:
  calib   : chỉ để hiệu chỉnh (seed riêng, không dùng train/test)
  src     : miền NGUỒN — 40 công ty, tiền nghiệm hiệu chỉnh (huấn luyện / tiền huấn luyện)
  tgt     : miền ĐÍCH "niêm phong" — 14 công ty SME nhỏ hơn, hành vi lệch khỏi tiền nghiệm (seed riêng,
            ghi sổ theo lô nhiều hơn, trễ dài hơn, nhiều tranh chấp hơn, ít ghi số HĐ trong nội dung CK).
            Mô phỏng "doanh nghiệp VN thật khác giả định" -> chỉ dùng lịch sử ngắn để thích nghi, đánh giá ở giai đoạn sau.
  sens_uk, sens_coface : kiểm thử chịu nhiễu với giả định đuôi trễ khác (Phần 7 mục 4.5)

  python scripts/build_worlds.py --calibrate --worlds src,tgt,sens_uk,sens_coface
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, RAW  # noqa: E402
from agent1.synth.world import WorldConfig, generate, INDUSTRY  # noqa: E402
from agent1.synth.fidelity import report  # noqa: E402

CAL_FILE = SYNTH / "calibration_fit.json"
UNIFORM = {k: 1.0 for k in INDUSTRY}


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return np.log(p / (1 - p))


def calibrate(iters=5, n_firms=24):
    shift = {k: 0.6 for k in INDUSTRY}
    pdm = {k: 1.0 for k in INDUSTRY}
    hist = []
    for it in range(iters):
        cfg = WorldConfig(name="calib", seed=101 + it, n_firms=n_firms, industry_mix=UNIFORM, ontime_shift=dict(shift),
                          pd_mult=dict(pdm), write_xml=0)
        generate(cfg, verbose=False)
        r = report(SYNTH / "calib")["A_calibration_targets"]["achieved"]
        row = {"iter": it}
        for ind, I in INDUSTRY.items():
            if ind not in r:
                continue
            tgt_bad = I["bad"]
            tgt_on = 1 - I["overdue"] - tgt_bad
            a = r[ind]
            shift[ind] += 0.8 * (logit(tgt_on) - logit(a["ontime"]))
            pdm[ind] = float(np.clip(pdm[ind] * (tgt_bad / max(a["bad_debt"], 1e-3)) ** 0.8, 0.1, 10))
            row[ind] = dict(ontime=round(a["ontime"], 3), target_ontime=round(tgt_on, 3), bad=round(a["bad_debt"], 4),
                            target_bad=tgt_bad)
        hist.append(row)
        print(json.dumps(row), flush=True)
    CAL_FILE.write_text(json.dumps({"ontime_shift": shift, "pd_mult": pdm, "history": hist}, indent=2), encoding="utf-8")
    return shift, pdm


def world_cfgs(shift, pdm):
    base = dict(ontime_shift=shift, pd_mult=pdm)
    return {
        "src": WorldConfig(name="src", seed=1, n_firms=40, **base),
        "tgt": WorldConfig(name="tgt", seed=999, n_firms=14, n_cust_median=35.0, revenue_median=20e9,
                           industry_mix={"steel_metals": .15, "textile_clothing": .3, "plastic_rubber": .3,
                                         "wholesale": .15, "food_processing": .05, "services": .05},
                           posting_mode_p=(0.25, 0.35, 0.40), payrun_p=(0.25, .05, .05, .05, .05, .17, .12, .12, .09, .05),
                           late_scale=1.25, dispute_scale=1.5, memo_invoice_no_p=(1.5, 3.0), **base),
        "sens_uk": WorldConfig(name="sens_uk", seed=21, n_firms=12, tail="uk", write_xml=0, **base),
        "sens_coface": WorldConfig(name="sens_coface", seed=22, n_firms=12, tail="coface", write_xml=0, **base),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--worlds", default="src,tgt,sens_uk,sens_coface")
    a = ap.parse_args()
    if a.calibrate or not CAL_FILE.exists():
        shift, pdm = calibrate()
    else:
        j = json.loads(CAL_FILE.read_text(encoding="utf-8"))
        shift, pdm = j["ontime_shift"], j["pd_mult"]
    cfgs = world_cfgs(shift, pdm)
    for w in [x.strip() for x in a.worlds.split(",") if x.strip()]:
        generate(cfgs[w])
        rep = report(SYNTH / w, RAW / "customer_invoices" / "Dataset.csv")
        (SYNTH / w / "fidelity_report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        print(json.dumps(rep["A_calibration_targets"]["achieved"].get("ALL"), default=str), flush=True)


if __name__ == "__main__":
    main()
