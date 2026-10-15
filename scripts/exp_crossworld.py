import sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from agent2 import methods as M
from agent2.data import load
from agent2.metrics import evaluate_scores, per_group_recall
names = ["w3_s201", "w3_s202", "w3_s203", "w3_s204", "w3_s205"]
dfs = {n: load("work/data/" + n) for n in names}
sets = M.supervised_sets()
out = {}
for target in names:
    pool = pd.concat([dfs[n] for n in names if n != target], ignore_index=True)
    train = pool[pool.split.isin(["train", "validation"])]
    valid = pool[pool.split == "test"]            # other worlds' test rows are used only for early stopping
    tgt = dfs[target]
    te = tgt[tgt.split == "test"]
    va_t = tgt[tgt.split == "validation"]
    tr_t = tgt[tgt.split == "train"]
    rg = lambda: M.RuleScore("rule_graph", "rg")
    ent = lambda: M.EntityDeviation()
    learned = M.Supervised(sets["friend190+eng+rules"], "L3-pretrained").fit(train, valid)
    fr = M.Supervised(sets["friend190"], "LGBM[friend190]-pretrained").fit(train, valid)
    rl = M.RuleLogit("Rules (weights pretrained on other worlds)").fit(train, valid)
    e = ent().fit(tr_t, va_t)
    res = {}
    def rec(name, score):
        r = evaluate_scores(te, score)
        res[name] = dict(ap=r["ap"], r_precision=r["r_precision"], B1=r["B1"], B3=r["B3"],
                         fam=per_group_recall(te, score, "fraud_type", 3))
        print(f"{target} {name:44s} AP={r['ap']:.3f} B3 P={r['B3']['precision']:.2f} R={r['B3']['recall']:.2f} case={r['B3']['case_recall']:.2f} hardneg={r['B3']['hard_neg_alert_rate']:.3f}", flush=True)
    rec("Rules+Graph (hand weights)", te["rule_graph"].to_numpy())
    rec("Rules (weights pretrained)", rl.score(te))
    rec("EntityDeviation", e.score(te))
    rec("LGBM[friend190] pretrained", fr.score(te))
    rec("L3 pretrained (friend190+eng+rules)", learned.score(te))
    ranks = lambda s, ref: M.empirical_rank(ref, s)
    rr = ranks(te["rule_graph"].to_numpy(), va_t["rule_graph"].to_numpy())
    rrl = ranks(rl.score(te), rl.score(va_t))
    er = ranks(e.score(te), e.score(va_t))
    lr = ranks(learned.score(te), learned.score(va_t))
    rec("Fusion max(Rules,Entity)", np.maximum(rr, er) + 1e-3 * (rr + er) / 2)
    rec("Fusion max(RulesPretrained,Entity)", np.maximum(rrl, er) + 1e-3 * (rrl + er) / 2)
    rec("Fusion max(L3,RulesPretrained,Entity)", np.maximum.reduce([lr, rrl, er]) + 1e-3 * (lr + rrl + er) / 3)
    rec("Fusion mean(L3,Entity)", (lr + er) / 2)
    out[target] = res
json.dump(out, open("work/results/crossworld.json", "w"), indent=1, default=float)
