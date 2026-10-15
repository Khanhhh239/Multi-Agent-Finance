import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from agent2 import methods as M
from agent2.alerting import select_mixed
from agent2.metrics import operating_point
src = open("work/exp_stack_lfo.py", encoding="utf-8-sig").read()
head = src.split("rows = []")[0]
exec(head)
rows = []
for target in names:
    others = [n for n in names if n != target]
    te_all = dfs[target][dfs[target].split == "test"]
    ep_te = EP[target][te_all.index.to_numpy()]
    fams = sorted(f for f in dfs[target].fraud_type.unique() if f)
    for fam in [None] + fams:
        sub = lambda x: x[x.fraud_type != fam] if fam else x
        Xs, Ys = [], []
        for w in others:
            d = sub(dfs[w][dfs[w].split.isin(["train", "validation"])])
            rest = pd.concat([sub(dfs[n][dfs[n].split.isin(["train", "validation"])]) for n in others if n != w], ignore_index=True)
            rl = M.RuleLogit().fit(rest)
            Xs.append(np.hstack([rl.score(d)[:, None], EP[w][d.index.to_numpy()]])); Ys.append(d.is_fraud.to_numpy())
        X, Y = np.vstack(Xs), np.concatenate(Ys)
        rl_all = M.RuleLogit().fit(pd.concat([sub(dfs[n][dfs[n].split.isin(["train", "validation"])]) for n in others], ignore_index=True))
        mask = np.ones(len(te_all), bool) if fam is None else ((te_all.fraud_type == fam) | (te_all.is_fraud == 0)).to_numpy()
        te = te_all[mask]; ep = ep_te[mask]
        Xt = np.hstack([rl_all.score(te)[:, None], ep])
        w0 = np.concatenate([[1.0], np.full(n_ent, .25)])
        th = fit_prior_lr(X, Y, w0, .02)
        stack = Xt @ th[1:] + th[0]
        val = dfs[target][dfs[target].split == "validation"]
        rr = M.empirical_rank(val["rule_graph"].to_numpy(), te["rule_graph"].to_numpy())
        ee = M.empirical_rank(ents[target].score(val), ents[target].score(te))
        novelty = np.maximum(rr, ee) + 1e-3 * (rr + ee) / 2
        te = te.reset_index(drop=True)
        configs = {"stack only (3 slots)": (3, 0), "novelty only (3 slots)": (0, 3), "stack 2 + novelty 1": (2, 1), "stack 1 + novelty 2": (1, 2)}
        for name, (a, b) in configs.items():
            alerts = select_mixed(te, stack, novelty, a, b)
            op = operating_point(te, alerts)
            rows.append(dict(target=target, family=fam or "ALL", config=name, recall=op["recall"], precision=op["precision"], case_recall=op["case_recall"], hn=op["hard_neg_alert_rate"], alerts=op["alerts"]))
out = pd.DataFrame(rows)
out.to_csv("work/results/mixed_slots.csv", index=False)
print("IN-DISTRIBUTION (cross-world):"); print(out[out.family == "ALL"].groupby("config")[["recall", "precision", "case_recall", "hn", "alerts"]].mean().round(3))
u = out[out.family != "ALL"]
print("UNSEEN FAMILY:"); print(u.groupby("config")[["recall", "case_recall"]].mean().round(3))
print(u.pivot_table(index="config", columns="family", values="recall", aggfunc="mean").round(2).to_string())
