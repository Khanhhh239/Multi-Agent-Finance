#!/usr/bin/env python3
"""T2 trên dữ liệu THẬT (SBA 7(a), Mỹ): xác suất bị xoá nợ trong 3 năm kể từ phê duyệt — chia theo năm tài khoá
(train FY2010–2016, hiệu chỉnh FY2017, test FY2018–2022). So sánh logistic, LightGBM, LightGBM + isotonic.
T3 trên tổng hợp: xác suất tranh chấp / trả một phần của hoá đơn tại ngày lập, học trên src, test trên tgt,
đặc trưng = lịch sử tranh chấp/trả một phần của khách (co về trung bình, as-of ngày lập)."""
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.threads import NT  # noqa: E402
from agent1.data import real_loaders as R  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402

RES = OUT / "t2_t3"
RES.mkdir(parents=True, exist_ok=True)
CAT = ["FixedorVariableInterestInd", "naics2", "ProjectState", "BusinessType", "BusinessAge", "RevolverStatus",
       "CollateralInd", "ProcessingMethod", "SoldSecMrktInd"]
NUM = ["log_amount", "guarantee_ratio", "TermInMonths", "InitialInterestRate", "JobsSupported", "approval_month",
       "is_franchise", "out_of_state_lender"]


def prob_metrics(y, p):
    return dict(ROC_AUC=roc_auc_score(y, p) if len(np.unique(y)) > 1 else np.nan,
                PR_AUC=average_precision_score(y, p) if np.any(y) else np.nan, Brier=M.brier(y, p),
                logloss=M.logloss(y, p), ECE=M.ece(y, p), mean_p=float(np.mean(p)), base_rate=float(np.mean(y)))


def t2_sba(exempt='drop'):
    df = R.sba_7a(exempt=exempt)
    n_unobserved = int((~df['label_observed']).sum())
    df = df[df['label_observed']].copy()
    df['y'] = df['y'].astype(int)
    df["is_franchise"] = df["FranchiseCode"].notna().astype(int)
    df["out_of_state_lender"] = (df["BankState"] != df["BorrState"]).astype(int)
    for c in CAT:
        df[c] = df[c].astype(str).fillna("NA").astype("category")
    fy = df["ApprovalFY"].astype(int)
    tr, ca, te = df[fy <= 2016], df[fy == 2017], df[(fy >= 2018) & (fy <= 2022)]
    rows = []
    # logistic (one-hot các biến phân loại phổ biến)
    Xall = pd.get_dummies(df[CAT], drop_first=True, sparse=False).astype("float32")
    Xn = df[NUM].astype("float32").fillna(df.loc[fy <= 2016, NUM].median()).fillna(0)
    Xn = (Xn - Xn[fy <= 2016].mean()) / (Xn[fy <= 2016].std() + 1e-6)
    XL = pd.concat([Xn, Xall], axis=1).values
    lr = LogisticRegression(max_iter=400, C=0.5).fit(XL[(fy <= 2016).values], tr["y"].values)
    p_lr = lr.predict_proba(XL[((fy >= 2018) & (fy <= 2022)).values])[:, 1]
    # LightGBM
    p = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.8,
             bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=NT, seed=1)
    m = lgb.train(p, lgb.Dataset(tr[CAT + NUM], tr["y"]), 800, valid_sets=[lgb.Dataset(ca[CAT + NUM], ca["y"])],
                  callbacks=[lgb.early_stopping(50, verbose=False)])
    p_gb = m.predict(te[CAT + NUM])
    iso = IsotonicRegression(out_of_bounds="clip").fit(m.predict(ca[CAT + NUM]), ca["y"])
    p_iso = iso.predict(p_gb)
    prior = np.full(len(te), tr["y"].mean())
    for name, pp in (("Base rate (train)", prior), ("Logistic", p_lr), ("LightGBM", p_gb), ("LightGBM + isotonic (FY2017)", p_iso)):
        for stratum, mask in [('term<=120', te.TermInMonths.le(120).to_numpy()), ('term>120', te.TermInMonths.gt(120).to_numpy())]:
            if not mask.any():
                continue
            y = te['y'].to_numpy()[mask]
            pred = pp[mask]
            r = dict(task="T2 SBA 7(a) charge-off<=3y (REAL)", model=name, n_test=int(mask.sum()),
                     exempt_policy=exempt, stratum=stratum, n_unobserved_excluded=n_unobserved, seed=1,
                     measurement_version='sba-exempt-v2', **prob_metrics(y, pred))
            amt = te['GrossApproval'].to_numpy()[mask]
            r['expected_vs_actual_default_amount'] = float((pred * amt).sum() / max((y * amt).sum(), 1))
            r['PR_AUC_over_base'] = r['PR_AUC'] / max(r['base_rate'], 1e-12)
            # Chưa có định danh DN ổn định trong bộ cột nạp: không giả CI cấp khoản vay là CI theo DN.
            r['company_bootstrap_status'] = 'unavailable_borrower_id'
            rows.append(r)
    byfy = pd.DataFrame({"fy": te["ApprovalFY"].values, "y": te["y"].values, "p": p_iso}).groupby("fy").mean()
    byfy.to_csv(RES / f"t2_sba_calibration_by_fy_{exempt}.csv")
    return rows


def t3_synth():
    rows = []
    feats = ["c_n", "c_disp_eb", "c_part_eb", "log_amt_rel", "term_days", "c_late_eb"]

    def build(world):
        inv = pd.read_parquet(SYNTH / world / "invoices.parquet").sort_values("issue_date")
        inv["amt_rel"] = inv["amount_gross"] / inv.groupby("firm_id")["amount_gross"].transform("median")
        g = inv.groupby("customer_id")
        # lịch sử as-of ngày lập: chỉ hoá đơn đã TẤT TOÁN trước ngày lập (biết được tranh chấp/trả một phần)
        out = []
        for cid, x in g:
            x = x.reset_index(drop=True)
            closed_at = x["paid_date_true"].fillna(x["writeoff_date"]).fillna(pd.Timestamp("2100-01-01")).values
            iss = x["issue_date"].values
            disp, part = x["dispute"].values.astype(float), x["partial"].values.astype(float)
            late = (x["days_late_true"].fillna(60).values > 0).astype(float)
            order = np.argsort(closed_at)
            cs = closed_at[order]
            cd, cp, cl = np.cumsum(disp[order]), np.cumsum(part[order]), np.cumsum(late[order])
            k = np.searchsorted(cs, iss, side="left")
            n = k.astype(float)
            sd = np.where(k > 0, cd[np.maximum(k - 1, 0)], 0)
            sp = np.where(k > 0, cp[np.maximum(k - 1, 0)], 0)
            sl = np.where(k > 0, cl[np.maximum(k - 1, 0)], 0)
            out.append(pd.DataFrame({"invoice_id": x["invoice_id"], "c_n": n, "c_disp_eb": (sd + 0.02 * 20) / (n + 20),
                                     "c_part_eb": (sp + 0.05 * 20) / (n + 20), "c_late_eb": (sl + 0.4 * 10) / (n + 10)}))
        f = pd.concat(out)
        inv = inv.merge(f, on="invoice_id")
        inv["log_amt_rel"] = np.log(inv["amt_rel"])
        return inv[inv["term_days"] > 0]

    src, tgt = build("src"), build("tgt")
    src = src[src["issue_date"] < "2024-07-01"]
    tgt = tgt[(tgt["issue_date"] >= "2024-07-01") & (tgt["issue_date"] <= "2025-06-30")]
    for label in ("dispute", "partial"):
        p = dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, verbose=-1, num_threads=NT, seed=2)
        m = lgb.train(p, lgb.Dataset(src[feats], src[label].astype(int)), 300)
        y = tgt[label].astype(int).values
        hist = tgt[f"c_{label[:4]}_eb"].values
        for name, pp in (("Base rate (src)", np.full(len(tgt), src[label].mean())),
                         ("Customer history rate (EB)", hist), ("LightGBM (src->tgt)", m.predict(tgt[feats]))):
            rows.append(dict(task=f"T3 {label} at issue (synthetic tgt)", model=name, n_test=len(tgt), **prob_metrics(y, pp)))
    # số tiền thu thực tế / số trên HĐ (tranh chấp -> giảm trừ; trả thiếu)
    for world, d in (("src", src), ("tgt", tgt)):
        ratio = (d["paid_amount"] / d["amount_gross"]).where(~d["is_bad_debt"])
        rows.append(dict(task=f"T3 collected/invoiced ratio ({world})", model="descriptive",
                         n_test=int(ratio.notna().sum()), mean_p=float(ratio.mean()),
                         base_rate=float((ratio < 0.995).mean())))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('--tasks', default='sba,t3')
    ap.add_argument('--exempt', default='drop,keep,censor')
    args = ap.parse_args()
    tasks = args.tasks.split(',')
    rows = []
    if 'sba' in tasks:
        for policy in args.exempt.split(','):
            rows += t2_sba(policy)
        pd.DataFrame(rows).to_csv(RES / 't2_sba_variants.csv', index=False)
    print(pd.DataFrame(rows).round(4).to_string(), flush=True)
    if 't3' in tasks:
        rows += t3_synth()
    out = pd.DataFrame(rows)
    print(out.round(4).to_string(), flush=True)
    out.to_csv(RES / "t2_t3_results.csv", index=False)
