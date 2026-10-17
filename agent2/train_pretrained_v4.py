"""Train the frozen v4 policy after the one-shot evaluation has been recorded.

Uses development worlds 411/412 only; world 413 remains a reported holdout.
No sealed world may be supplied for training or holdout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

from . import methods as M
from .deployment_v4 import PreparedV4Detector, policy_components, serializable_model
from .eval_v4 import CANDIDATES, SUPERVISED, prepare
from .metrics import evaluate_scores, operating_point
from .repro_v4 import environment
from .sealed_v4 import compact_integer_storage, file_hashes


def train(worlds, holdout, frozen_path, sealed_report, out):
    worlds, holdout, out = [Path(w) for w in worlds], Path(holdout), Path(out)
    if {w.name for w in worlds} != {"w4_s411", "w4_s412"} or len(worlds) != 2 or holdout.name != "w4_s413":
        raise ValueError("A6 trains on development 411/412 and holds out development 413")
    if out.exists():
        raise FileExistsError(f"refusing to overwrite pretrained model: {out}")
    frozen = json.loads(Path(frozen_path).read_text(encoding="utf-8"))
    sealed = json.loads(Path(sealed_report).read_text(encoding="utf-8"))
    if sealed.get("frozen") != frozen or set(sealed.get("worlds", {})) != {"s4_s931", "s4_s932", "s4_s933"}:
        raise ValueError("A5 complete one-shot report must match the frozen configuration")
    if file_hashes(Path(".")) != frozen["hashes"]:
        raise ValueError("frozen code differs; do not silently train another implementation")
    for scenario in ('S1', 'S2'):
        values = np.asarray([[w[scenario][frozen['chosen']]['recall'], w[scenario][frozen['chosen']]['hard_neg_alert_rate']]
                             for w in sealed['worlds'].values()], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError('M2 metrics undefined; training is forbidden')
        recall, hard_negative = values.mean(axis=0)
        if recall < .50 or hard_negative > .25:
            raise ValueError('M2 global stop condition met; training is forbidden')
    frames = [compact_integer_storage(prepare(w)) for w in worlds]
    pool_tr = pd.concat([f[f.split == "train"] for f in frames], ignore_index=True)
    pool_va = pd.concat([f[f.split == "validation"] for f in frames], ignore_index=True)
    needed = set(policy_components(frozen["chosen"])) | {"L3"}
    models = {}
    for name in SUPERVISED:
        if name in needed:
            print("train", name, flush=True)
            models[name] = serializable_model(CANDIDATES[name]().fit(pool_tr, pool_va))
    ces = M.CalibratedStack().fit_worlds(frames)
    meta = {"data_kind": "synthetic", "trained_at": dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
            "training_worlds": [w.name for w in worlds], "holdout_world": holdout.name,
            "labelled_rows": len(pool_tr) + len(pool_va), "positives": int(pool_tr.is_fraud.sum() + pool_va.is_fraud.sum()),
            "code_hashes": file_hashes(Path(".")), "environment": environment(),
            "feature_columns": {name: list(model.cols if hasattr(model, "cols") else model.base.cols) for name, model in models.items()},
            "parameters": {name: model.model.get_params() for name, model in models.items()},
            "ces_detector_count": len(ces.theta) - 2, "development_scores": frozen["dev_scores"],
            "limitations": ["synthetic data only; real-company performance is unverified",
                            "world 413 participated in A2 selection; it is held out from final training, not an independent selection test",
                            "target label-free signals require the target company's own past data",
                            "priority scores are not calibrated fraud probabilities"]}
    meta['holdout_is_independent_selection_test'] = False
    meta['artifact_status'] = 'synthetic_research_only'
    meta['accepted_for_real_company_use'] = False
    bundle = {"schema_version": 2, "frozen": frozen, "models": models, "ces": ces, "meta": meta}
    target = compact_integer_storage(prepare(holdout))
    tr, va, te = (target[target.split == s] for s in ("train", "validation", "test"))
    det = PreparedV4Detector(bundle, allow_multiple_companies=True).fit(tr, va)
    flags, score, _ = det.alerts(te.reset_index(drop=True))
    meta["holdout_operating_point"] = operating_point(te.reset_index(drop=True), flags)
    meta["holdout_priority_score_ap"] = evaluate_scores(te, score)["ap"]
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out)
    restored = joblib.load(out)
    restored_det = PreparedV4Detector(restored, allow_multiple_companies=True).fit(tr, va)
    before, after = det.score(te.iloc[:100]), restored_det.score(te.iloc[:100])
    for name in before:
        np.testing.assert_allclose(before[name], after[name], rtol=0, atol=0)
        if not np.isfinite(after[name]).all():
            raise ValueError("non-finite restored model scores")
    meta["reload_check_rows"] = min(100, len(te))
    meta["model_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    card = out.with_suffix(".card.json")
    card.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(meta["holdout_operating_point"], ensure_ascii=False), flush=True)
    return bundle


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worlds", type=Path, nargs="+", default=[Path("work/data/w4_s411"), Path("work/data/w4_s412")])
    p.add_argument("--holdout", type=Path, default=Path("work/data/w4_s413"))
    p.add_argument("--frozen", type=Path, default=Path("work/results/v4_frozen.json"))
    p.add_argument("--sealed-report", type=Path, default=Path("work/results/sealed_v4.json"))
    p.add_argument("--out", type=Path, default=Path("models/pretrained_v2.joblib"))
    p.add_argument("--config-out", type=Path, default=Path("configs/agent2_default.json"))
    a = p.parse_args()
    if a.config_out.exists():
        raise FileExistsError(f"configuration already exists: {a.config_out}")
    train(a.worlds, a.holdout, a.frozen, a.sealed_report, a.out)
    from .pipeline_v4 import make_config
    make_config(a.frozen, a.out, a.config_out)


if __name__ == "__main__":
    main()
