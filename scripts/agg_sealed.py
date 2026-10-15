import json, numpy as np, pandas as pd
r = json.load(open("work/results/final_sealed.json"))
worlds = [k for k in r if k.startswith("sealed")]
cfgs = ["Rules (friend)", "Novelty (cold start)", "CES", "CES 2+1", "CES 1+2", "L3", "L3 2+1", "B1 Novelty", "B1 CES", "B1 L3", "B2 CES 1+1", "B2 L3 1+1"]
novel = ["price_creep", "off_cycle_payroll", "vendor_burst"]
rows = []
for c in cfgs:
    g = lambda k: np.mean([r[w][c][k] for w in worlds])
    nov = np.mean([r[w][c]["by_family_recall"][f] for w in worlds for f in novel])
    old = np.mean([r[w][c]["by_family_recall"][f] for w in worlds for f in r[worlds[0]][c]["by_family_recall"] if f not in novel])
    rows.append(dict(config=c, alerts=g("alerts"), precision=g("precision"), recall=g("recall"), recall_old9=old, recall_novel3=nov, case=g("case_recall"), hardneg=g("hard_neg_alert_rate"), ent_prec=g("entity_precision"),
                     **{f"n_{f[:8]}": np.mean([r[w][c]["by_family_recall"][f] for w in worlds]) for f in novel}))
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
print(pd.DataFrame(rows).set_index("config").round(3))
print("AP:", {k: round(np.mean([r[w]["_ap"][k] for w in worlds]), 3) for k in r[worlds[0]]["_ap"]})
print(r["ces_weights"])
fam = pd.DataFrame({c: pd.Series(np.mean([[r[w][c]["by_family_recall"][f] for f in sorted(r[worlds[0]][c]["by_family_recall"])] for w in worlds], axis=0), index=sorted(r[worlds[0]][c]["by_family_recall"])) for c in ["Rules (friend)", "Novelty (cold start)", "CES 2+1", "L3 2+1", "L3"]})
print(fam.round(2))

