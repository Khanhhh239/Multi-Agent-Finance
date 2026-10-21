"""Replay train/validation against the frozen sync snapshot after admission repair."""
from __future__ import annotations

import argparse
from collections import Counter
import gc
import json
from pathlib import Path
import time

from .evaluate import np, joblib, sklearn
from .feature_contract import current_contract, digest, require_model, sha
from .rules import DEFAULT_CONFIG, load_inputs, score_rules
from .case_queue import review_queue, operational_members
from .generate import write_csv
from .sync_feature_model import PERIODS, CUTOFF, read_rows, write_json
from .run_rule_repairs import write_jsonl
from .run_rules import evaluate_scores
from .evidence_evaluation import budget_review
from .review_store import ReviewStore
from .review_capacity import workload_scenarios
from .admission_export import explain_admissions, FIELDS as ADMISSION_EXPORT_FIELDS

BASELINE = Path('reports/feature_model_sync_20261017')
DATA = Path('data/feature_model_sync_20261017')
FIXED_FIELDS = ('base_score', 'recurrence_points', 'rule_score', 'rule_ids', 'hard_trigger',
                'case_entity', 'case_cluster_members', 'explanation_vi')


def jsonl(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def content_signature(records):
    # CSV feature loading converts integer-valued features to floats. Compare
    # JSON evidence by numeric value, preserving booleans, rather than 0 vs 0.0.
    def canonical(value):
        if type(value) is float and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    return Counter(digest(canonical(r)) for r in records)


def a4_trace(tables, result):
    """Known loss diagnosis only; IDs never affect the admission policy."""
    identity = 'T000081861'
    tx = {r['transaction_id']: r for r in tables['transactions']}
    if identity not in tx:
        return None
    row = tx[identity]
    legacy = next(h for h in jsonl(Path('reports/rules/sme_fraud_003/rule_hits.jsonl'))
                  if h['transaction_id'] == identity and h['rule_id'] == 'A4')
    current_month_near = [r for r in tx.values() if r['company_id'] == row['company_id']
        and r['creator_id'] == row['creator_id'] and r['posted_at'] <= row['posted_at']
        and r['posted_at'][:7] == row['posted_at'][:7] and int(r['is_financial_entry'])
        and r['payment_channel'] in {'bank', 'cash'} and r['txn_type'] != 'customer_receipt'
        and .8 <= int(r['amount_vnd'])/int(r['approval_limit_vnd']) <= .99]
    followup = [h for h in result['hits'] if h['points'] > 0 and identity in h['related_transaction_ids']]
    followup.sort(key=lambda h: (h['detected_at'], h['transaction_id'], h['rule_id']))
    fields = ('transaction_id', 'posted_at', 'company_id', 'creator_id', 'txn_type',
              'amount_vnd', 'approval_limit_vnd', 'vendor_id', 'recipient_account')
    return dict(transaction_id=identity, current={k: row[k] for k in fields},
        legacy_a4_prior=[{k: tx[i][k] for k in fields} for i in legacy['related_transaction_ids']],
        current_month_near_count_at_transaction=len(current_month_near),
        current_month_ids=sorted(r['transaction_id'] for r in current_month_near),
        current_a4_present=any(h['transaction_id'] == identity and h['rule_id'] == 'A4' and h['points'] > 0 for h in result['hits']),
        first_followup={k: followup[0][k] for k in ('transaction_id', 'detected_at', 'rule_id', 'points')} if followup else None,
        conclusion='Legacy rolling-window context is in May; calendar-month A4 correctly has insufficient June observations at the first payment. Later detection is distinct from immediate row admission.')


def run(root, tag):
    started = time.monotonic()
    data, before_path, output = DATA/f'sme_fraud_{tag}', BASELINE/f'sme_fraud_{tag}', root/f'sme_fraud_{tag}'
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    output.mkdir(parents=True)
    protected = {str(p): sha(p) for p in data.glob('*') if p.is_file()}
    protected.update({str(p): sha(p) for p in before_path.glob('*') if p.is_file() and p.name != '.feedback.lock'})
    print(f'{tag}: load compatible feature cache; replay raw rule engine on train/validation', flush=True)
    tables, features, meta = load_inputs(data)
    splits = {r['transaction_id']: r['split'] for r in read_rows(data/'splits.csv')}
    ids = [r['transaction_id'] for r in features]
    if set(splits.values()) != set(PERIODS) or set(splits) != set(ids) or any(r['posted_at'] >= CUTOFF for r in tables['transactions']):
        raise ValueError('This replay only permits the frozen train/validation snapshot')
    model_path = before_path/'isolation_forest.joblib'
    artifact = joblib.load(model_path)
    compatibility = require_model(artifact, meta, sklearn.__version__)
    del artifact
    replay_config = json.loads((before_path/'rule_config.json').read_text(encoding='utf-8'))
    replay_config.setdefault('cash_payment_policy', 'disabled')
    replay_config['split_pattern_policy'] = DEFAULT_CONFIG['split_pattern_policy']
    result = score_rules(tables, features=features, config=replay_config)
    before = {r['transaction_id']: r for r in read_rows(before_path/'rule_scores.csv')}
    for r in result['scores']:
        for field in FIXED_FIELDS:
            if str(r[field]) != str(before[r['transaction_id']][field]):
                raise ValueError(f'Numeric/predicate replay differs: {tag}/{r["transaction_id"]}/{field}')
        if int(before[r['transaction_id']]['operational_alert']) and not r['operational_alert']:
            raise ValueError('Admission policy removed an existing operational alert')
    if content_signature(jsonl(before_path/'rule_hits.jsonl')) != content_signature(result['hits']):
        raise ValueError('Admission repair unexpectedly changed per-rule evidence')
    if content_signature(jsonl(before_path/'batch_events.jsonl')) != content_signature(result['batch_events']):
        raise ValueError('Admission repair unexpectedly changed batch evidence')
    cases, events = review_queue(result, tables)
    members = {t for c in cases for t in json.loads(c['transaction_ids'])}
    if members != operational_members(result):
        raise ValueError('Review membership does not reconcile')
    for name, records in (('rule_scores', [{k:v for k,v in r.items() if k != 'known_risky_prior_ids'} for r in result['scores']]),
                          ('case_queue', cases), ('case_events', events)):
        write_csv(output/f'{name}.csv', records)
    for name, records in (('rule_hits', result['hits']), ('batch_events', result['batch_events']), ('evidence_findings', result['evidence_findings'])):
        write_jsonl(output/f'{name}.jsonl', records)
    write_json(output/'rule_config.json', result['config'])
    write_json(output/'rule_coverage.json', result['coverage'])
    frozen = dict(labels_loaded=False, rows=len(ids), test_rows=0, operational_score=result['config']['operational_score'],
        policy=result['config']['split_pattern_policy'],
        sha256={p.name: sha(p) for p in output.glob('*') if p.is_file()},
        predicate_hits_unchanged=True, numeric_scores_and_hard_triggers_unchanged=True,
        feature_contract_fingerprint=meta['feature_contract']['fingerprint'], model_sha256=sha(model_path))
    write_json(output/'predictions_frozen.json', frozen)
    print(f'{tag}: predicates/points/hard triggers unchanged; admission frozen, join labels for metrics', flush=True)
    labels = {r['transaction_id']: r for r in read_rows(data/'labels.csv')}
    if set(labels) != set(ids):
        raise ValueError('Unexpected label IDs')
    tx = {r['transaction_id']: r for r in tables['transactions']}
    previous_scores = [before[i] for i in ids]
    previous_config = json.loads((before_path/'rule_config.json').read_text(encoding='utf-8'))
    previous_result = dict(scores=previous_scores, config=previous_config, batch_events=list(jsonl(before_path/'batch_events.jsonl')))
    # CSV booleans must be decoded before the generic membership helper.
    for r in previous_scores:
        r['operational_alert'] = int(r['operational_alert'])
    old_members = operational_members(previous_result)
    old_cases, old_events = list(read_rows(before_path/'case_queue.csv')), list(read_rows(before_path/'case_events.csv'))
    report = dict(tag=tag, data=str(data), baseline=str(before_path), periods={}, workload=[], companies=[],
        policy=result['config']['split_pattern_policy'], numeric_scores_unchanged=True, predicate_hits_unchanged=True,
        hard_triggers_unchanged=True, model_compatibility=compatibility, model_refitted=False,
        model_usage='Compatible frozen model; feature semantics and all numeric scores unchanged, so no refit or ensemble recalibration',
        source_unchanged=False, test_scored=False, admission_counts=dict(Counter(r['admission_basis'] for r in result['scores'])))
    changed = []
    for period in PERIODS:
        period_ids = [i for i in ids if splits[i] == period]
        y = np.array([int(labels[i]['is_fraud']) for i in period_ids])
        measures = dict(rows=len(period_ids), fraud_rows=int(y.sum()))
        for version, admitted in (('before', old_members), ('after', members)):
            selected = np.array([i in admitted for i in period_ids])
            measures[version] = evaluate_scores(y, np.zeros(len(y)), selected, labels, tx, period_ids)
            for company in sorted({tx[i]['company_id'] for i in period_ids}):
                company_ids = [i for i in period_ids if tx[i]['company_id'] == company]
                truth = np.array([int(labels[i]['is_fraud']) for i in company_ids])
                chosen = np.array([i in admitted for i in company_ids])
                report['companies'].append(dict(period=period, version=version, company_id=company,
                    **evaluate_scores(truth, np.zeros(len(truth)), chosen, labels, tx, company_ids)))
        gained = (members-old_members) & set(period_ids)
        measures.update(added_alerts=len(gained), added_fraud_alerts=sum(int(labels[i]['is_fraud']) for i in gained),
                        removed_alerts=len((old_members-members) & set(period_ids)))
        report['periods'][period] = measures
        changed.extend(dict(transaction_id=i, period=period, is_fraud=labels[i]['is_fraud'], fraud_type=labels[i]['fraud_type'],
            hard_negative_type=labels[i]['hard_negative_type'], rule_score=next_score['rule_score'],
            review_rule_ids=next_score['review_rule_ids'], admission_basis=next_score['admission_basis'])
            for next_score in result['scores'] if (i := next_score['transaction_id']) in gained)
        for version, queue, history in (('before', old_cases, old_events), ('after', cases, events)):
            subset = [c for c in queue if c['opened_at'][:4] == ('2024' if period == 'train' else '2025')]
            for profile, kind, capacity in workload_scenarios():
                load = budget_review(subset, history, tx, labels, capacity.slots,
                    capacity_minutes=capacity.minutes,
                    period_end='2024-12-31' if period == 'train' else '2025-06-30')
                load.pop('admissions')
                report['workload'].append(dict(period=period, version=version,
                    capacity_profile=profile, profile_kind=kind, **load))
    write_csv(output/'added_admissions.csv', changed)
    detailed, admission_evidence = explain_admissions(result, cases, members-old_members,
        metadata={row['transaction_id']: row for row in changed})
    write_csv(output/'added_admissions_v2.csv', detailed, list(ADMISSION_EXPORT_FIELDS))
    write_jsonl(output/'admission_evidence.jsonl', admission_evidence)
    write_json(output/'admission_export_commitment.json', dict(version='admission-provenance-v2',
        sha256={name: sha(output/name) for name in ('added_admissions_v2.csv', 'admission_evidence.jsonl')},
        membership_unchanged=True, row_scores_flags_hard_triggers_unchanged=True))
    # Compare identifiers by shared transactions for review, never transfer feedback automatically.
    new_owners = {i: c['case_id'] for c in cases for i in json.loads(c['transaction_ids'])}
    write_json(output/'case_identity_comparison.json', [dict(previous_case_id=c['case_id'],
        current_case_ids=sorted({new_owners[i] for i in json.loads(c['transaction_ids']) if i in new_owners}),
        automatic_feedback_transfer=False) for c in old_cases])
    if tag == '003':
        write_json(output/'a4_boundary_trace.json', a4_trace(tables, result))
    store = ReviewStore(DATA, root, root/f'review_{tag}.sqlite3', scenarios=[tag])
    store.prepare()
    count = store.list_cases(tag, status='all', limit=1)['total']
    if count != len(cases):
        raise ValueError('Review cache case count differs')
    store.prepare()
    if any(sha(output/name) != value for name, value in frozen['sha256'].items()):
        raise ValueError('Frozen prediction/report changed during evaluation')
    report.update(review_cases=count, review_cache_replay=True,
        source_unchanged=all(sha(Path(p)) == value for p,value in protected.items()),
        protected_sha256=protected, seconds=round(time.monotonic()-started, 3))
    if not report['source_unchanged']:
        raise ValueError('Source/baseline/model changed')
    write_json(output/'comparison.json', report)
    print(f'{tag}: complete, {count:,} review cases, validation added TP={report["periods"]["validation"]["added_fraud_alerts"]}', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('reports/split_pattern_admission_20261017_v2'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    code = Path(__file__).resolve().parent
    frozen_code = {str(p):sha(p) for p in (*code.glob('*.py'), *code.glob('*.schema.json'))}
    plan = dict(periods=list(PERIODS), test_scored=False, cutoff_exclusive=CUTOFF,
        admission_policy=DEFAULT_CONFIG['split_pattern_policy'], other_policies='frozen baseline rule_config.json',
        feature_contract=current_contract(), labels_used_for_policy=False,
        policy='Admit already evaluated unsuppressed A2/A4; no score, threshold, hard trigger, feature or model change',
        source_sha256=frozen_code)
    plan_path = args.output/'evaluation_plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text(encoding='utf-8')) != plan:
        raise ValueError('Plan/code differs; use a new output root')
    write_json(plan_path, plan)
    reports = []
    for tag in ('001', '003', '005'):
        path = args.output/f'sme_fraud_{tag}/comparison.json'
        reports.append(json.loads(path.read_text(encoding='utf-8')) if path.exists() else run(args.output, tag))
        gc.collect()
    if any(sha(Path(p)) != value for p,value in frozen_code.items()):
        raise ValueError('Code changed during the evaluation')
    write_json(args.output/'summary.json', dict(successful=True, test_scored=False, observations=225000,
        reports=reports, source_sha256=frozen_code))


if __name__ == '__main__':
    main()
