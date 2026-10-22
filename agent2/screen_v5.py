"""R2 runner for the registered v5 candidates (R1 v1.2). All results are dữ liệu tổng hợp.

Efficiency without changing the estimand: for one target world and one feature set the 19 source worlds are
streamed ONCE into a LightGBM Dataset; the eleven protocols (S2 and ten hidden ACFE branches), the PU weight
and the model seeds only change labels and sample weights (`set_label`, `set_weight`).

Registered training policy (v1.2): fixed 400 trees, learning rate 0.05, leaves 7 and 15 with the leaf setting
chosen by source-validation AP, PU weight w on unlabelled rows, family balancing only for L4-FB-PU.
Optional negative subsampling keeps every true fraud row of the sources (observed or hidden, the latter as U
with weight w), every hard negative, and a fraction f of the remaining rows with weight 1/f (an unbiased
importance-sampling estimate of the full-data loss). Validation and targets are never subsampled.

Candidates: L3-PU, L4-FB-PU, L4-PU-E2-AR (L4 + change features), L4-PU-E2-AR-2plus1 (two slots from
L4-PU-E2-AR, one from Cold-Rules-E2), Cold-Rules-E2 = max rank(rules, EntityDeviation2 without the link shortcut, R1 v1.3), Cold-v4 = max rank
(rules, EntityDeviation v4). Cold ranks are relative to the TARGET world's own validation period (no labels).
"""
from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from .base_v5 import (BRANCHES, ConcatSequence, MatrixSequence, SubsetSequence, observed_labels,
                      predict_sequences)
from .methods import empirical_rank
from .metrics import tie_break, weekly_alerts
from .runtime_v5 import limit_memory, sha256, write_json
from .select_v5 import (COLD, HN_WEIGHTS, PU_WEIGHTS, advance, SUPERVISED, TIERS, candidate_summary, choose_cold, final_choice,
                        pre_seal_gate, selection_roster, world_summary)

WORLDS = tuple(range(1001, 1021))
ROUNDS, LEAVES, LR = 400, (7, 15), .05
THREADS = 8
KIND = {'L3-PU': ('L3', False, False), 'L4-FB-PU': ('L4', True, False), 'L4-PU-E2-AR': ('L4', False, True)}
PROTOCOLS = ('S2', *BRANCHES)


# R1 v1.3: in the v4/v5 generators only FRAUDULENT reversals carry `applied_invoice_id` (legitimate returns and
# write-offs never link the original invoice), so every feature built on that link is a generator shortcut.
# They are excluded and the EntityDeviation2 maximum is recomputed without them.
LINK_SHORTCUT = {'ar_reversal_age_days', 'ar_reversal_unpaid', 'ar_creator_reversal_share',
                 'ar_reversal_age_days-', 'ar_reversal_unpaid+', 'ar_creator_reversal_share+', 'ed2_score'}


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


class CleanChangeSequence(lgb.Sequence):
    """Change-feature matrix without the link shortcut, plus `ed2_clean` = max over the kept detector tails."""
    batch_size = 4096

    def __init__(self, path, names):
        self.array = np.load(path, mmap_mode='r')
        self.keep = np.array([i for i, n in enumerate(names) if n not in LINK_SHORTCUT])
        self.detectors = np.array([i for i, n in enumerate(names) if n[-1] in '+-' and n not in LINK_SHORTCUT])

    def __len__(self):
        return len(self.array)

    def _block(self, x):
        x = np.atleast_2d(np.asarray(x, dtype=np.float64))
        return np.concatenate([x[:, self.keep], x[:, self.detectors].max(axis=1, keepdims=True)], axis=1)

    def __getitem__(self, index):
        block = self._block(self.array[index])
        return block[0] if np.ndim(index) == 0 and not isinstance(index, slice) else block

    def take(self, rows):
        return self._block(self.array[np.asarray(rows)])


def clean_change_names(matrices):
    names = _load(matrices / 's1001' / 'manifest_cd.json')['columns']
    return [n for n in names if n not in LINK_SHORTCUT] + ['ed2_clean']


def pool_sequence(directory, split, cols, change):
    base = MatrixSequence(directory / f'{split}.npy', cols)
    if not change:
        return base
    names = _load(directory / 'manifest_cd.json')['columns']
    return ConcatSequence([base, CleanChangeSequence(directory / f'{split}_cd.npy', names)])


def columns_for(matrices, kind):
    contract = _load(matrices / 's1001' / 'manifest.json')
    if KIND[kind][0] == 'L3':
        return [contract['columns'].index(c) for c in contract['L3_columns']]
    return list(range(len(contract['columns'])))


def _meta(directory, split):
    meta = pd.read_parquet(directory / f'{split}.parquet')
    if 'hard_negative_type' not in meta:
        meta['hard_negative_type'] = ''
    return meta[['is_fraud', 'fraud_type', 'branch', 'hard_negative_type']].copy()


class SourcePool:
    """Source worlds of one target, one feature set; train rows optionally subsampled once."""

    def __init__(self, target, matrices, kind, fraction, sources=WORLDS, target_dir=None):
        _, self.balanced, change = KIND[kind]
        cols = columns_for(matrices, kind)
        seqs, metas = [], []
        for seed in sources:
            if seed == target:
                continue
            d = matrices / f's{seed}'
            seq, meta = pool_sequence(d, 'train', cols, change), _meta(d, 'train')
            meta['factor'] = 1.0
            if fraction < 1:
                rng = np.random.default_rng(1000 + seed)
                always = (meta.is_fraud.to_numpy() == 1) | (meta.hard_negative_type.to_numpy() != '')
                keep = always | (rng.random(len(meta)) < fraction)
                index = np.flatnonzero(keep)
                seq = SubsetSequence(seq, index)
                meta = meta.iloc[index].reset_index(drop=True)
                meta['factor'] = np.where(always[index], 1.0, 1.0 / fraction)
            seqs.append(seq)
            metas.append(meta)
        self.meta = pd.concat(metas, ignore_index=True)
        self.dataset = lgb.Dataset(seqs, label=np.zeros(len(self.meta)), weight=np.ones(len(self.meta)),
                                   params={'max_bin': 255, 'feature_pre_filter': False, 'verbosity': -1},
                                   free_raw_data=False).construct()
        self.valid = [pool_sequence(matrices / f's{s}', 'validation', cols, change) for s in sources if s != target]
        self.valid_meta = pd.concat([_meta(matrices / f's{s}', 'validation') for s in sources if s != target],
                                    ignore_index=True)
        self.target = pool_sequence(Path(target_dir) if target_dir else matrices / f's{target}', 'test', cols, change)
        self.rows, self.sources = len(self.meta), len([s for s in sources if s != target])

    def fit_score(self, hidden, weight, seed, hn=None):
        y, sample = observed_labels(self.meta, hidden, self.balanced, weight, hn)
        sample = sample * self.meta.factor.to_numpy(dtype=np.float32)
        self.dataset.set_label(y)
        self.dataset.set_weight(sample)
        yv, _ = observed_labels(self.valid_meta, hidden, False, weight)
        if not y.sum() or not yv.sum():
            raise ValueError('Source positive support absent; refuse undocumented fallback')
        params = dict(objective='binary', learning_rate=LR, min_child_samples=10, subsample=.8, subsample_freq=1,
                      colsample_bytree=.6, reg_lambda=2., scale_pos_weight=max(1., (len(y) - y.sum()) / y.sum()) ** .5,
                      seed=seed, num_threads=THREADS, verbosity=-1)
        best = (-1., None, None)
        for leaves in LEAVES:
            model = lgb.train(dict(params, num_leaves=leaves), self.dataset, num_boost_round=ROUNDS)
            ap = float(average_precision_score(yv, predict_sequences(model, self.valid)))
            if ap > best[0]:
                best = (ap, model, leaves)
        scores = predict_sequences(best[1], [self.target])
        return scores, {'validation_ap': best[0], 'num_leaves': best[2], 'trees': best[1].current_iteration(),
                        'source_train_rows': self.rows, 'source_worlds': self.sources,
                        'observed_train_positives': int(y.sum()), 'PU_weight': weight, 'model_seed': seed}


def evaluate(te, scores, protocol, alerts=None):
    alerts = weekly_alerts(te, scores + tie_break(len(te), 5), 3) if alerts is None else alerts
    positive = te.is_fraud.to_numpy() == 1
    hard = (te.hard_negative_type.to_numpy() != '') & ~positive
    branch = (te.branch.to_numpy() == protocol) & positive
    return alerts, {'tp': int((positive & alerts).sum()), 'positives': int(positive.sum()),
                    'branch_tp': int((branch & alerts).sum()), 'branch_positives': int(branch.sum()),
                    'hard_negative_alerts': int((hard & alerts).sum()), 'hard_negatives': int(hard.sum()),
                    'alerts': int(alerts.sum())}


def save(directory, protocol, te, scores, alerts, result):
    directory.mkdir(parents=True, exist_ok=True)
    flags = directory / f'{protocol}.npz'
    tmp = flags.with_suffix('.tmp.npz')
    np.savez_compressed(tmp, scores=np.asarray(scores, dtype=np.float32), alerts=alerts)
    tmp.replace(flags)
    result = dict(result, data_origin='dữ liệu tổng hợp', protocol=protocol, flags_sha256=sha256(flags))
    write_json(directory / f'{protocol}.json', result)
    return result


def run_supervised(kind, target, tier_dir, matrices, weight, seeds, fraction, hn=None):
    """All eleven protocols of one target; resumes protocol by protocol."""
    out = tier_dir / kind / f's{target}'
    done = {p: _load(out / f'{p}.json') for p in PROTOCOLS if (out / f'{p}.json').exists()}
    if len(done) < len(PROTOCOLS):
        began = time.monotonic()
        pool = SourcePool(target, matrices, kind, fraction)
        built = time.monotonic() - began
        te = pd.read_parquet(matrices / f's{target}' / 'test.parquet')
        for protocol in PROTOCOLS:
            if protocol in done:
                continue
            t0 = time.monotonic()
            runs = [pool.fit_score(None if protocol == 'S2' else protocol, weight, seed, hn) for seed in seeds]
            scores = np.mean([r[0] for r in runs], axis=0)
            alerts, metrics = evaluate(te, scores, protocol)
            done[protocol] = save(out, protocol, te, scores, alerts,
                                  dict(metrics, world=target, candidate=kind, fits=[r[1] for r in runs],
                                       seconds=time.monotonic() - t0, dataset_seconds=built))
            print(f'{kind} w={weight} hn={hn} target={target} {protocol} R={metrics["tp"] / max(1, metrics["positives"]):.3f}',
                  flush=True)
        del pool
        gc.collect()
    summary = world_summary(done, BRANCHES)
    write_json(out / 'summary.json', summary)
    return summary


def cold_scores(matrices, target, which):
    d = matrices / f's{target}'
    va, te = pd.read_parquet(d / 'validation.parquet'), pd.read_parquet(d / 'test.parquet')
    channels = [('rule_graph', va.rule_graph.fillna(0).to_numpy(), te.rule_graph.fillna(0).to_numpy())]
    if which == 'Cold-v4':
        channels.append(('u_entity', va.u_entity.fillna(0).to_numpy(), te.u_entity.fillna(0).to_numpy()))
    else:
        names = _load(d / 'manifest_cd.json')['columns']
        clean = CleanChangeSequence(d / 'validation_cd.npy', names)       # max over kept detectors (v1.3)
        channels.append(('ed2_clean', clean.take(np.arange(len(clean)))[:, -1],
                         CleanChangeSequence(d / 'test_cd.npy', names).take(np.arange(len(te)))[:, -1]))
    ranks = [empirical_rank(np.sort(np.asarray(v, dtype=float)), np.asarray(t, dtype=float)) for _, v, t in channels]
    return te, np.max(ranks, axis=0) + 1e-3 * np.mean(ranks, axis=0)


def run_cold(which, target, tier_dir, matrices):
    """Label-free: one alert set; hidden-branch protocols differ only in which positives they count."""
    out = tier_dir / which / f's{target}'
    te, scores = cold_scores(matrices, target, which)
    alerts = weekly_alerts(te, scores + tie_break(len(te), 5), 3)
    done = {}
    for protocol in PROTOCOLS:
        _, metrics = evaluate(te, scores, protocol, alerts)
        done[protocol] = save(out, protocol, te, scores, alerts, dict(metrics, world=target, candidate=which))
    summary = world_summary(done, BRANCHES)
    write_json(out / 'summary.json', summary)
    return summary


def run_two_plus_one(target, tier_dir, matrices):
    """Two slots from L4-PU-E2-AR (per protocol scores), one slot from Cold-Rules-E2."""
    out = tier_dir / 'L4-PU-E2-AR-2plus1' / f's{target}'
    te, cold = cold_scores(matrices, target, 'Cold-Rules-E2')
    base = tier_dir / 'L4-PU-E2-AR' / f's{target}'
    done = {}
    for protocol in PROTOCOLS:
        s = np.load(base / f'{protocol}.npz')['scores'].astype(float)
        first = weekly_alerts(te, s + tie_break(len(te), 3), 2)
        second = weekly_alerts(te, np.where(first, -np.inf, cold + tie_break(len(te), 4)), 1) & ~first
        alerts = first | second
        _, metrics = evaluate(te, s, protocol, alerts)
        done[protocol] = save(out, protocol, te, s, alerts, dict(metrics, world=target, candidate='L4-PU-E2-AR-2plus1'))
    summary = world_summary(done, BRANCHES)
    write_json(out / 'summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['pu', 'hn', 'screen', 'select', 'cold', 'one'])
    p.add_argument('--matrices', type=Path, default=Path('work/v5_matrices'))
    p.add_argument('--output', type=Path, default=Path('results/v5/R2'))
    p.add_argument('--fraction', type=float, required=True, help='registered negative subsampling fraction (1 = none)')
    p.add_argument('--kind', default='L4-FB-PU')
    p.add_argument('--target', type=int, default=1001)
    p.add_argument('--weight', type=float, default=.2)
    p.add_argument('--weights', type=float, nargs='*', help='pu: compute only these w (parallel workers); summary needs all')
    p.add_argument('--hns', type=float, nargs='*', help='hn: compute only these h (parallel workers); summary needs all')
    p.add_argument('--kinds', nargs='*', help='screen/select: compute only these kinds (parallel workers), no summary')
    p.add_argument('--threads', type=int, default=8)
    a = p.parse_args()
    global THREADS
    THREADS = a.threads
    limit_memory(10)
    screening, _ = TIERS['screening']
    selection, _ = TIERS['selection']
    if a.stage == 'one':                                   # timing pilot, one target, one kind
        print(json.dumps(run_supervised(a.kind, a.target, a.output / 'pilot', a.matrices, a.weight, (0,), a.fraction),
                         ensure_ascii=False)[:400])
        return
    if a.stage == 'pu':
        summaries = {}
        for w in (a.weights or PU_WEIGHTS):
            worlds = {s: run_supervised('L4-FB-PU', s, a.output / f'pu_w{w}', a.matrices, w, (0,), a.fraction)
                      for s in screening}
            summaries[str(w)] = candidate_summary(worlds, 'screening')
        if a.weights:                      # worker mode: results are checkpointed, the summary run decides
            return
        valid = [w for w in PU_WEIGHTS if summaries[str(w)]['eligible']]
        w = max(valid, key=lambda v: (summaries[str(v)]['J'], -PU_WEIGHTS.index(v))) if valid else None
        write_json(a.output / 'PU_locked.json', {'status': 'locked' if w is not None else 'no_eligible_weight', 'w': w,
                   'J': {k: v['J'] for k, v in summaries.items()},
                   'eligible': {k: v['eligible'] for k, v in summaries.items()}, 'data_origin': 'dữ liệu tổng hợp'})
        return
    lock = _load(a.output / 'PU_locked.json')
    w = lock['w'] if lock['w'] is not None else PU_WEIGHTS[0]
    if a.stage == 'hn':                                    # v6 registration section 3: lock h on L4-FB-PU, w fixed
        summaries = {}
        for h in (a.hns or HN_WEIGHTS):
            worlds = {s: run_supervised('L4-FB-PU', s, a.output / f'hn_{h}', a.matrices, w, (0,), a.fraction, h)
                      for s in screening}
            summaries[str(h)] = candidate_summary(worlds, 'screening')
        if a.hns:
            return
        valid = [h for h in HN_WEIGHTS if summaries[str(h)]['eligible']]
        h = max(valid, key=lambda v: (summaries[str(v)]['J'], -HN_WEIGHTS.index(v))) if valid else None
        write_json(a.output / 'HN_locked.json', {'status': 'locked' if h is not None else 'no_eligible_hn_weight', 'h': h,
                   'w': w, 'J': {k: v['J'] for k, v in summaries.items()},
                   'eligible': {k: v['eligible'] for k, v in summaries.items()},
                   'R_mean': {k: v['R_mean'] for k, v in summaries.items()},
                   'B_mean': {k: v['B_mean'] for k, v in summaries.items()}, 'data_origin': 'dữ liệu tổng hợp'})
        return
    hn_lock = a.output / 'HN_locked.json'
    hn = _load(hn_lock)['h'] if hn_lock.exists() else None          # v6 when present; None keeps v5 behaviour
    if hn_lock.exists() and hn is None:
        raise SystemExit('v6: no eligible hard-negative weight; the round stops (registration section 3)')
    if a.stage == 'screen':
        tier = a.output / 'screening'
        cands = {}
        for kind in (a.kinds or ('L3-PU', 'L4-FB-PU', 'L4-PU-E2-AR')):
            reuse = a.output / (f'pu_w{w}' if hn is None else f'hn_{hn}')
            src = reuse if kind == 'L4-FB-PU' and reuse.exists() else tier   # identical estimand: reuse, never refit
            cands[kind] = candidate_summary({s: run_supervised(kind, s, src, a.matrices, w, (0,), a.fraction, hn)
                                             for s in screening}, 'screening')
        if a.kinds:
            return
        if hn is None:
            cands['L4-PU-E2-AR-2plus1'] = candidate_summary({s: run_two_plus_one(s, tier, a.matrices) for s in screening},
                                                            'screening')
            roster = selection_roster(cands)
        else:                                          # v6: three supervised candidates, no Cold, no 2plus1
            roster = {'supervised': advance(cands, order=tuple(cands)), 'cold': []}
        write_json(a.output / 'screening_summary.json', {'w': w, 'hn': hn, 'candidates': {k: {x: v[x] for x in
                   ('J', 'Q_min', 'Q_mean', 'R_mean', 'R_min', 'B_mean', 'B_min', 'eligible', 'tail_worlds')}
                   for k, v in cands.items()}, 'roster': roster, 'data_origin': 'dữ liệu tổng hợp'})
        return
    if a.stage == 'cold':
        tier = a.output / 'selection'
        res = {c: candidate_summary({s: run_cold(c, s, tier, a.matrices) for s in selection}, 'selection') for c in COLD}
        chosen = choose_cold(res)
        write_json(a.output / 'cold_selection.json', {'chosen': chosen,
                   'candidates': {k: {x: v[x] for x in ('J', 'Q_min', 'Q_mean', 'R_mean', 'R_min', 'B_mean', 'eligible')}
                                  for k, v in res.items()},
                   'gate': pre_seal_gate(res[chosen], cold=True) if chosen else None, 'data_origin': 'dữ liệu tổng hợp'})
        return
    if a.stage == 'select':
        roster = _load(a.output / 'screening_summary.json')['roster']['supervised']
        tier = a.output / 'selection'
        res = {}
        if a.kinds:                        # worker mode: fit the given base kinds only
            for kind in a.kinds:
                for s in selection:
                    run_supervised(kind, s, tier, a.matrices, w, (0, 1, 2, 3, 4), a.fraction, hn)
            return
        for kind in roster:
            base = 'L4-PU-E2-AR' if kind == 'L4-PU-E2-AR-2plus1' else kind
            worlds = {s: run_supervised(base, s, tier, a.matrices, w, (0, 1, 2, 3, 4), a.fraction, hn) for s in selection}
            if kind == 'L4-PU-E2-AR-2plus1':
                worlds = {s: run_two_plus_one(s, tier, a.matrices) for s in selection}
            res[kind] = candidate_summary(worlds, 'selection')
        chosen = final_choice(res, SUPERVISED)
        write_json(a.output / 'selection_summary.json', {'w': w, 'hn': hn, 'chosen': chosen,
                   'candidates': {k: {x: v[x] for x in ('J', 'Q_min', 'Q_mean', 'R_mean', 'R_min', 'B_mean', 'B_min',
                                                         'eligible', 'tail_worlds')} for k, v in res.items()},
                   'gate': pre_seal_gate(res[chosen]) if chosen else {'passed': False, 'decision':
                           'stop_without_generating_sealed_worlds', 'reason': 'no eligible candidate'},
                   'data_origin': 'dữ liệu tổng hợp'})


if __name__ == '__main__':
    main()
