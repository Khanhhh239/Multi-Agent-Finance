"""One-shot evaluation on the sealed v4 worlds (see AGENT2_WORKLOG.md section 14).

S1 in-firm   the firm's own history (train 2024, validation H1 2025) is labelled only for the 30 development schemes; rows
             of the 7 new schemes stay in the history labelled 0 (undiscovered). Test = H2 2025, every fraud counts.
S2 new firm  supervised parts trained on the three development worlds; label-free parts and the collective history use
             the sealed firm's own earlier periods without labels.
Alerts are always chosen on the full test period (all schemes compete for the same weekly budget); recall is then
reported overall, for the 30 known schemes and for the 7 new schemes. Refuses to run twice or before the freeze file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import eval_v4

from .eval_v4 import KEEP, alerts_for, prepare, run_candidates
from .metrics import evaluate_scores, operating_point
from .world_v4_sealed import NOVEL

NEW_DECOYS = ("legit_volume_discount", "legit_extra_withdrawal", "legit_overtime_peak", "legit_new_lease", "legit_tax_installment")
FROZEN_FILES = ("agent2/hybrid.py", "agent2/eval_v4.py", "agent2/methods.py", "agent2/feats_v4.py", "agent2/feats.py", "agent2/data.py")


def file_hashes(root: Path):
    return {f: hashlib.sha256((root / f).read_bytes()).hexdigest()[:16] for f in FROZEN_FILES}


def report(te: pd.DataFrame, alerts: dict, scores: dict):
    pos = te.is_fraud.to_numpy() == 1
    novel = te.fraud_type.isin(list(NOVEL)).to_numpy()
    decoy_new = te.hard_negative_type.isin(NEW_DECOYS).to_numpy()
    fam = te.fraud_type.to_numpy()
    out = {}
    for name, a in alerts.items():
        op = operating_point(te, a)
        res = {k: op[k] for k in KEEP}
        if name in scores:
            res["ap"] = evaluate_scores(te, scores[name])["ap"]
        for tag, m in (("known", pos & ~novel), ("novel", pos & novel)):
            sub = te[m | ~pos]
            res[f"{tag}_recall"] = float(a[m].mean()) if m.any() else float("nan")
            res[f"{tag}_case_recall"] = operating_point(sub.reset_index(drop=True), a[m | ~pos])["case_recall"]
        res["new_decoy_alert_rate"] = float(a[decoy_new].mean()) if decoy_new.any() else float("nan")
        res["by_family"] = {f: float(a[pos & (fam == f)].mean()) for f in sorted(set(fam[pos]))}
        out[name] = res
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dev", type=Path, nargs="+", required=True)
    p.add_argument("--sealed", type=Path, nargs="+", required=True)
    p.add_argument("--frozen", type=Path, default=Path("work/results/v4_frozen.json"))
    p.add_argument("--out", type=Path, default=Path("work/results/sealed_v4.json"))
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists: the sealed worlds are evaluated once only")
    frozen = json.loads(a.frozen.read_text(encoding="utf-8"))
    now = file_hashes(Path("."))
    if now != frozen["hashes"]:
        raise SystemExit(f"code changed after the freeze: {now} != {frozen['hashes']}")
    eval_v4.WORKERS = frozen.get("candidate_workers", 1)
    # Check the output location before any scoring. Persist the complete result
    # before exposing metrics, so a final write failure cannot leak a lost run.
    a.out.parent.mkdir(parents=True, exist_ok=True)
    dev = [prepare(x) for x in a.dev]
    result = {"frozen": frozen, "worlds": {}}
    for path in a.sealed:
        df = prepare(path)
        novel = df.fraud_type.isin(list(NOVEL))
        masked = df.copy()
        masked.loc[novel.to_numpy(), "is_fraud"] = 0
        masked.loc[novel.to_numpy(), "fraud_type"] = ""
        tr, va = masked[masked.split == "train"], masked[masked.split == "validation"]
        te = df[df.split == "test"]
        s_te, s_va, _ = run_candidates(tr, va, te)
        te_r = te.reset_index(drop=True)
        al, sc = alerts_for(te_r, s_te, s_va)
        r1 = report(te_r, al, sc)
        pool_tr = pd.concat([d[d.split == "train"] for d in dev], ignore_index=True)
        pool_va = pd.concat([d[d.split == "validation"] for d in dev], ignore_index=True)
        s_te2, s_va2, _ = run_candidates(pool_tr, pool_va, te, history=[df[df.split == "train"], df[df.split == "validation"]],
                                         ref_for_novelty=df[df.split == "validation"])
        al2, sc2 = alerts_for(te_r, s_te2, s_va2)
        r2 = report(te_r, al2, sc2)
        result["worlds"][path.name] = {"S1": r1, "S2": r2, "test_fraud_rows": int(te.is_fraud.sum()),
                                       "test_novel_rows": int(te.fraud_type.isin(list(NOVEL)).sum())}
    with a.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=1))
    c = frozen["chosen"]
    for name, world in result["worlds"].items():
        print(name, "S1", c, {k: round(world["S1"][c][k], 3) for k in ("recall", "known_recall", "novel_recall", "case_recall", "hard_neg_alert_rate")},
              "S2", {k: round(world["S2"][c][k], 3) for k in ("recall", "known_recall", "novel_recall", "case_recall")}, flush=True)


if __name__ == "__main__":
    main()
