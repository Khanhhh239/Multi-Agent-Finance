"""R4: freeze the selected v5 configuration and evaluate the sealed v5 worlds exactly once (dữ liệu tổng hợp).

freeze  -> results/v5/v5_frozen.json: chosen supervised candidate, chosen Cold, PU weight, subsampling fraction,
           development S2 recall of the chosen candidate (for the dev-gap gate), SHA-256 of every agent2/ and
           sme_fraud/ module. Refuses if the pre-seal gate did not pass.
evaluate -> results/v5/sealed_v5.json: refuses to run twice or when any hashed module changed. The final S2 model
           is trained on ALL twenty development worlds (train split, validation for the leaf choice), five seeds
           averaged; the sealed target only provides label-free history to its own matrices.
Registered gates (R1 v1.1 section 5): V5-S2 mean recall >= 60%, novel >= 35%, each world >= 45%,
|sealed - dev S2 recall| <= 15 points, hard-negative alert rate <= 15% in each world; V5-Cold mean >= 35%,
novel >= 30%, each world >= 25%, hard <= 15% in each world.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import tie_break, weekly_alerts
from .runtime_v5 import limit_memory, write_json
from .screen_v5 import SourcePool, cold_scores

R2 = Path('results/v5/R2')
FROZEN = Path('results/v5/v5_frozen.json')
OUT = Path('results/v5/sealed_v5.json')


def code_hashes(root=Path('.')):
    files = sorted([*root.glob('agent2/*.py'), *root.glob('sme_fraud/*.py')])
    return {str(f.as_posix()): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def freeze():
    if FROZEN.exists():
        raise SystemExit(f'{FROZEN} exists; the configuration is already frozen')
    sel = json.loads((R2 / 'selection_summary.json').read_text(encoding='utf-8'))
    cold = json.loads((R2 / 'cold_selection.json').read_text(encoding='utf-8'))
    if not sel['gate']['passed']:
        raise SystemExit('pre-seal gate did not pass: sealed v5 worlds must not be generated or scored')
    chosen = sel['chosen']
    master = json.loads((R2 / 'master_state.json').read_text(encoding='utf-8'))
    frozen = {'supervised': chosen, 'cold': cold['chosen'] if cold['gate'] and cold['gate']['passed'] else None,
              'cold_gate_passed': bool(cold['gate'] and cold['gate']['passed']), 'w': sel['w'],
              'fraction': master['fraction'], 'dev_S2_recall_mean': sel['candidates'][chosen]['R_mean'],
              'hashes': code_hashes(), 'data_origin': 'dữ liệu tổng hợp'}
    write_json(FROZEN, frozen)
    return frozen


def recall(flags, mask):
    return float(flags[mask].mean()) if mask.any() else float('nan')


def case_bootstrap(te, flags, mask, reps=1000, seed=0):
    cases = te.loc[mask, 'case_id'].to_numpy()
    hit = flags[mask]
    ids, inv = np.unique(cases, return_inverse=True)
    tp, n = np.bincount(inv, weights=hit), np.bincount(inv)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(ids), size=(reps, len(ids)))
    stats = tp[draws].sum(1) / n[draws].sum(1)
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def evaluate(dev_matrices: Path, sealed_matrices: Path, sealed_seeds, novel, new_decoys, out_path=OUT):
    if out_path.exists():
        raise SystemExit(f'{out_path} exists: the sealed v5 worlds are evaluated once only')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if code_hashes() != frozen['hashes']:
        changed = sorted(k for k in set(code_hashes()) | set(frozen['hashes'])
                         if code_hashes().get(k) != frozen['hashes'].get(k))
        raise SystemExit(f'code changed after the freeze: {changed}')
    kind = frozen['supervised']
    base = 'L4-PU-E2-AR' if kind == 'L4-PU-E2-AR-2plus1' else kind
    out = {'frozen': frozen, 'worlds': {}, 'data_origin': 'dữ liệu tổng hợp'}
    for seed in sealed_seeds:
        tdir = sealed_matrices / f's{seed}'
        te = pd.read_parquet(tdir / 'test.parquet')
        pool = SourcePool(seed, dev_matrices, base, frozen['fraction'], target_dir=tdir)
        scores = np.mean([pool.fit_score(None, frozen['w'], s)[0] for s in range(5)], axis=0)
        del pool
        if kind.endswith('2plus1'):
            _, cold = cold_scores(sealed_matrices, seed, 'Cold-Rules-E2')
            first = weekly_alerts(te, scores + tie_break(len(te), 3), 2)
            flags = first | (weekly_alerts(te, np.where(first, -np.inf, cold + tie_break(len(te), 4)), 1) & ~first)
        else:
            flags = weekly_alerts(te, scores + tie_break(len(te), 5), 3)
        res = {'S2': measure(te, flags, novel, new_decoys)}
        if frozen['cold']:
            _, cs = cold_scores(sealed_matrices, seed, frozen['cold'])
            res['Cold'] = measure(te, weekly_alerts(te, cs + tie_break(len(te), 5), 3), novel, new_decoys)
        out['worlds'][str(seed)] = res
        print(seed, {k: round(v['recall'], 4) for k, v in res.items()}, flush=True)
    out['gates'] = gates(out, frozen)
    write_json(out_path, out)
    return out


def measure(te, flags, novel, new_decoys):
    pos = te.is_fraud.to_numpy() == 1
    nov = pos & te.fraud_type.isin(list(novel)).to_numpy()
    hard = (te.hard_negative_type.to_numpy() != '') & ~pos
    newhard = te.hard_negative_type.isin(list(new_decoys)).to_numpy() & ~pos
    return {'recall': recall(flags, pos), 'recall_ci95': case_bootstrap(te, flags, pos),
            'known_recall': recall(flags, pos & ~nov), 'novel_recall': recall(flags, nov),
            'novel_ci95': case_bootstrap(te, flags, nov) if nov.any() else None,
            'hard_negative_rate': recall(flags, hard), 'new_hard_negative_rate': recall(flags, newhard),
            'positives': int(pos.sum()), 'novel_positives': int(nov.sum()),
            'cases': int(te.loc[pos, 'case_id'].nunique()), 'novel_cases': int(te.loc[nov, 'case_id'].nunique()),
            'by_family': {f: recall(flags, pos & (te.fraud_type.to_numpy() == f)) for f in sorted(set(te.fraud_type[pos]))}}


def gates(out, frozen):
    worlds = out['worlds'].values()
    s2 = [w['S2'] for w in worlds]
    mean = lambda key, rows: float(np.mean([r[key] for r in rows]))
    g = {'V5-S2 chung': mean('recall', s2) >= .60, 'V5-S2 mới': mean('novel_recall', s2) >= .35,
         'V5-S2 sàn': min(r['recall'] for r in s2) >= .45,
         'V5-S2 lệch dev': abs(mean('recall', s2) - frozen['dev_S2_recall_mean']) <= .15,
         'V5-S2 báo nhầm': max(r['hard_negative_rate'] for r in s2) <= .15}
    result = {'S2': {'checks': g, 'passed': all(g.values()), 'mean_recall': mean('recall', s2),
                     'mean_novel_recall': mean('novel_recall', s2), 'min_recall': min(r['recall'] for r in s2),
                     'dev_recall': frozen['dev_S2_recall_mean']}}
    if frozen['cold']:
        cold = [w['Cold'] for w in worlds]
        c = {'V5-Cold chung': mean('recall', cold) >= .35, 'V5-Cold mới': mean('novel_recall', cold) >= .30,
             'V5-Cold sàn': min(r['recall'] for r in cold) >= .25,
             'V5-Cold báo nhầm': max(r['hard_negative_rate'] for r in cold) <= .15}
        result['Cold'] = {'checks': c, 'passed': all(c.values())}
    else:
        result['Cold'] = {'passed': False, 'reason': 'Cold did not pass its pre-seal gate; not offered'}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['freeze', 'evaluate'])
    p.add_argument('--dev-matrices', type=Path, default=Path('work/v5_matrices'))
    p.add_argument('--sealed-matrices', type=Path, default=Path('work/v5_sealed_matrices'))
    p.add_argument('--seeds', type=int, nargs='+', default=[5101, 5102, 5103, 5104])
    p.add_argument('--out', type=Path, default=OUT, help='use a different path for the dry run')
    a = p.parse_args()
    limit_memory(10)
    if a.stage == 'freeze':
        print(json.dumps(freeze(), ensure_ascii=False)[:500])
    else:
        from .world_v5_sealed import NOVEL_V5, NEW_DECOYS_V5
        if a.out == OUT and a.seeds != [5101, 5102, 5103, 5104]:
            raise SystemExit('only the four sealed seeds may write the sealed result')
        evaluate(a.dev_matrices, a.sealed_matrices, a.seeds, NOVEL_V5, NEW_DECOYS_V5, a.out)


if __name__ == '__main__':
    main()
