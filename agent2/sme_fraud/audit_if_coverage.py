"""Explain frozen IF coverage by temporal scope and actual data defects.

Reads existing scores only. Never fits, scores, widens evaluation or edits queues.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path

import numpy as np

from .audit_model_windows import partition_rows
from .compare_shadow import build_snapshots, read_csv, read_json, write_csv, write_json
from .feature_contract import sha, validate_cache
from .shadow_scoring import guarded, instant, output_guard, source_checks

VERSION = 'if-coverage-audit-v1'
HISTORY = {'train', 'calibration'}


def unique_index(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError('Empty or duplicate '+key)
        result[value] = row
    return result


def feature_status(path, columns, transactions):
    """Inspect ID/schema/finite float32 values without sending a matrix to IF."""
    result = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        rows = csv.reader(stream)
        if next(rows, None) != ['transaction_id', *columns]:
            raise ValueError('Feature header differs from the frozen contract')
        for row in rows:
            if not row or not row[0] or row[0] in result:
                raise ValueError('Empty or duplicate feature ID')
            tid = row[0]
            if tid not in transactions:
                raise ValueError('Feature ID absent from source transactions')
            status = 'valid'
            if len(row) != len(columns)+1:
                status = 'invalid_width'
            else:
                try:
                    with np.errstate(over='ignore', invalid='ignore'):
                        values = np.asarray(row[1:], dtype=np.float32)
                    if not np.isfinite(values).all():
                        status = 'nonfinite'
                except (ValueError, TypeError, OverflowError):
                    status = 'nonnumeric'
            result[tid] = status
    return result


def member_audit(tid, company, cutoff, transactions, partitions, features, scores, run_id):
    row, score = transactions.get(tid), scores.get(tid)
    partition = partitions.get(tid, {}).get('partition', 'unknown')
    errors = []
    if row is None:
        errors.append('unknown_transaction')
    else:
        if row['company_id'] != company:
            errors.append('cross_company_member')
        if cutoff is not None and instant(row['posted_at']) >= instant(cutoff):
            errors.append('future_member')
        if features.get(tid, 'missing') != 'valid':
            errors.append('feature_'+features.get(tid, 'missing'))
        if partition == 'unknown':
            errors.append('missing_partition')
    if score is not None:
        try:
            if not math.isfinite(float(score['anomaly_score'])):
                errors.append('nonfinite_score')
        except (ValueError, TypeError, KeyError):
            errors.append('invalid_score')
        if row is not None and (score.get('company_id') != row['company_id']
                or instant(score.get('posted_at')) != instant(row['posted_at'])):
            errors.append('score_source_mismatch')
        if score.get('run_id') != run_id:
            errors.append('score_run_mismatch')
        if partition != 'evaluation':
            errors.append('score_outside_evaluation')
    elif partition == 'evaluation':
        errors.append('evaluation_score_missing')
    status = ('data_error' if errors else 'evaluation_scored' if score is not None else
              'historical_exclusion' if partition in HISTORY else 'other_scope_exclusion')
    return dict(transaction_id=tid, source_company_id=row['company_id'] if row else '',
        posted_at=row['posted_at'] if row else '', partition=partition,
        feature_status=features.get(tid, 'missing'), score_present=score is not None,
        member_status=status, errors='|'.join(sorted(errors)))


def case_audit(case, cutoff, transactions, partitions, features, scores, run_id):
    raw = case['transaction_ids']
    members = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(members, list) or any(not isinstance(t, str) or not t for t in members):
        raise ValueError('Case members must be nonempty transaction IDs in a list')
    rows = [member_audit(t, case['company_id'], cutoff, transactions, partitions, features, scores, run_id)
            for t in members]
    errors = sorted({e for r in rows for e in r['errors'].split('|') if e})
    if len(members) != len(set(members)):
        errors.append('duplicate_member_link')
    if case['case_type'] != 'transaction':
        return dict(coverage_reason='outside_transaction_scope', errors=''), []
    if not members:
        errors.append('empty_transaction_case')
    counts = Counter(r['partition'] for r in rows)
    if errors:
        reason = 'data_error'
    elif set(counts) == {'evaluation'}:
        reason = 'full_evaluation_scored'
    elif set(counts) <= HISTORY:
        reason = 'historical_only_unscored'
    elif set(counts) <= HISTORY | {'evaluation'} and counts['evaluation']:
        reason = 'mixed_history_evaluation'
    else:
        reason = 'other_scope_exclusion'
    return dict(coverage_reason=reason, errors='|'.join(errors), member_count=len(members),
        scored_members=sum(r['score_present'] for r in rows),
        train_members=counts['train'], calibration_members=counts['calibration'],
        evaluation_members=counts['evaluation'],
        other_members=sum(n for p, n in counts.items() if p not in HISTORY | {'evaluation'}),
        partition_signature='+'.join(p for p in ('train','calibration','evaluation',
            'outside_time_windows','outside_company_scope','unknown') if counts[p])), rows


def summarize(rows):
    tx = [r for r in rows if r['case_type'] == 'transaction']
    reasons = Counter(r['coverage_reason'] for r in tx)
    eligible = [r for r in tx if r['evaluation_members'] == r['member_count'] and r['member_count'] > 0]
    full = reasons['full_evaluation_scored']
    return dict(selected_work_reviews=len(rows), transaction_work_reviews=len(tx),
        nontransaction_work_reviews=len(rows)-len(tx), full_if_coverage=full,
        missing_or_partial=len(tx)-full, full_fraction=full/len(tx) if tx else None,
        reasons=dict(sorted(reasons.items())),
        unscored_partition_signatures=dict(sorted(Counter(r['partition_signature'] for r in tx
            if r['coverage_reason'] != 'full_evaluation_scored').items())),
        entirely_evaluation_work_reviews=len(eligible),
        entirely_evaluation_full_fraction=full/len(eligible) if eligible else None,
        unique_transaction_case_ids=len({r['case_id'] for r in tx}),
        unique_transaction_work_keys=len({r['work_key'] for r in tx}))


def verify_commitment(directory):
    directory = guarded(directory)
    checks = {str(directory/'predictions_frozen.json'): sha(directory/'predictions_frozen.json')}
    for name, expected in read_json(directory/'predictions_frozen.json').items():
        path = guarded(directory/name)
        if not path.is_relative_to(directory) or sha(path) != expected:
            raise ValueError('Frozen comparison checksum differs: '+name)
        checks[str(path)] = expected
    return checks


def audit_coverage(dataset, baseline, comparison, temporal, output):
    dataset, baseline, comparison, temporal, output = map(guarded,
        (dataset, baseline, comparison, temporal, output))
    output_guard(output, dataset, comparison/'unused-model')
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in (baseline,comparison,temporal)):
        raise ValueError('Coverage output must be separate from frozen inputs')
    inputs = verify_commitment(comparison)
    metadata = read_json(dataset/'manifest.json')
    if metadata.get('role') != 'reporting' or metadata.get('is_synthetic') is not True:
        raise ValueError('Coverage audit requires synthetic reporting sources')
    contract = validate_cache(metadata)
    source_hashes = source_checks(dataset, metadata)
    inputs.update({str(dataset/name): h for name, h in source_hashes.items()})
    inputs[str(dataset/'manifest.json')] = sha(dataset/'manifest.json')
    plan = read_json(comparison/'evaluation_plan.json')
    run = read_json(comparison/'if_scores/run.json')
    time_audit = read_json(temporal/'audit.json')
    model = guarded(run['model_path'])
    record = model.parent/'training_run.json'
    training = read_json(record)
    for path, expected in {**plan['baseline_input_sha256'], **plan['code_sha256'],
            str(model): plan['model_sha256'], str(record): time_audit['training_record_sha256'],
            str(temporal/'temporal_partitions.csv'): time_audit['membership_csv_sha256']}.items():
        if sha(guarded(path)) != expected:
            raise ValueError('Frozen source/model/reconstruction binding changed: '+str(path))
        inputs[str(path)] = expected
    inputs[str(temporal/'audit.json')] = sha(temporal/'audit.json')
    if (run['model_sha256'] != plan['model_sha256'] or time_audit['model_sha256'] != plan['model_sha256']
            or training['model_sha256'] != plan['model_sha256']
            or run['manifest_sha256'] != sha(dataset/'manifest.json')
            or time_audit['source_manifest_sha256'] != run['manifest_sha256']
            or run['input_sha256'] != source_hashes or run['scope'] != plan['scope']
            or not run['model_training_window_disjointness_verified']
            or training['temporal_provenance']['plan'] != time_audit['plan']
            or plan['scope'] != dict(company_ids=time_audit['plan']['company_ids'],
                source_ref=time_audit['plan']['source_ref'], **time_audit['plan']['evaluation'])
            or run['scores_sha256'] != sha(comparison/'if_scores/shadow_scores.csv')):
        raise ValueError('Frozen score, source, model or temporal windows do not match')
    transactions = unique_index(read_csv(dataset/'transactions.csv'), 'transaction_id')
    memberships = partition_rows(transactions.values(), time_audit['plan'])
    partitions = unique_index(read_csv(temporal/'temporal_partitions.csv'), 'transaction_id')
    if partitions != unique_index(memberships, 'transaction_id'):
        raise ValueError('Recorded temporal membership differs from source times')
    features = feature_status(dataset/'features.csv', contract['columns'], transactions)
    scores = unique_index(read_csv(comparison/'if_scores/shadow_scores.csv'), 'transaction_id')
    if set(scores)-set(transactions) or len(scores) != run['rows_scored']:
        raise ValueError('Frozen score IDs or count differ from source/run')
    source_rows = [member_audit(t, row['company_id'], None, transactions, partitions, features, scores, run['run_id'])
                   for t, row in transactions.items()]
    # Snapshot reconstruction consumes existing scalar scores, never estimator methods.
    snapshots, rebuilt_inputs, reconstruction = build_snapshots(dataset, baseline, plan['scope'],
        {t: float(r['anomaly_score']) for t, r in scores.items()})
    if rebuilt_inputs != plan['baseline_input_sha256'] or reconstruction != plan['baseline_reconstruction']:
        raise ValueError('Baseline reconstruction differs from the frozen comparison')
    lookup = {(s['day'].isoformat(), c['case_id'], c['production_scope_hash']): (s['cutoff'], c)
              for s in snapshots for c in s['cases']}
    reviews, member_rows, summaries = [], [], {}
    for budget in (5, 10):
        selected = read_csv(comparison/f'budget_{budget}/selections.private.csv')
        seen = set()
        for row in selected:
            key = (row['arm'], row['work_key'])
            if row['arm'] not in {'baseline','if_shadow'} or key in seen:
                raise ValueError('Unknown arm or duplicated selected work')
            seen.add(key)
            found = lookup.get((row['day'], row['case_id'], row['case_scope_hash']))
            if found is None:
                raise ValueError('Selected review absent from as-of snapshot')
            cutoff, case = found
            if (instant(cutoff) != instant(row['cutoff_exclusive']) or case['company_id'] != row['company_id']
                    or case['case_type'] != row['case_type'] or case['if_coverage'] != row['if_coverage']
                    or case['member_count'] != int(row['member_count'])
                    or (row['if_score'] == '') != (case['if_score'] is None)
                    or (row['if_score'] and float(row['if_score']) != case['if_score'])):
                raise ValueError('Frozen selected scope or IF value differs from reconstruction')
            result, members = case_audit(case, cutoff, transactions, partitions, features, scores, run['run_id'])
            descriptor = dict(budget=budget, arm=row['arm'], day=row['day'], cutoff_exclusive=cutoff,
                company_id=row['company_id'], case_id=row['case_id'], case_scope_hash=row['case_scope_hash'],
                work_key=row['work_key'], work_type=row['work_type'], case_type=row['case_type'],
                frozen_if_coverage=row['if_coverage'])
            reviews.append(dict(descriptor, **result))
            member_rows.extend(dict(descriptor, **m) for m in members)
        summaries[str(budget)] = {arm: summarize([r for r in reviews if r['budget']==budget and r['arm']==arm])
                                  for arm in ('baseline','if_shadow')}
    breakdown = []
    for budget in (5, 10):
        for arm in ('baseline','if_shadow'):
            subset = [r for r in reviews if r['budget']==budget and r['arm']==arm]
            for dimension in ('company_id','month'):
                groups = sorted({r['company_id'] if dimension=='company_id' else r['day'][:7] for r in subset})
                for group in groups:
                    rows = [r for r in subset if (r['company_id'] if dimension=='company_id' else r['day'][:7])==group]
                    s = summarize(rows)
                    breakdown.append(dict(budget=budget, arm=arm, dimension=dimension, group=group,
                        transaction_work_reviews=s['transaction_work_reviews'], full_if_coverage=s['full_if_coverage'],
                        historical_only=s['reasons'].get('historical_only_unscored',0),
                        mixed_history_evaluation=s['reasons'].get('mixed_history_evaluation',0),
                        other_scope_exclusion=s['reasons'].get('other_scope_exclusion',0),
                        data_error=s['reasons'].get('data_error',0)))
    source_errors = Counter(e for r in source_rows for e in r['errors'].split('|') if e)
    selected_errors = sum(r['coverage_reason']=='data_error' for r in reviews)
    report = dict(version=VERSION, status='coverage_explained' if not source_errors and not selected_errors else 'data_defects_found',
        dataset=str(dataset), comparison=str(comparison), source_origin=metadata.get('data_origin'),
        windows=time_audit['plan'], summaries=summaries,
        source_transactions=len(transactions), source_partition_counts=dict(Counter(r['partition'] for r in source_rows)),
        source_feature_status=dict(Counter(r['feature_status'] for r in source_rows)),
        evaluation_transactions=sum(r['partition']=='evaluation' for r in source_rows),
        valid_evaluation_scores=sum(r['member_status']=='evaluation_scored' for r in source_rows),
        source_defects=dict(sorted(source_errors.items())),
        selected_review_data_errors=selected_errors,
        models_fitted=0, observations_scored=0, training_or_calibration_scored=False,
        queue_changed=False, evaluation_window_changed=False, independent_outcomes_added=0,
        coverage_policy='All members must have valid evaluation scores; history keeps its baseline position',
        denominator='Selected transaction review work, including continued reviews; not unique cases or transactions',
        limitations=['Source is simulated; data integrity does not prove detection or operational benefit',
            'Historical-only and mixed cases remain outside full IF coverage',
            'Evaluation contains earlier technical scores; no untouched field benchmark is asserted'])
    if any(sha(p)!=h for p,h in inputs.items()):
        raise ValueError('Frozen inputs changed during coverage audit')
    output.mkdir(parents=True)
    write_csv(output/'source_member_coverage.csv', source_rows, list(source_rows[0]))
    fields = list(dict.fromkeys(k for r in reviews for k in r))
    write_csv(output/'selected_review_coverage.private.csv', reviews, fields)
    write_csv(output/'selected_member_coverage.private.csv', member_rows, list(member_rows[0]))
    write_csv(output/'coverage_breakdown.csv', breakdown, list(breakdown[0]))
    write_json(output/'input_commitment.json', inputs)
    write_json(output/'summary.json', report)
    write_json(output/'output_commitment.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','baseline','comparison','temporal','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    report = audit_coverage(**vars(args))
    print(json.dumps(dict(status=report['status'], summaries=report['summaries']), ensure_ascii=False))


if __name__ == '__main__':
    main()
