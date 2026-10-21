#!/usr/bin/env python3
"""Chạy luồng ĐÃ ĐÓNG BĂNG trên tgt2 đúng một lần (đăng ký trước: docs/03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md, mục 4).

Không chọn gì trên tgt2:
  - mô hình T1/T2/T4/Direct, rho: học/chọn trên src bên trong run_t6.main (như E2E);
  - chính sách cảnh báo: τ, k đã chọn trên backtest src (outputs/g13/policy_choice.json), isotonic học trên src.
Giới hạn: tgt2 sinh với write_xml=0 nên KHÔNG có đường T9 ước lượng (nhãn = số dư/thanh toán thật tgt2, 'oracle_bank').
Kết quả vì vậy là cận trên so với E2E nhãn ước lượng của tgt.

  python scripts/sprint5/run_tgt2_frozen.py            # chạy T6 (~1 giờ) rồi chấm chính sách
  python scripts/sprint5/run_tgt2_frozen.py --score    # chỉ chấm lại từ dự báo đã có
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.eval.alert_policy import fit_isotonic, policy_metrics, firm_bootstrap  # noqa: E402

RES = OUT / "tgt2"
HORIZON = 13
MODEL = "MC-copula-t (T1+T4+T5)"


def score():
    choices = json.loads((OUT / "g13" / "policy_choice.json").read_text(encoding="utf-8"))
    src = pd.read_csv(OUT / "g13" / "src_backtest" / "t6_shortfall_predictions.csv", parse_dates=["cutoff"])
    t2 = pd.read_csv(RES / "t6" / "t6_shortfall_predictions.csv", parse_dates=["cutoff"])
    cash = pd.read_parquet(SYNTH / "tgt2" / "daily_cash.parquet", columns=["firm_id", "date", "balance"])
    p, y = f"p{HORIZON}", f"y{HORIZON}"
    rows = []
    for key, ch in choices.items():
        model, calib = key.split("|")
        s, t = src[src.model == model], t2[t2.model == model]
        if t.empty:
            continue
        q = t[p] if calib == "raw" else fit_isotonic(s[y], s[p]).predict(t[p])
        t = t.assign(q=np.asarray(q, float))
        m = policy_metrics(t, cash, "q", ch["tau"], ch["k"], 7 * HORIZON)
        ci = firm_bootstrap(t, cash, "q", ch["tau"], ch["k"], 7 * HORIZON)
        rows.append(dict(model=model, calibration=calib, horizon=HORIZON, tau=ch["tau"], k=ch["k"], **m, **ci,
                         threshold_selected_on="source_only", target_used_for_selection=False, world="tgt2",
                         labels="oracle_bank", measurement_version="g13-frozen-tgt2-v1"))
    out = pd.DataFrame(rows)
    out.to_csv(RES / "alert_policy_tgt2.csv", index=False)
    cols = ["model", "calibration", "tau", "k", "n_events", "detected_at_least_4w", "detected_ci_low", "detected_ci_high",
            "median_lead_weeks", "false_alarms_per_firm_year", "fa_ci_low", "fa_ci_high"]
    print(out[cols].round(3).to_string(index=False))
    r = out[(out.model == MODEL) & (out.calibration == "isotonic")].iloc[0]
    ok = r.n_events > 0 and r.detected_at_least_4w >= .7 and r.median_lead_weeks >= 4 and r.false_alarms_per_firm_year <= 1
    print("G13 tgt2:", "PASSED" if ok else "FAILED")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--score", action="store_true"); a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    if not a.score:
        import run_t6
        run_t6.main(target_world="tgt2", evaluation_world="tgt2", result_dir=RES / "t6", source_budget=40000,
                    n_weeks=52, label_mode="oracle_bank")
    score()


if __name__ == "__main__":
    main()
