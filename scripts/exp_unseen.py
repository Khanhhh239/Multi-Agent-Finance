import sys, warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from agent2 import methods as M
from agent2.data import load
from agent2.metrics import evaluate_scores
df = load("work/data/" + sys.argv[1])
sets = M.supervised_sets()
def factories():
    ent = lambda: M.EntityDeviation()
    rg = lambda: M.RuleScore("rule_graph", "rg")
    full = lambda: M.Supervised(sets["friend190+eng+rules"], "L3")
    return {
     "Entity(label-free)": ent,
     "Rules+Graph": rg,
     "Gate(Rules,Entity)": lambda: M.Gate(rg(), ent(), eps=.5, name="g"),
     "Fusion mean(Rules,Entity)": lambda: M.RankFusion([rg(), ent()], "mean", name="f1"),
     "Fusion max(Rules,Entity)": lambda: M.RankFusion([rg(), ent()], "max", name="f2"),
     "RuleLogit": lambda: M.RuleLogit(),
     "L3 LGBM full": full,
     "Fusion mean(L3,Rules,Entity)": lambda: M.RankFusion([full(), rg(), ent()], "mean", name="f3"),
     "Fusion max(L3,Rules,Entity)": lambda: M.RankFusion([full(), rg(), ent()], "max", name="f4"),
    }
fams = sorted(f for f in df.fraud_type.unique() if f)
rows = []
for fam in fams:
    hide = df.index[df.fraud_type == fam]
    tr = df[(df.split == "train") & ~df.index.isin(hide)]
    va = df[(df.split == "validation") & ~df.index.isin(hide)]
    te = df[(df.split == "test") & ((df.fraud_type == fam) | (df.is_fraud == 0))]
    for name, make in factories().items():
        m = make().fit(tr, va)
        r = evaluate_scores(te, m.score(te))
        rows.append(dict(family=fam, method=name, ap=r["ap"], rec3=r["B3"]["recall"], prec3=r["B3"]["precision"], n=r["positives"]))
out = pd.DataFrame(rows)
piv = out.pivot(index="method", columns="family", values="ap").round(2)
piv["mean"] = piv.mean(axis=1).round(3)
print(piv.sort_values("mean", ascending=False).to_string())
piv2 = out.pivot(index="method", columns="family", values="rec3").round(2); piv2["mean"] = piv2.mean(axis=1).round(3)
print(piv2.sort_values("mean", ascending=False).to_string())
out.to_csv("work/results/unseen_%s.csv" % sys.argv[1], index=False)
