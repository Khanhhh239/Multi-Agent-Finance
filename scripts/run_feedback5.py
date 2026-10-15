import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from agent2 import methods as M
from agent2.data import load
from agent2.feedback_sim import build_matrix, simulate
res = {}
for name in ["w3_s201", "w3_s202", "w3_s203", "w3_s204", "w3_s205"]:
    df = load("work/data/" + name)
    tr = df[df.split == "train"]
    dep = df[df.split != "train"].reset_index(drop=True)
    ent = M.EntityDeviation().fit(tr)
    x, base, origin = build_matrix(dep, tr["rule_graph"].to_numpy(dtype=float), ent)
    res[name] = {}
    for noise in (0.0, 0.15, 0.30):
        for mode in ("static", "relax", "reweight", "reweight+audit"):
            runs = [simulate(dep, x, base, origin, mode, budget=3, noise=noise, seed=s, lr=.3, pos_weight=3, soft=.1) for s in (1, 2, 3)]
            res[name][f"{mode}|{noise}"] = dict(tp_rows=float(np.mean([r["tp_rows"] for r in runs])), cases=float(np.mean([r["cases_found"] for r in runs])),
                                               cases_total=runs[0]["cases_total"], alerts=runs[0]["alerts"])
    print(name, {k: round(v["tp_rows"], 1) for k, v in res[name].items()}, flush=True)
json.dump(res, open("work/results/feedback_sim_5seeds.json", "w"), indent=1)
rows = []
for k in res["w3_s201"]:
    rows.append((k, np.mean([res[n][k]["tp_rows"] for n in res]), np.mean([res[n][k]["cases"] for n in res]), np.mean([res[n][k]["cases_total"] for n in res])))
print(pd.DataFrame(rows, columns=["mode|noise", "tp_rows", "cases_found", "cases_total"]).round(1).to_string(index=False))
