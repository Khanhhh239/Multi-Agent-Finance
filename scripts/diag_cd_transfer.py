"""Diagnostic only: does adding change_detect features help S2 transfer? (dữ liệu tổng hợp)

Light models (rule hits + label-free u_* scores + transaction type, about 70 columns) trained with PU weight
0.2 on the v4 development worlds 411..413 and scored on the spent v4 sealed worlds 931..933. A = without,
B = with the change features. This is a post-hoc diagnostic to decide whether the features deserve a slot in
the registered v5 screening; it is not selection evidence.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from agent2.change_detect import CD_FEATURES, change_features  # noqa: E402
from agent2.metrics import tie_break, weekly_alerts  # noqa: E402
from agent2.world_v4_sealed import NOVEL  # noqa: E402

ROOT = Path("work/data")
CACHE = Path("work/diag/cd_cache")
TYPES = ["payroll", "vendor_payment", "cash_expense", "sales_invoice", "customer_receipt", "stock_purchase",
         "selling_expense", "cogs", "material_purchase", "advance_issue", "rent", "cash_withdrawal", "adjustment",
         "advance_settlement", "tax_payment", "bad_debt_writeoff", "sales_return", "inventory_writeoff",
         "customer_refund", "advance_writeoff", "tools_purchase"]


def frame(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{name}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    path = ROOT / name
    tx = pd.read_csv(path / "transactions.csv", dtype=str, keep_default_na=False,
                     usecols=["transaction_id", "company_id", "posted_at", "txn_type"])
    lab = pd.read_csv(path / "labels.csv", dtype=str, keep_default_na=False,
                      usecols=["transaction_id", "is_fraud", "fraud_type", "hard_negative_type"])
    df = tx.merge(lab, on="transaction_id").merge(pd.read_csv(path / "splits.csv", dtype=str), on="transaction_id")
    rules = pd.read_pickle(path / "_cache" / "rules2.pkl")
    keep = ["transaction_id", "rule_graph", "rule_direct", "rule_hard"] + [c for c in rules if c.startswith("hit_")]
    df = df.merge(rules[keep], on="transaction_id", how="left")
    df = df.merge(pd.read_pickle(path / "_cache" / "ustack.pkl"), on="transaction_id", how="left")
    df = df.merge(change_features(path), on="transaction_id")
    for t in TYPES:
        df[f"type_{t}"] = (df.txn_type == t).astype(np.int8)
    t = pd.to_datetime(df.posted_at, utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    df["week"] = (t - pd.Timestamp("2024-01-01")).dt.days // 7
    df["is_fraud"] = df.is_fraud.astype(int)
    df = df.drop(columns=["posted_at"])
    num = df.select_dtypes("float64").columns
    df[num] = df[num].astype(np.float32)
    df.to_parquet(out, index=False)
    return df


def fit(train, valid, cols, w=.2, seed=0):
    y = train.is_fraud.to_numpy()
    sw = np.where(y == 1, 1.0, w)
    # Fixed 400 trees, 15 leaves: early stopping on validation AP collapsed to ONE tree on some seeds.
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=.05, num_leaves=15, min_child_samples=10,
                           subsample=.8, subsample_freq=1, colsample_bytree=.6, reg_lambda=2.0,
                           scale_pos_weight=max(1.0, (len(y) - y.sum()) / y.sum()) ** .5, random_state=seed,
                           verbose=-1, n_jobs=4)
    m.fit(train[cols], y, sample_weight=sw)
    return m


def main():
    dev = [frame(f"w4_s{s}") for s in (411, 412, 413)]
    for k, d in enumerate(dev):                      # world prefix so pooled keys never collide
        d["company_id"] = f"d{k}:" + d.company_id
    pool = pd.concat(dev, ignore_index=True)
    del dev
    tr, va = pool[pool.split == "train"], pool[pool.split == "validation"]
    base = [c for c in pool.columns if c.startswith(("hit_", "rule_", "u_", "type_"))]
    models = {"A rules+u+type": base, "B A+change": base + CD_FEATURES}
    fitted = {n: fit(tr, va, c) for n, c in models.items()}
    res = {"data_origin": "dữ liệu tổng hợp", "status": "post-hoc diagnostic, not selection"}
    for s in (931, 932, 933):
        te = frame(f"s4_s{s}")
        te = te[te.split == "test"].reset_index(drop=True)
        pos = te.is_fraud.to_numpy() == 1
        novel = pos & te.fraud_type.isin(list(NOVEL)).to_numpy()
        hard = (te.hard_negative_type.to_numpy() != "") & ~pos
        res[s] = {}
        for n, m in fitted.items():
            a = weekly_alerts(te, m.predict_proba(te[models[n]])[:, 1] + tie_break(len(te), 5), 3)
            res[s][n] = dict(recall=round(float(a[pos].mean()), 4), known=round(float(a[pos & ~novel].mean()), 4),
                             novel=round(float(a[novel].mean()), 4), hard_fa=round(float(a[hard].mean()), 4),
                             by_novel={f: round(float(a[pos & (te.fraud_type == f).to_numpy()].mean()), 3) for f in NOVEL})
        print(s, {n: (v["recall"], v["novel"], v["hard_fa"]) for n, v in res[s].items()}, flush=True)
    imp = fitted["B A+change"].booster_.feature_importance("gain")
    names = models["B A+change"]
    res["top_change_gain"] = sorted([(n, float(g)) for n, g in zip(names, imp) if n in CD_FEATURES], key=lambda x: -x[1])[:10]
    Path("work/diag/diag_cd_transfer.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
