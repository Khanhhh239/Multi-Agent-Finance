#!/usr/bin/env python3
"""Sprint 4 — C2ST tách đặc trưng chủ đích / hành vi; so máy phát v1 và realism v2 (cặp cùng seed, 12 công ty).

  python scripts/sprint4/c2st_split.py --build   # sinh c2st_ctrl_v1 và c2st_v2 (nếu chưa có)
  python scripts/sprint4/c2st_split.py           # đo tất cả

Quy tắc đăng ký trước: mục tiêu <0,75 CHỈ áp cho bộ 'behavioral'. 'designed' (kỳ hạn) báo cáo minh bạch, không sửa cho giống bộ Mỹ.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.data.real_loaders import customer_invoices  # noqa: E402
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.synth.c2st import classifier_two_sample, match_window, FEATURE_SETS  # noqa: E402
from agent1.synth.world import WorldConfig, generate  # noqa: E402

PAIR = {"c2st_ctrl_v1": ("v1", False), "c2st_v2": ("v2", False), "c2st_v2_customers_exp": ("v2", True)}
EXISTING = ("src", "sens_uk", "sens_coface")


def build():
    fit = json.loads((SYNTH / "calibration_fit.json").read_text(encoding="utf-8"))
    for name, (real, cust) in PAIR.items():
        if (SYNTH / name / "invoices.parquet").exists():
            print("skip", name)
            continue
        generate(WorldConfig(name=name, seed=1, n_firms=12, realism=real, customer_realism=cust, write_xml=0,
                             ontime_shift=fit["ontime_shift"], pd_mult=fit["pd_mult"]), verbose=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--window-months", type=float, default=0,
                    help="cắt tổng hợp về cửa sổ N tháng/công ty (0 = toàn bộ, giao thức c2st-split-v1)")
    ap.add_argument("--worlds", default="", help="danh sách thế giới, phân tách bằng dấu phẩy (mặc định: tất cả)")
    a = ap.parse_args()
    if a.build:
        build()
    real = customer_invoices()
    real = real.dropna(subset=["paid_date_true"]).reset_index(drop=True)
    rows = []
    version = f"c2st-split-window{a.window_months:g}m-v1" if a.window_months else "c2st-split-v1"
    worlds = a.worlds.split(",") if a.worlds else list(PAIR) + list(EXISTING)
    for world in worlds:
        p = SYNTH / world / "invoices.parquet"
        if not p.exists():
            continue
        syn = pd.read_parquet(p)
        if a.window_months:
            syn = match_window(syn, a.window_months)
        syn = syn.dropna(subset=["paid_date_true"]).reset_index(drop=True)
        for fs in FEATURE_SETS:
            m, imp = classifier_two_sample(real, syn, feature_set=fs)
            rows.append(dict(world=world, feature_set=fs, **m, measurement_version=version))
            if fs == "behavioral":
                tag = f"_w{a.window_months:g}" if a.window_months else ""
                imp.to_csv(OUT / "data" / f"c2st_behavioral_features_{world}{tag}.csv", index=False)
            print(world, fs, round(m["AUC"], 4), flush=True)
    out = pd.DataFrame(rows)
    name = f"c2st_split_window{a.window_months:g}m.csv" if a.window_months else "c2st_split.csv"
    out.to_csv(OUT / "data" / name, index=False)
    print(out[["world", "feature_set", "AUC", "ci_low", "ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
