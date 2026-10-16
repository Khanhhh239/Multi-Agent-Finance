"""Company-local, explicitly versioned feedback correction for future weeks.

The frozen policy remains the default. This optional research variant learns
only from confirmed/legitimate reviewed cases; unreviewed or suspected cases
and worth-review ratings are never converted into negative/positive labels.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .methods import fit_prior_logistic
from .metrics import weekly_alerts
from .review_store_v4 import ReviewStore


def vectors(frame, entity):
    columns = {f'rule:{c[4:]}': (frame[c].to_numpy(dtype=float) > 0).astype(float)
               for c in frame if c.startswith('hit_')}
    columns.update({f'entity:{key}': np.clip(value, 0, 12) / 12 for key, value in entity.parts(frame).items()})
    return pd.DataFrame(columns, index=frame.index)


def aggregate(cases, frame, matrix):
    aligned = matrix.set_axis(frame.transaction_id.to_numpy())
    return [aligned.loc[identifiers].max().to_dict() for identifiers in cases.transaction_ids]


def learn(store, company, cutoff, minimum=20):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        raise ValueError('feedback cutoff requires timezone')
    latest = {}
    for decision in store.decisions(company):
        if pd.Timestamp(decision['created_at']) <= cutoff:
            latest[decision['case_id']] = decision
    cases = {case['case_id']: case for case in store.list_cases(company)}
    rows, labels, ids = [], [], []
    for identifier, decision in latest.items():
        case = cases.get(identifier, {})
        if decision['conclusion'] not in ('confirmed', 'legitimate') or not case.get('feedback_vector'):
            continue
        rows.append(case['feedback_vector'])
        labels.append(int(decision['conclusion'] == 'confirmed'))
        ids.append(decision['id'])
    names = sorted({key for row in rows for key in row})
    ready = len(rows) >= minimum and set(labels) == {0, 1}
    theta = np.zeros(len(names) + 1)
    if ready:
        x = np.asarray([[row.get(key, 0) for key in names] for row in rows], dtype=float)
        if not np.isfinite(x).all() or (x < 0).any() or (x > 1).any():
            raise ValueError('feedback vectors must be finite values in [0,1]')
        theta = fit_prior_logistic(x, np.asarray(labels), np.zeros(len(names)), lam=.1)
    return {'schema_version': 1, 'company_id': company, 'cutoff': cutoff.isoformat(),
            'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'status': 'trained' if ready else 'insufficient_labels', 'labelled_cases': len(rows),
            'positive_cases': sum(labels), 'decision_ids': ids, 'features': names,
            'intercept': float(theta[0]), 'weights': theta[1:].tolist(), 'minimum_cases': minimum,
            'prior': 'zero correction; L2 penalty 0.1', 'hard_trigger_protection': True,
            'limitations': ['selective labels from reviewed alerts only', 'unvalidated research variant',
                            'not a calibrated probability; not the frozen G5 policy']}


def apply(frame, base, hard, matrix, artifact, company, week_start):
    if artifact.get('schema_version') != 1 or artifact.get('company_id') != str(company):
        raise ValueError('feedback artifact belongs to another company or schema')
    if artifact.get('status') != 'trained':
        raise ValueError('feedback artifact has insufficient confirmed/legitimate labels')
    cutoff = pd.Timestamp(artifact['cutoff'])
    created = pd.Timestamp(artifact['created_at'])
    if cutoff.tzinfo is None or created.tzinfo is None or max(cutoff, created) > week_start:
        raise ValueError('feedback must be trained before the scoring week; no retrospective leakage')
    names, weights = artifact['features'], np.asarray(artifact['weights'], dtype=float)
    if len(weights) != len(names) or not np.isfinite(weights).all() or len(set(names)) != len(names):
        raise ValueError('invalid feedback weights')
    if set(names) - set(matrix):
        raise ValueError('feedback features differ from this pipeline version')
    adjustment = matrix[names].to_numpy(dtype=float) @ weights + float(artifact['intercept'])
    score = 10 * np.asarray(base, dtype=float) + np.tanh(adjustment)
    if not np.isfinite(score).all():
        raise ValueError('non-finite feedback score')
    hard = np.asarray(hard, dtype=bool)
    # Reserve the top tier for hard evidence, even when other signals gain weight.
    if hard.any():
        score[hard] = max(float(score.max()), 10) + 1 + np.asarray(base)[hard]
    return weekly_alerts(frame, score, 3), score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--company', required=True)
    parser.add_argument('--cutoff', required=True, help='ISO timestamp with timezone')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('feedback artifacts are versioned; choose a new output path')
    artifact = learn(ReviewStore(args.db), args.company, args.cutoff)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(artifact, ensure_ascii=False, indent=2))
    print(json.dumps({'status': artifact['status'], 'labelled_cases': artifact['labelled_cases'],
                      'sha256': hashlib.sha256(args.out.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
