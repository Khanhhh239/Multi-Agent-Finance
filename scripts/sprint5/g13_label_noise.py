#!/usr/bin/env python3
"""G13 — nhãn T9 ước lượng ảnh hưởng thế nào tới cảnh báo? Cùng thế giới tgt, cùng đầu vào, chỉ khác nhãn thanh toán.

Áp CHÍNH SÁCH ĐÃ ĐÓNG BĂNG (outputs/g13/policy_choice.json: MC-copula-t, isotonic học trên src, τ=0,30, k=1) lên
  - E2E nhãn T9 ước lượng : outputs/e2e/protocol/t6_shortfall_predictions.csv
  - E2E nhãn thật cùng đầu vào : outputs/e2e/protocol/oracle_equal_budget/t6_shortfall_predictions.csv
Không chọn lại gì. Đầu ra: outputs/g13/v3/label_noise.csv
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.eval.alert_policy import fit_isotonic, policy_metrics, firm_bootstrap  # noqa: E402

MODEL = "MC-copula-t (T1+T4+T5)"


def main():
    ch = json.loads((OUT / "g13/policy_choice.json").read_text(encoding="utf-8"))[f"{MODEL}|isotonic"]
    src = pd.read_csv(OUT / "g13/src_backtest/t6_shortfall_predictions.csv", parse_dates=["cutoff"])
    s = src[src.model == MODEL]
    iso = fit_isotonic(s["y13"], s["p13"])
    cash = pd.read_parquet(SYNTH / "tgt/daily_cash.parquet", columns=["firm_id", "date", "balance"])
    rows = []
    for label, path in (("T9 ước lượng (E2E)", OUT / "e2e/protocol/t6_shortfall_predictions.csv"),
                        ("nhãn thật, cùng đầu vào", OUT / "e2e/protocol/oracle_equal_budget/t6_shortfall_predictions.csv")):
        t = pd.read_csv(path, parse_dates=["cutoff"]); t = t[t.model == MODEL].reset_index(drop=True)
        t = t.assign(q=iso.predict(t["p13"]))
        m = policy_metrics(t, cash, "q", ch["tau"], ch["k"], 91)
        ci = firm_bootstrap(t, cash, "q", ch["tau"], ch["k"], 91)
        brier = float(((t.q - t.y13) ** 2).mean())
        rows.append(dict(labels=label, tau=ch["tau"], k=ch["k"], brier_13w=brier, **m, **ci, policy_frozen_on="src",
                         world="tgt", measurement_version="g13-label-noise-v1"))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "g13/v3/label_noise.csv", index=False)
    print(out[["labels", "n_events", "detected_at_least_4w", "detected_ci_low", "detected_ci_high", "median_lead_weeks",
               "false_alarms_per_firm_year", "fa_ci_low", "fa_ci_high", "brier_13w"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
