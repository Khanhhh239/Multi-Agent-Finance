"""Diagnostic only: label-free recall@B3 of EntityDeviation2 vs rules and the old Novelty, per scheme.

Not a selection run and not registered evidence. Output is dữ liệu tổng hợp; on sealed v4 worlds it is a
post-hoc diagnostic (those worlds are already spent). Usage:
  python scripts/diag_change_detect.py work/data/v5dev_s1001 [more worlds...] --out results/v5/diag_cd.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from agent2.change_detect import EntityDeviation2, change_features  # noqa: E402
from agent2.methods import empirical_rank  # noqa: E402
from agent2.metrics import tie_break, weekly_alerts  # noqa: E402


def world(path: Path):
    tx = pd.read_csv(path / "transactions.csv", dtype=str, keep_default_na=False,
                     usecols=["transaction_id", "company_id", "posted_at", "txn_type"])
    lab = pd.read_csv(path / "labels.csv", dtype=str, keep_default_na=False,
                      usecols=["transaction_id", "is_fraud", "fraud_type", "hard_negative_type"])
    sp = pd.read_csv(path / "splits.csv", dtype=str)
    df = tx.merge(lab, on="transaction_id").merge(sp, on="transaction_id").merge(change_features(path), on="transaction_id")
    for name in ("rules2.pkl", "rules.pkl"):
        cache = path / "_cache" / name
        if cache.exists():
            df = df.merge(pd.read_pickle(cache)[["transaction_id", "rule_graph"]], on="transaction_id", how="left")
            break
    ust = path / "_cache" / "ustack.pkl"
    if ust.exists():
        df = df.merge(pd.read_pickle(ust)[["transaction_id", "u_entity"]], on="transaction_id", how="left")
    t = pd.to_datetime(df.posted_at, utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    df["week"] = (t - pd.Timestamp("2024-01-01")).dt.days // 7
    df["is_fraud"] = df.is_fraud.astype(int)
    return df


def slot_policy(te, channels, per_slot=1):
    """Fill each company-week budget one slot per channel, skipping rows already chosen."""
    chosen = np.zeros(len(te), dtype=bool)
    for k, score in enumerate(channels):
        s = np.where(chosen, -np.inf, np.asarray(score, dtype=float) + tie_break(len(te), 10 + k))
        chosen |= weekly_alerts(te, s, per_slot) & ~chosen
    return chosen


def evaluate(df):
    tr, va, te = (df[df.split == s] for s in ("train", "validation", "test"))
    ed = EntityDeviation2().fit(tr, tr.txn_type.to_numpy())
    channels = {"ED2": (ed.score(va, va.txn_type.to_numpy()), ed.score(te, te.txn_type.to_numpy()))}
    if "rule_graph" in df:
        channels["Rules"] = (va.rule_graph.fillna(0).to_numpy(), te.rule_graph.fillna(0).to_numpy())
    if "u_entity" in df:
        channels["Entity(v4)"] = (va.u_entity.fillna(0).to_numpy(), te.u_entity.fillna(0).to_numpy())
    ranks = {k: empirical_rank(np.sort(v), t) for k, (v, t) in channels.items()}
    combos = dict(ranks)
    if "Rules" in ranks and "Entity(v4)" in ranks:
        combos["Novelty old max(R,E)"] = np.maximum(ranks["Rules"], ranks["Entity(v4)"])
        combos["Cold new max(R,E,ED2)"] = np.maximum(combos["Novelty old max(R,E)"], ranks["ED2"])
    te = te.reset_index(drop=True)
    pos = te.is_fraud.to_numpy() == 1
    hard = (te.hard_negative_type.to_numpy() != "") & ~pos
    alerts = {name: weekly_alerts(te, score + tie_break(len(te), 5), 3) for name, score in combos.items()}
    if {"Rules", "Entity(v4)"} <= set(ranks):
        # one slot per channel per company-week, taken in a fixed order
        alerts["Slots R|E|ED2"] = slot_policy(te, [ranks["Rules"], ranks["Entity(v4)"], ranks["ED2"]])
        alerts["Slots R|E (2+1)"] = slot_policy(te, [ranks["Rules"], ranks["Entity(v4)"], ranks["Rules"]])
    out = {}
    for name, a in alerts.items():
        fam = {f: round(float(a[pos & (te.fraud_type.to_numpy() == f)].mean()), 3) for f in sorted(set(te.fraud_type[pos]))}
        out[name] = dict(recall=round(float(a[pos].mean()), 4), hard_negative_alert_rate=round(float(a[hard].mean()), 4),
                         by_family=fam)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("worlds", type=Path, nargs="+")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    res = {"data_origin": "dữ liệu tổng hợp", "status": "diagnostic_not_selection"}
    for w in a.worlds:
        res[w.name] = evaluate(world(w))
        print(w.name, {k: (v["recall"], v["hard_negative_alert_rate"]) for k, v in res[w.name].items()}, flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
