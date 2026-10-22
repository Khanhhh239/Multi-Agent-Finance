import sys, numpy as np, pandas as pd
sys.path.insert(0, ".")
sys.argv = ["x"]
import scripts.diag_cd_transfer as D
from agent2.metrics import tie_break, weekly_alerts
dev = [D.frame(f"w4_s{s}") for s in (411, 412, 413)]
for k, d in enumerate(dev): d["company_id"] = f"d{k}:" + d.company_id
pool = pd.concat(dev, ignore_index=True); tr, va = pool[pool.split=="train"], pool[pool.split=="validation"]
base = [c for c in pool.columns if c.startswith(("hit_","rule_","u_","type_"))]
print("CD nonzero share in train:", {c: round(float((tr[c]!=0).mean()),3) for c in D.CD_FEATURES})
tes = {s: D.frame(f"s4_s{s}").query("split=='test'").reset_index(drop=True) for s in (931,932,933)}
for name, cols in (("A", base), ("B", base + D.CD_FEATURES)):
    rows = []
    for seed in (0, 1, 2):
        m = D.fit(tr, va, cols, seed=seed)
        r = []
        for s, te in tes.items():
            pos = te.is_fraud.to_numpy()==1; nov = pos & te.fraud_type.isin(list(D.NOVEL)).to_numpy(); hard=(te.hard_negative_type.to_numpy()!="")&~pos
            a = weekly_alerts(te, m.predict_proba(te[cols])[:,1] + tie_break(len(te),5), 3)
            r.append((a[pos].mean(), a[nov].mean(), a[hard].mean()))
        rows.append(np.mean(r, axis=0))
        if name == "B" and seed == 0:
            g = dict(zip(cols, m.booster_.feature_importance("gain"))); print("B trees", m.booster_.num_trees(), "CD gain>0:", {c: round(float(g[c])) for c in D.CD_FEATURES if g[c] > 0})
    rows = np.array(rows); print(name, "recall/novel/hardFA mean over seeds:", rows.mean(0).round(4), "per seed:", rows.round(3).tolist())
