"""Method study on world v4 (dev worlds only; the sealed v4 worlds are evaluated once by `--sealed`).

Protocols
  P1 temporal      train 2024, validation H1 2025 (early stopping, reference ranks), test H2 2025
  P2 unseen branch for each ACFE branch: its labels are hidden in train and validation (rows kept, labelled 0, i.e.
                   undiscovered fraud in the history), test = that branch's fraud rows + all legitimate rows
  P3 new firm      supervised parts trained on the other dev worlds; label-free parts fitted on the target's own history
Every candidate and every alert policy is listed in CANDIDATES / POLICIES before any run; the selection rule is in
AGENT2_WORKLOG.md (section 14) and is applied to P1 and P2 means over the dev worlds.
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import methods as M
from .alerting import select_mixed
from .data import load
from .hybrid import FEATURE_SETS, LGBM, Collective, Novelty, attach_unsupervised
from .metrics import evaluate_scores, operating_point, tie_break, weekly_alerts
from .world_v4_schemes import SCHEMES

warnings.filterwarnings("ignore")
F = FEATURE_SETS

CANDIDATES = {
    "Rules+Graph (friend)": lambda: M.RuleScore("rule_graph", "Rules+Graph"),
    "Novelty max(R,E)": lambda: Novelty(("rule_graph", "u_entity"), "Novelty max(R,E)"),
    "Novelty max(R,E,AE)": lambda: Novelty(("rule_graph", "u_entity", "u_ae_r"), "Novelty max(R,E,AE)"),
    "L3": lambda: LGBM(F["L3"], "L3"),
    "L3-FB": lambda: LGBM(F["L3"], "L3-FB", balance="family"),
    "L4": lambda: LGBM(F["L4"], "L4"),
    "L4-FB": lambda: LGBM(F["L4"], "L4-FB", balance="family"),
    "C-L4": lambda: Collective(lambda: LGBM(F["L4"], "s1", grid=((15, .05),)), "C-L4"),
    "C-L4-FB": lambda: Collective(lambda: LGBM(F["L4"], "s1", balance="family", grid=((15, .05),)), "C-L4-FB"),
}
SUPERVISED = ["L3", "L3-FB", "L4", "L4-FB", "C-L4", "C-L4-FB"]
NOVELTY = ["Novelty max(R,E)", "Novelty max(R,E,AE)"]
# alert policies built from the scores above: (name, kind, args)
POLICIES = [(f"{s} 2+1 {n.split()[0][0]}{n.split(' ', 1)[1]}", "slots", (s, n, 2, 1)) for s in SUPERVISED for n in NOVELTY] + \
           [(f"max({s},{n.split(' ', 1)[1]})", "max", (s, n)) for s in ("L3", "L4-FB", "C-L4-FB") for n in NOVELTY[:1]]
KEEP = ("alerts", "tp", "precision", "recall", "case_recall", "hard_neg_alert_rate", "entity_precision", "median_delay_days")
WORKERS = 1


def prepare(path: Path) -> pd.DataFrame:
    df = attach_unsupervised(load(path), Path(path) / "_cache" / "ustack.pkl")
    # identifiers restart in every synthetic world; prefix them so pooled worlds never share a row or company key
    tag = Path(path).name + ":"
    df = df.drop(columns=[c for c in ("explanation_vi", "rule_ids") if c in df.columns])
    wide = df.select_dtypes("float64").columns
    df[wide] = df[wide].astype(np.float32)               # halves memory; LightGBM works in float32 anyway
    return df.assign(transaction_id=tag + df["transaction_id"], company_id=tag + df["company_id"])


def branch_of(fraud_type: pd.Series) -> pd.Series:
    return fraud_type.map(lambda f: SCHEMES[f][0] if f in SCHEMES else ("" if not f else "other"))


def summarise(te, alerts_by_name, scores_by_name, per_family=True):
    out = {}
    pos = te.is_fraud.to_numpy() == 1
    fam = te.fraud_type.to_numpy()
    diff = te.difficulty.to_numpy()
    for name, alerts in alerts_by_name.items():
        op = operating_point(te, alerts)
        res = {k: op[k] for k in KEEP}
        if name in scores_by_name:
            ev = evaluate_scores(te, scores_by_name[name])
            res.update(ap=ev["ap"], B1_precision=ev["B1"]["precision"], B1_recall=ev["B1"]["recall"])
        if per_family and pos.any():
            res["by_family"] = {f: float(alerts[pos & (fam == f)].mean()) for f in sorted(set(fam[pos]))}
            res["by_difficulty"] = {d: float(alerts[pos & (diff == d)].mean()) for d in sorted(set(diff[pos]))}
        out[name] = res
    return out


def run_candidates(train, valid, test, names=None, history=None, ref_for_novelty=None):
    """Fit every candidate on (train, valid); score test. Returns scores on test and on valid."""
    s_te, s_va, secs = {}, {}, {}
    def run(name):
        t0 = time.time()
        m = CANDIDATES[name]()
        if isinstance(m, Novelty):
            m.fit(None, ref_for_novelty if ref_for_novelty is not None else valid)
        else:
            m.fit(train, valid)
            if history is not None and isinstance(m, Collective):
                m.set_history(history)
        te_score = m.score(test)
        va_score = m.score(ref_for_novelty if ref_for_novelty is not None else valid)
        return te_score, va_score, round(time.time() - t0, 1)
    ordered_names = list(names or CANDIDATES)
    if WORKERS == 1:
        fitted = map(run, ordered_names)
        for name, (te_score, va_score, elapsed) in zip(ordered_names, fitted):
            s_te[name], s_va[name], secs[name] = te_score, va_score, elapsed
    else:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for name, (te_score, va_score, elapsed) in zip(ordered_names, pool.map(run, ordered_names)):
                s_te[name], s_va[name], secs[name] = te_score, va_score, elapsed
    return s_te, s_va, secs


def alerts_for(te, s_te, s_va, budget=3):
    top = lambda s: weekly_alerts(te, np.asarray(s, dtype=float) + tie_break(len(te), 5), budget)
    alerts = {k: top(v) for k, v in s_te.items()}
    scores = dict(s_te)
    for name, kind, args in POLICIES:
        if any(a not in s_te for a in args[:2]):
            continue
        if kind == "slots":
            s, n, a, b = args
            alerts[name] = select_mixed(te, s_te[s], s_te[n], a, b)
        else:
            s, n = args
            fused = np.maximum(M.empirical_rank(s_va[s], s_te[s]), M.empirical_rank(s_va[n], s_te[n]))
            scores[name] = fused
            alerts[name] = top(fused)
    return alerts, scores


def p1_temporal(df, save_alerts=None):
    tr, va, te = (df[df.split == s] for s in ("train", "validation", "test"))
    s_te, s_va, secs = run_candidates(tr, va, te)
    te = te.reset_index(drop=True)
    alerts, scores = alerts_for(te, s_te, s_va)
    if save_alerts is not None:
        np.savez_compressed(save_alerts, names=np.asarray(list(alerts), dtype=str),
                            alerts=np.stack(list(alerts.values())),
                            company_id=te.company_id.to_numpy(dtype=str),
                            case_id=te.case_id.fillna("").to_numpy(dtype=str),
                            transaction_id=te.transaction_id.to_numpy(dtype=str),
                            is_fraud=te.is_fraud.to_numpy(dtype=int))
    res = summarise(te, alerts, scores)
    for k, v in secs.items():
        res[k]["seconds"] = v
    return res


def p2_unseen_branch(df):
    br = branch_of(df.fraud_type)
    out = {}
    for b in sorted(x for x in br.unique() if x):
        hide = (br == b).to_numpy()
        masked = df.copy()
        masked.loc[hide, ["is_fraud"]] = 0
        masked.loc[hide, ["fraud_type"]] = ""
        tr, va = masked[masked.split == "train"], masked[masked.split == "validation"]
        te = df[(df.split == "test") & (hide | (df.is_fraud == 0).to_numpy())].reset_index(drop=True)
        if te.is_fraud.sum() == 0:
            continue
        s_te, s_va, _ = run_candidates(tr, va, te)
        alerts, scores = alerts_for(te, s_te, s_va)
        out[b] = summarise(te, alerts, scores)
        print(f"     P2 {b:20s} n={int(te.is_fraud.sum()):3d} " + " ".join(f"{k}={out[b][k]['recall']:.2f}" for k in ("L3", "L4-FB", "C-L4-FB")), flush=True)
    return out


def p3_new_firm(target, others):
    pool_tr = pd.concat([o[o.split == "train"] for o in others], ignore_index=True)
    pool_va = pd.concat([o[o.split == "validation"] for o in others], ignore_index=True)
    tr, va, te = (target[target.split == s] for s in ("train", "validation", "test"))
    s_te, s_va, _ = run_candidates(pool_tr, pool_va, te, history=[tr, va], ref_for_novelty=va)
    te = te.reset_index(drop=True)
    alerts, scores = alerts_for(te, s_te, s_va)
    return summarise(te, alerts, scores)


def main():
    global WORKERS
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--protocols", default="P1,P2,P3")
    p.add_argument("--save-alerts", action="store_true", help="Save P1 row decisions for paired bootstrap")
    p.add_argument("--workers", type=int, default=1, choices=(1, 2, 3), help="Concurrent independent candidate fits; model parameters unchanged")
    a = p.parse_args()
    WORKERS = a.workers
    a.out.mkdir(parents=True, exist_ok=True)
    protos = a.protocols.split(",")
    target = lambda path: a.out / f"{path.name}.json"
    read = lambda path: json.loads(target(path).read_text(encoding="utf-8")) if target(path).exists() else {"dataset": path.name}

    def save(path, res):
        res["candidate_workers"] = WORKERS
        target(path).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    for path in a.data:                                   # P1 and P2 need one world in memory at a time
        res = read(path)
        todo = [x for x in protos if x in ("P1", "P2") and x not in res]
        if not todo:
            continue
        df = prepare(path)
        for proto in todo:
            t0 = time.time()
            print("==", path.name, proto, flush=True)
            if proto == "P1":
                res[proto] = p1_temporal(df, a.out / f"{path.name}_P1_alerts.npz" if a.save_alerts else None)
                print("   " + " | ".join(f"{k} R={v['recall']:.2f}" for k, v in res[proto].items()), flush=True)
            else:
                res[proto] = p2_unseen_branch(df)
            res[f"{proto}_seconds"] = round(time.time() - t0)
            save(path, res)
        del df
    if "P3" in protos and any("P3" not in read(x) for x in a.data):
        worlds = {x.name: prepare(x) for x in a.data}
        for path in a.data:
            res = read(path)
            if "P3" in res:
                continue
            t0 = time.time()
            print("==", path.name, "P3", flush=True)
            res["P3"] = p3_new_firm(worlds[path.name], [w for n, w in worlds.items() if n != path.name])
            print("   " + " | ".join(f"{k} R={v['recall']:.2f}" for k, v in res["P3"].items()), flush=True)
            res["P3_seconds"] = round(time.time() - t0)
            save(path, res)


if __name__ == "__main__":
    main()
