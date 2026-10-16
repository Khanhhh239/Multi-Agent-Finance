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
import gc
import time
import sys
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import eval_v4

from .eval_v4 import CANDIDATES, KEEP, alerts_for, prepare, run_candidates
from .metrics import evaluate_scores, operating_point
from .world_v4_sealed import NOVEL

NEW_DECOYS = ("legit_volume_discount", "legit_extra_withdrawal", "legit_overtime_peak", "legit_new_lease", "legit_tax_installment")
FROZEN_FILES = ("agent2/hybrid.py", "agent2/eval_v4.py", "agent2/methods.py", "agent2/feats_v4.py", "agent2/feats.py", "agent2/data.py")


def file_hashes(root: Path):
    return {f: hashlib.sha256((root / f).read_bytes()).hexdigest()[:16] for f in FROZEN_FILES}


def release_feature_caches():
    from sme_fraud import rules
    # These deterministic parse/normalisation caches are needed only while raw
    # rules execute. Long-lived small objects can otherwise pin large arenas.
    rules.parse.cache_clear()
    rules.normalize.cache_clear()
    gc.collect()


def available_commit_memory():
    if sys.platform != 'win32':
        return None
    import ctypes
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in ('total_physical', 'available_physical', 'total_commit',
                                                            'available_commit', 'total_virtual', 'available_virtual', 'extended')]]
    status = Status()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.available_commit)


def wait_for_memory(gib=2, timeout=1800):
    """Wait for other workloads; never terminate them or change system settings."""
    began, announced = time.monotonic(), False
    while True:
        free = available_commit_memory()
        if free is None or free >= gib * 1024**3:
            return
        if not announced:
            print(f'waiting for at least {gib} GiB of system commit headroom', flush=True)
            announced = True
        if time.monotonic() - began > timeout:
            raise MemoryError('insufficient system commit headroom; no detector metrics have been printed')
        gc.collect()
        time.sleep(5)


def compact_integer_storage(frame):
    """Losslessly store bounded integers; model matrices remain float32."""
    result = frame.copy(deep=False)
    for column in result.select_dtypes(include=['int64']).columns:
        values = result[column].to_numpy()
        if not len(values):
            continue
        low, high = values.min(), values.max()
        for dtype in (np.int8, np.int16, np.int32):
            bounds = np.iinfo(dtype)
            if low >= bounds.min and high <= bounds.max:
                small = values.astype(dtype)
                if not np.array_equal(values, small):
                    raise ValueError('integer compaction changed a value')
                result[column] = small
                break
    return result.copy()


def development_pool(paths, compact=False):
    # S2 never uses development test rows. Release them world by world, and
    # concatenate once rather than keeping three full worlds plus two copies
    # of their training/calibration rows alive during candidate fitting.
    history = []
    for path in paths:
        if compact:
            wait_for_memory()
        frame = prepare(path)
        if compact:
            frame = compact_integer_storage(frame)
        history.append(frame[frame.split.isin(["train", "validation"])].copy())
        del frame
        release_feature_caches()
    pooled = pd.concat(history, ignore_index=True)
    del history
    train = pooled[pooled.split == "train"].reset_index(drop=True)
    valid = pooled[pooled.split == "validation"].reset_index(drop=True)
    del pooled
    gc.collect()
    return train, valid


def run_bounded(train, valid, test, limit=None, **kwargs):
    """Bound execution memory without changing candidates, parameters or order."""
    if limit is None:
        return run_candidates(train, valid, test, **kwargs)
    names = list(CANDIDATES)
    scores, reference, seconds = {}, {}, {}
    for begin in range(0, len(names), limit):
        wait_for_memory()
        current, calibration, elapsed = run_candidates(train, valid, test, names=names[begin:begin + limit], **kwargs)
        scores.update(current)
        reference.update(calibration)
        seconds.update(elapsed)
        print('candidate batch completed:', ', '.join(current), flush=True)
        gc.collect()
    return scores, reference, seconds


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
    p.add_argument("--max-concurrent-candidates", type=int, choices=(1, 2, 3), default=None,
                   help="optional memory bound; candidates and fitted parameters stay frozen")
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
    if a.max_concurrent_candidates is not None:
        # Prepare one raw world at a time before allocating the S2 pool. This
        # uses the same existing deterministic feature caches, no metrics.
        for path in a.sealed:
            wait_for_memory(2 if (path / '_cache' / 'ustack.pkl').exists() else 6)
            print('preparing raw inputs:', path.name, flush=True)
            prepared = prepare(path)
            del prepared
            release_feature_caches()
    pool_tr, pool_va = development_pool(a.dev, compact=a.max_concurrent_candidates is not None)
    result = {"frozen": frozen, "worlds": {},
              "execution_max_concurrent_candidates": min(a.max_concurrent_candidates or eval_v4.WORKERS, eval_v4.WORKERS),
              'lossless_integer_compaction': a.max_concurrent_candidates is not None}
    for path in a.sealed:
        df = prepare(path)
        if a.max_concurrent_candidates is not None:
            df = compact_integer_storage(df)
        release_feature_caches()
        novel = df.fraud_type.isin(list(NOVEL))
        masked = df.copy()
        masked.loc[novel.to_numpy(), "is_fraud"] = 0
        masked.loc[novel.to_numpy(), "fraud_type"] = ""
        tr, va = masked[masked.split == "train"], masked[masked.split == "validation"]
        te = df[df.split == "test"]
        if a.max_concurrent_candidates is not None:
            print('scoring scenario:', path.name, 'S1', flush=True)
        s_te, s_va, _ = run_bounded(tr, va, te, a.max_concurrent_candidates)
        te_r = te.reset_index(drop=True)
        al, sc = alerts_for(te_r, s_te, s_va)
        r1 = report(te_r, al, sc)
        del masked, tr, va, s_te, s_va, al, sc
        gc.collect()
        if a.max_concurrent_candidates is not None:
            print('scoring scenario:', path.name, 'S2', flush=True)
        s_te2, s_va2, _ = run_bounded(pool_tr, pool_va, te, a.max_concurrent_candidates,
                                         history=[df[df.split == "train"], df[df.split == "validation"]],
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
