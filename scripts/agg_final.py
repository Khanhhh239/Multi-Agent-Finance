import json, numpy as np, pandas as pd
r = json.load(open("work/results/final_dev.json"))
cfgs = ["Rules (friend)", "Novelty (cold start)", "CES", "CES 2+1", "CES 1+2", "L3", "L3 2+1"]
rows = []
for cfg in cfgs:
    ind = [r[w]["in_distribution"][cfg] for w in r]
    row = dict(config=cfg,
        in_recall=np.mean([x["recall"] for x in ind]), in_prec=np.mean([x["precision"] for x in ind]), in_case=np.mean([x["case_recall"] for x in ind]),
        in_hn=np.mean([x["hard_neg_alert_rate"] for x in ind]), in_ent_prec=np.mean([x["entity_precision"] for x in ind]))
    fams = sorted(next(iter(r.values()))["unseen_family"])
    un = {f: np.mean([r[w]["unseen_family"][f][cfg]["recall"] for w in r]) for f in fams}
    row["unseen_recall_mean"] = np.mean(list(un.values()))
    row["unseen_case_mean"] = np.mean([np.mean([r[w]["unseen_family"][f][cfg]["case_recall"] for w in r]) for f in fams])
    row["unseen_hn"] = np.mean([np.mean([r[w]["unseen_family"][f][cfg]["hard_neg_alert_rate"] for w in r]) for f in fams])
    row.update({f"u_{f[:10]}": round(v, 2) for f, v in un.items()})
    rows.append(row)
df = pd.DataFrame(rows).set_index("config")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(df[["in_recall", "in_prec", "in_case", "in_hn", "in_ent_prec", "unseen_recall_mean", "unseen_case_mean", "unseen_hn"]].round(3))
print(df[[c for c in df.columns if c.startswith("u_")]].round(2).to_string())
ap = {k: np.mean([r[w]["in_distribution"]["_ap"][k] for w in r]) for k in r[next(iter(r))]["in_distribution"]["_ap"]}
print("AP", {k: round(v, 3) for k, v in ap.items()})
sel = df.assign(score=(df.in_recall + df.unseen_recall_mean) / 2)[["score", "in_hn", "unseen_hn"]]
print(sel.round(3))
