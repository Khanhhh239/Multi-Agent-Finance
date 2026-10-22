#!/usr/bin/env python3
"""G8 — hiệu chỉnh lại hằng năm bằng nhóm khoản vay đã chín nhãn (đăng ký trước: docs/03_Evaluation/G8_T2_PREREG.md).
Đầu ra: outputs/sprint5/t2_rolling_recal.csv"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.special import expit, logit
from scipy.optimize import brentq
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from agent1.paths import OUT  # noqa: E402
from agent1.threads import NT  # noqa: E402
from agent1.data import real_loaders as R  # noqa: E402
from run_t2_t3 import CAT, NUM, prob_metrics  # noqa: E402

VERSION = "sba-rolling-recal-f-minus-4-v1"
LAG = 4


def shift_intercept(p, target):
    z = logit(np.clip(p, 1e-6, 1 - 1e-6))
    f = lambda b: expit(z + b).mean() - target  # noqa: E731
    return brentq(f, -6, 6)


def main():
    df = R.sba_7a(exempt="drop")
    df = df[df["label_observed"]].copy(); df["y"] = df["y"].astype(int)
    df["is_franchise"] = df["FranchiseCode"].notna().astype(int)
    df["out_of_state_lender"] = (df["BankState"] != df["BorrState"]).astype(int)
    for c in CAT:
        df[c] = df[c].astype(str).fillna("NA").astype("category")
    fy = df["ApprovalFY"].astype(int)
    tr, ca = df[fy <= 2013], df[fy == 2014]
    params = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.8,
                  bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=NT, seed=1)
    m = lgb.train(params, lgb.Dataset(tr[CAT + NUM], tr["y"]), 800, valid_sets=[lgb.Dataset(ca[CAT + NUM], ca["y"])],
                  callbacks=[lgb.early_stopping(50, verbose=False)])
    iso14 = IsotonicRegression(out_of_bounds="clip").fit(m.predict(ca[CAT + NUM]), ca["y"])
    preds = {"A isotonic f-4": [], "B intercept f-4": [], "C isotonic FY2014 (hiện tại)": []}
    tests = []
    for f in range(2018, 2023):
        te = df[(fy == f) & (df.TermInMonths <= 120)]
        co = df[(fy == f - LAG) & (df.TermInMonths <= 120)]
        pc, pt = m.predict(co[CAT + NUM]), m.predict(te[CAT + NUM])
        preds["A isotonic f-4"].append(IsotonicRegression(out_of_bounds="clip").fit(pc, co["y"]).predict(pt))
        preds["B intercept f-4"].append(expit(logit(np.clip(pt, 1e-6, 1 - 1e-6)) + shift_intercept(pc, co["y"].mean())))
        preds["C isotonic FY2014 (hiện tại)"].append(iso14.predict(pt))
        tests.append(te)
    rows = []
    scopes = {"gộp FY2018-2022 (cổng)": [0, 1, 2, 3, 4], "gộp FY2018-2021 (bỏ FY2022)": [0, 1, 2, 3]}
    scopes.update({f"FY{2018 + i}": [i] for i in range(5)})
    for scope, idx in scopes.items():
        te = pd.concat([tests[i] for i in idx]); y = te["y"].to_numpy(); amt = te["GrossApproval"].to_numpy()
        for name, parts in preds.items():
            p = np.concatenate([parts[i] for i in idx])
            r = dict(scope=scope, model=name, n_test=len(te), **prob_metrics(y, p))
            r["expected_vs_actual_default_amount"] = float((p * amt).sum() / max((y * amt).sum(), 1))
            r["PR_AUC_over_base"] = r["PR_AUC"] / max(r["base_rate"], 1e-12)
            r["G8_pass"] = bool(r["PR_AUC_over_base"] >= 2 and r["ECE"] <= .02 and .8 <= r["expected_vs_actual_default_amount"] <= 1.25)
            r.update(measurement_version=VERSION, calibration_lag_years=LAG, stratum="term<=120", exempt_policy="drop")
            rows.append(r)
    out = pd.DataFrame(rows)
    (OUT / "sprint5").mkdir(exist_ok=True)
    out.to_csv(OUT / "sprint5" / "t2_rolling_recal.csv", index=False)
    print(out[["scope", "model", "n_test", "base_rate", "mean_p", "PR_AUC_over_base", "ECE", "expected_vs_actual_default_amount", "G8_pass"]]
          .round(3).to_string(index=False))


if __name__ == "__main__":
    main()
