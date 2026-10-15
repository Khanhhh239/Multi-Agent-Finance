import sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression
from agent2 import methods as M
from agent2.data import load
from agent2.metrics import evaluate_scores
names = ["w3_s201", "w3_s202", "w3_s203", "w3_s204", "w3_s205"]
dfs = {n: load("work/data/" + n) for n in names}
ents = {n: M.EntityDeviation().fit(dfs[n][dfs[n].split == "train"], dfs[n][dfs[n].split == "validation"]) for n in names}
EP = {n: np.vstack([np.clip(v, 0, 12) for v in ents[n].parts(dfs[n]).values()]).T for n in names}
n_ent = EP[names[0]].shape[1]

def fit_prior_lr(X, y, w0, lam):
    sw = np.where(y > 0, (len(y) - y.sum()) / max(1, y.sum()), 1.0); sw = sw / sw.mean()
    def f(theta):
        b, w = theta[0], theta[1:]
        z = X @ w + b
        loss = np.sum(sw * (np.logaddexp(0, z) - y * z)) / len(y) + lam * np.sum((w - w0) ** 2)
        p = 1 / (1 + np.exp(-z))
        g = (X.T @ (sw * (p - y))) / len(y) + 2 * lam * (w - w0)
        return loss, np.concatenate([[np.sum(sw * (p - y)) / len(y)], g])
    r = minimize(f, np.concatenate([[-3.0], w0]), jac=True, method="L-BFGS-B")
    return r.x

rows = []
for target in names:
    others = [n for n in names if n != target]
    te_all = dfs[target][dfs[target].split == "test"]
    ep_te = EP[target][te_all.index.to_numpy()]
    fams = sorted(f for f in dfs[target].fraud_type.unique() if f)
    for fam in [None] + fams:
        Xs, Ys = [], []
        for w in others:
            d = dfs[w][dfs[w].split.isin(["train", "validation"])]
            keep = d.index[(d.fraud_type != fam)] if fam else d.index
            d = d.loc[keep]
            rest = pd.concat([dfs[n][dfs[n].split.isin(["train", "validation"])].pipe(lambda x: x[x.fraud_type != fam] if fam else x) for n in others if n != w], ignore_index=True)
            rl = M.RuleLogit().fit(rest)
            Xs.append(np.hstack([rl.score(d)[:, None], EP[w][d.index.to_numpy()]])); Ys.append(d.is_fraud.to_numpy())
        X, Y = np.vstack(Xs), np.concatenate(Ys)
        rest_all = pd.concat([dfs[n][dfs[n].split.isin(["train", "validation"])].pipe(lambda x: x[x.fraud_type != fam] if fam else x) for n in others], ignore_index=True)
        rl_all = M.RuleLogit().fit(rest_all)
        te = te_all if fam is None else te_all[(te_all.fraud_type == fam) | (te_all.is_fraud == 0)]
        ep = ep_te if fam is None else ep_te[(te_all.fraud_type == fam).values | (te_all.is_fraud == 0).values]
        Xt = np.hstack([rl_all.score(te)[:, None], ep])
        res = {}
        lr = LogisticRegression(C=.3, class_weight="balanced", max_iter=3000).fit(X, Y)
        res["Stack LR"] = lr.decision_function(Xt)
        for lam in (.002, .02):
            w0 = np.concatenate([[1.0], np.full(n_ent, .25)])
            th = fit_prior_lr(X, Y, w0, lam)
            res[f"Stack prior-LR lam={lam}"] = Xt @ th[1:] + th[0]
        rr = M.empirical_rank(dfs[target][dfs[target].split == "validation"]["rule_graph"].to_numpy(), te["rule_graph"].to_numpy())
        ee = M.empirical_rank(ents[target].score(dfs[target][dfs[target].split == "validation"]), ents[target].score(te))
        res["max-rank fusion"] = np.maximum(rr, ee) + 1e-3 * (rr + ee) / 2
        for k, s in res.items():
            r = evaluate_scores(te, s)
            rows.append(dict(target=target, family=fam or "ALL", method=k, ap=r["ap"], rec3=r["B3"]["recall"], prec3=r["B3"]["precision"], hn=r["B3"]["hard_neg_alert_rate"]))
    print(target, "done", flush=True)
out = pd.DataFrame(rows)
out.to_csv("work/results/stack_lfo.csv", index=False)
pd.set_option("display.width", 250)
print(out[out.family == "ALL"].groupby("method")[["ap", "rec3", "prec3", "hn"]].mean().round(3))
u = out[out.family != "ALL"]
print("UNSEEN FAMILY mean over families x targets:"); print(u.groupby("method")[["ap", "rec3"]].mean().round(3))
print(u.pivot_table(index="method", columns="family", values="rec3", aggfunc="mean").round(2).to_string())
