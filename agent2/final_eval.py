"""Cross-world evaluation of deployable configurations.

A 'world' = one synthetic population (8 companies, 2 years). A detector is *pretrained* on other worlds (labels allowed
there) and applied to a target world it has never seen, where only label-free fitting is allowed (entity baselines are
fitted on the target's own training period, reference ranks on its validation period).

Configurations (budget = 3 alerts per company-week; 'x+y' = x slots from the first voice, y slots from the novelty voice):
  Rules (friend)            hand-weighted 31 rules + graph
  Novelty                   max-rank fusion of Rules and EntityDeviation (no pretraining at all: cold start)
  CES                       calibrated evidence stack (14 weights pretrained on other worlds)
  CES 2+1 / CES 1+2         exploit/explore split
  L3                        LightGBM on friend190 + engineered + rule hits, pretrained on other worlds
  L3 2+1                    exploit/explore split
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import methods as M
from .alerting import select_mixed
from .data import load
from .metrics import evaluate_scores, operating_point, weekly_alerts, tie_break

warnings.filterwarnings("ignore")
CONFIGS = ["Rules (friend)", "Novelty (cold start)", "CES", "CES 2+1", "CES 1+2", "L3", "L3 2+1",
           "B1 Novelty", "B1 CES", "B1 L3", "B2 CES 1+1", "B2 L3 1+1"]


def pretrain(worlds: list[pd.DataFrame], drop_family: str | None = None):
    sets = M.supervised_sets()
    pool = pd.concat([w[w.split.isin(["train", "validation"])] for w in worlds], ignore_index=True)
    if drop_family:
        pool = pool[pool.fraud_type != drop_family]
    l3 = M.Supervised(sets["friend190+eng+rules"], "L3", grid=((7, .05),)).fit(pool, None)
    ces = M.CalibratedStack().fit_worlds(worlds, drop_family)
    return ces, l3


def score_target(target: pd.DataFrame, ces, l3, mask=None):
    tr, va = target[target.split == "train"], target[target.split == "validation"]
    te = target[target.split == "test"]
    if mask is not None:
        te = te[mask(te)]
    ent = M.EntityDeviation().fit(tr, va)
    rr = M.empirical_rank(va["rule_graph"].to_numpy(), te["rule_graph"].to_numpy())
    ee = M.empirical_rank(ent.score(va), ent.score(te))
    novelty = np.maximum(rr, ee) + 1e-3 * (rr + ee) / 2
    stack = ces.score(te, ent)
    l3s = l3.score(te)
    return te.reset_index(drop=True), dict(rules=te["rule_graph"].to_numpy(dtype=float), novelty=novelty, stack=stack, l3=l3s)


def configs_alerts(te: pd.DataFrame, s: dict):
    top_b = lambda score, b: weekly_alerts(te, np.asarray(score) + tie_break(len(te), 5), b)
    top3 = lambda score: top_b(score, 3)
    return {
        "Rules (friend)": top3(s["rules"]), "Novelty (cold start)": top3(s["novelty"]), "CES": top3(s["stack"]),
        "CES 2+1": select_mixed(te, s["stack"], s["novelty"], 2, 1), "CES 1+2": select_mixed(te, s["stack"], s["novelty"], 1, 2),
        "L3": top3(s["l3"]), "L3 2+1": select_mixed(te, s["l3"], s["novelty"], 2, 1),
        "B1 Novelty": top_b(s["novelty"], 1), "B1 CES": top_b(s["stack"], 1), "B1 L3": top_b(s["l3"], 1),
        "B2 CES 1+1": select_mixed(te, s["stack"], s["novelty"], 1, 1), "B2 L3 1+1": select_mixed(te, s["l3"], s["novelty"], 1, 1)}


def evaluate_world(target, worlds, drop_family=None, only_family=None):
    ces, l3 = pretrain(worlds, drop_family)
    mask = None
    if only_family:
        mask = lambda te: (te.fraud_type == only_family) | (te.is_fraud == 0)
    te, s = score_target(target, ces, l3, mask)
    out = {}
    for name, alerts in configs_alerts(te, s).items():
        op = operating_point(te, alerts)
        out[name] = {k: op[k] for k in ("alerts", "tp", "precision", "recall", "case_recall", "hard_neg_alert_rate", "entity_precision", "entity_alerts")}
    if only_family is None:
        out["_ap"] = {"Rules (friend)": evaluate_scores(te, s["rules"])["ap"], "Novelty (cold start)": evaluate_scores(te, s["novelty"])["ap"],
                      "CES": evaluate_scores(te, s["stack"])["ap"], "L3": evaluate_scores(te, s["l3"])["ap"]}
        pos = te.is_fraud.to_numpy() == 1
        fam = {}
        for f in sorted(te.loc[pos, "fraud_type"].unique()):
            row = {}
            for name, alerts in configs_alerts(te, s).items():
                m = pos & (te.fraud_type.to_numpy() == f)
                row[name] = float(alerts[m].mean())
            fam[f] = row
        out["_family_recall"] = fam
    return out, ces


def run_dev(paths: list[Path], out: Path):
    worlds = {p.name: load(p) for p in paths}
    result = {}
    for name in worlds:
        others = [w for n, w in worlds.items() if n != name]
        res, ces = evaluate_world(worlds[name], others)
        result[name] = dict(in_distribution=res, unseen_family={})
        fams = sorted(f for f in worlds[name].fraud_type.unique() if f)
        for f in fams:
            r, _ = evaluate_world(worlds[name], others, drop_family=f, only_family=f)
            result[name]["unseen_family"][f] = r
        print(name, "done", {k: round(v["recall"], 3) for k, v in res.items() if not k.startswith("_")}, flush=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def run_sealed(dev: list[Path], sealed: list[Path], out: Path):
    worlds = [load(p, need_text=False) for p in dev]
    ces, l3 = pretrain(worlds)
    result = {"ces_weights": {k: float(v) for k, v in ces.weights().items()}}
    for p in sealed:
        t = load(p)
        te, s = score_target(t, ces, l3)
        res = {}
        pos = te.is_fraud.to_numpy() == 1
        for name, alerts in configs_alerts(te, s).items():
            op = operating_point(te, alerts)
            res[name] = {k: op[k] for k in ("alerts", "tp", "precision", "recall", "case_recall", "hard_neg_alert_rate", "entity_precision", "entity_alerts")}
            res[name]["by_family_recall"] = {f: float(alerts[pos & (te.fraud_type.to_numpy() == f)].mean()) for f in sorted(te.loc[pos, "fraud_type"].unique())}
        res["_ap"] = {"Rules (friend)": evaluate_scores(te, s["rules"])["ap"], "Novelty (cold start)": evaluate_scores(te, s["novelty"])["ap"],
                      "CES": evaluate_scores(te, s["stack"])["ap"], "L3": evaluate_scores(te, s["l3"])["ap"]}
        result[p.name] = res
        print(p.name, {k: round(v["recall"], 3) for k, v in res.items() if not k.startswith("_")}, flush=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["dev", "sealed"])
    ap.add_argument("--dev", type=Path, nargs="+", required=True)
    ap.add_argument("--sealed", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.mode == "dev":
        run_dev(a.dev, a.out)
    else:
        run_sealed(a.dev, a.sealed, a.out)


if __name__ == "__main__":
    main()
