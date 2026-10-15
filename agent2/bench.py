"""Benchmark runner: temporal protocol, leave-one-family-out, leave-one-company-out, multi-seed aggregation."""
from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import methods as M
from .data import load
from .metrics import bootstrap_ap, evaluate_scores, per_group_recall

warnings.filterwarnings("ignore")


def build_methods(seed=0, quick=False):
    sets = M.supervised_sets()
    rg = lambda: M.RuleScore("rule_graph", "rg")
    full = lambda: M.Supervised(sets["friend190+eng+rules"], "L3", seed=seed)
    ms = [
        M.RuleScore("rule_direct", "Rules"),
        M.RuleScore("rule_graph", "Rules+Graph"),
        M.IForest(M.friend_columns, name="IF[friend190] (friend baseline)", seed=seed),
        M.IForest(name="IF[U]", seed=seed),
        M.ECOD(name="ECOD[U]"),
        M.HBOS(name="HBOS[U]"),
        M.EntityDeviation(name="EntityDeviation"),
        M.Gate(rg(), M.ECOD(name="ECOD-g"), eps=.5, name="Gate(Rules,ECOD)"),
        M.Blend([rg(), M.IForest(M.friend_columns, name="IFf", seed=seed)], [.8, .2], "Blend .8 Rules + .2 IF (friend ensemble)"),
        M.RankFusion([rg(), M.EntityDeviation(name="e")], "max", name="Fusion max(Rules,Entity)"),
        M.RuleLogit(),
        M.Supervised(sets["friend190"], "LGBM[friend190]", seed=seed),
        M.Supervised(sets["friend190+eng"], "LGBM[friend190+eng]", seed=seed),
        M.Supervised(sets["friend190+eng+rules"], "LGBM[friend190+eng+rules]", seed=seed),
        M.RankFusion([full(), rg(), M.EntityDeviation(name="e2")], "max", name="Fusion max(L3,Rules,Entity)"),
    ]
    if not quick:
        ms.insert(5, M.Autoencoder(name="AE[U]", seed=seed))
        ms.append(M.RankFusion([rg(), M.EntityDeviation(name="e3"), M.Autoencoder(name="ae3", seed=seed)], "max",
                               name="Fusion max(Rules,Entity,AE)"))
    return ms


def slim(res):
    return {k: v for k, v in res.items()}


def run_temporal(df, methods, seed=0, boot=True):
    tr, va, te = (df[df.split == s] for s in ("train", "validation", "test"))
    out = {}
    for m in methods:
        t0 = time.time()
        m.fit(tr, va)
        s_te = m.score(te)
        res = evaluate_scores(te, s_te, seed=seed)
        res["regime"] = m.regime
        res["by_family_B3"] = per_group_recall(te, s_te, "fraud_type", 3, seed)
        res["by_difficulty_B3"] = per_group_recall(te, s_te, "difficulty", 3, seed)
        res["val_ap"] = evaluate_scores(va, m.score(va), seed=seed)["ap"]
        if boot:
            res["ap_ci95"] = bootstrap_ap(te, s_te, reps=100, seed=seed)
        res["fit_score_seconds"] = round(time.time() - t0, 1)
        out[m.name] = res
        print(f"   {m.name:46s} AP={res['ap']:.3f} Rprec={res['r_precision']:.3f} "
              f"B1 P={res['B1']['precision']:.2f} R={res['B1']['recall']:.2f} | B3 P={res['B3']['precision']:.2f} "
              f"R={res['B3']['recall']:.2f} case={res['B3']['case_recall']:.2f} ({res['fit_score_seconds']}s)", flush=True)
    return out


def run_leave_family_out(df, seed=0):
    """Supervised only: drop one fraud family from training, test on that family (plus all legitimate rows)."""
    sets = M.supervised_sets()
    fams = sorted(f for f in df.fraud_type.unique() if f)
    out = {}
    for fam in fams:
        hide = df[(df.fraud_type == fam)].index
        train = df[(df.split == "train") & ~df.index.isin(hide)]
        valid = df[(df.split == "validation") & ~df.index.isin(hide)]
        test = df[(df.split == "test") & ((df.fraud_type == fam) | (df.is_fraud == 0))]
        rg = lambda: M.RuleScore("rule_graph", "rg")
        full = lambda: M.Supervised(sets["friend190+eng+rules"], "L3", seed=seed)
        zoo = [M.Supervised(sets["friend190"], "LGBM[friend190]", seed=seed), full(),
               M.RuleScore("rule_graph", "Rules+Graph"), M.EntityDeviation(name="EntityDeviation"),
               M.RankFusion([rg(), M.EntityDeviation(name="e")], "max", name="Fusion max(Rules,Entity)"),
               M.RankFusion([full(), rg(), M.EntityDeviation(name="e2")], "max", name="Fusion max(L3,Rules,Entity)")]
        for m in zoo:
            m.fit(train, valid)
            res = evaluate_scores(test, m.score(test), seed=seed)
            out.setdefault(fam, {})[m.name] = dict(ap=res["ap"], B3_recall=res["B3"]["recall"], B3_precision=res["B3"]["precision"],
                                                   positives=res["positives"])
    return out


def run_leave_company_out(df, seed=0):
    sets = M.supervised_sets()
    keep = ["friend190", "friend190+eng", "friend190+eng+rules"]
    out = {}
    for k in keep:
        aps, parts = [], []
        for company in sorted(df.company_id.unique()):
            train = df[(df.split == "train") & (df.company_id != company)]
            valid = df[(df.split == "validation") & (df.company_id != company)]
            test = df[(df.split == "test") & (df.company_id == company)]
            if test.is_fraud.sum() == 0:
                continue
            m = M.Supervised(sets[k], f"LGBM[{k}]", seed=seed).fit(train, valid)
            parts.append((test, m.score(test)))
        test_all = pd.concat([p[0] for p in parts])
        score_all = np.concatenate([p[1] for p in parts])
        res = evaluate_scores(test_all, score_all, seed=seed)
        out[f"LGBM[{k}]"] = dict(ap=res["ap"], r_precision=res["r_precision"], B3_precision=res["B3"]["precision"],
                                 B3_recall=res["B3"]["recall"], positives=res["positives"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-transfer", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.data:
        target = args.out / f"{path.name}.json"
        if target.exists():
            print("skip (done):", path.name)
            continue
        print("==", path.name, flush=True)
        df = load(path)
        result = dict(dataset=path.name, temporal=run_temporal(df, build_methods(quick=args.quick)))
        if not args.skip_transfer:
            result["leave_family_out"] = run_leave_family_out(df)
            result["leave_company_out"] = run_leave_company_out(df)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
