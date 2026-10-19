"""Rebuild versioned train/validation caches and models without scoring test.

Legacy sources/reports stay immutable. Known synthetic callback chronology is
represented as an unverified observation followed by a verified revision.
Labels are joined only after predictions, thresholds and queue outputs freeze.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime
import gc
import hashlib
import json
from pathlib import Path
import platform
import time

from .evaluate import threshold_metrics, average_precision_score, np, sklearn, joblib
from sklearn.ensemble import IsolationForest
from .case_queue import review_queue, operational_members
from .feature_contract import (cache_contract, current_contract, digest, sha, validate_cache,
                                model_compatibility, require_model)
from .features import FEATURE_DESCRIPTIONS, build_features
from .generate import write_csv
from .exception_validation import flag, validated_tables
from .rules import DEFAULT_CONFIG, INPUT_TABLES, OPTIONAL_INPUT_TABLES, score_rules
from .run_rules import empirical_rank, evaluate_scores
from .run_rule_repairs import write_jsonl
from .evidence_evaluation import budget_review
from .review_store import ReviewStore

CUTOFF = '2025-07-01T00:00:00+07:00'
PERIODS = ('train', 'validation')
RULE_INPUTS = (*INPUT_TABLES, *OPTIONAL_INPUT_TABLES)
FEATURE_INPUTS = (*RULE_INPUTS, 'journal_lines')


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream)


def callback_revisions(rows, cutoff=CUTOFF, *, synthetic=False):
    result, repairs = [], []
    for row in rows:
        if row['observed_at'] >= cutoff:
            continue
        verified = flag(row['callback_verified'])
        if verified and row.get('verified_at') and row['verified_at'] > row['observed_at']:
            if not synthetic:
                raise ValueError('Cannot repair callback chronology without synthetic source provenance')
            # Parse before ordering/copying; other source domains are validated
            # afterward by the same R7 validator as the actual engine.
            datetime.fromisoformat(row['verified_at'])
            initial = dict(row, callback_verified='0', verified_at='', approver_id='')
            revision = dict(row, observed_at=row['verified_at'])
            versions = [initial, revision]
            repairs.append(dict(change_id=row['change_id'], company_id=row['company_id'],
                original_observed_at=row['observed_at'], verified_at=row['verified_at'],
                action='unverified_observation_then_verified_revision',
                included_revisions=sum(r['observed_at'] < cutoff for r in versions)))
        else:
            versions = [dict(row)]
        result.extend(r for r in versions if r['observed_at'] < cutoff)
    return result, repairs


def before_cutoff(row):
    for field in ('observed_at', 'recorded_at', 'posted_at', 'issued_at'):
        if row.get(field):
            return row[field] < CUTOFF
    return True


def derive(source, target):
    """Build all detector inputs first; neither label contents nor test X are used."""
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError(f'Derived dataset already exists: {target}')
    original = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    hashes = {'manifest.json': sha(source / 'manifest.json')}
    for name, entry in original['files'].items():
        actual = sha(source / name)
        if actual != entry['sha256']:
            raise ValueError(f'Original source checksum differs: {source / name}')
        hashes[name] = actual
    synthetic = 'synthetic' in original.get('assumptions', {}).get('ids', '').lower()
    tables, files, repairs = defaultdict(list), {}, []
    target.mkdir(parents=True)
    for name in original['files']:
        if name in {'features.csv', 'labels.csv', 'splits.csv'}:
            continue
        table = Path(name).stem
        rows = read_rows(source / name)
        if table == 'bank_account_changes':
            selected, repairs = callback_revisions(rows, synthetic=synthetic)
        else:
            selected = [r for r in rows if before_cutoff(r)]
        with (source / name).open(encoding='utf-8-sig', newline='') as stream:
            fields = csv.DictReader(stream).fieldnames or []
        write_csv(target / name, selected, fields)
        files[name] = dict(rows=len(selected), sha256=sha(target / name))
        if table in FEATURE_INPUTS:
            tables[table] = selected
    tables = validated_tables(tables)
    if not tables['transactions'] or any(r['posted_at'] >= CUTOFF for r in tables['transactions']):
        raise ValueError('Train/validation derivation includes an invalid observation range')
    ids = {r['transaction_id'] for r in tables['transactions']}
    if len(ids) != len(tables['transactions']):
        raise ValueError('Duplicate derived transaction ID')
    journal_ids = {r['transaction_id'] for r in tables.get('journal_lines', []) if r['transaction_id']}
    if any(int(r['is_financial_entry']) and r['transaction_id'] not in journal_ids for r in tables['transactions']):
        raise ValueError('Financial transaction has no primary journal lines in feature inputs')
    partitions = {r['transaction_id']: r['split'] for r in read_rows(source / 'splits.csv') if r['transaction_id'] in ids}
    if set(partitions) != ids or set(partitions.values()) != set(PERIODS):
        raise ValueError('Derived snapshot must contain exactly train and validation, no test')
    for row in tables['transactions']:
        expected = 'train' if row['posted_at'] < '2025-01-01T00:00:00+07:00' else 'validation'
        if partitions[row['transaction_id']] != expected:
            raise ValueError('Chronological split mismatch')
    manifest = dict(version='2.1-feature-sync', seed=original['seed'], companies=original['companies'],
        timezone=original['timezone'], currency='VND', requested_fraud_rate=original['requested_fraud_rate'],
        observation_unit=original['observation_unit'], feature_columns=list(FEATURE_DESCRIPTIONS), files=files,
        derivation=dict(source=str(source), source_sha256=hashes, cutoff_exclusive=CUTOFF,
            selected_periods=list(PERIODS), test_scored=False, synthetic_callback_revisions=len(repairs),
            label_selection='IDs/times only; labels copied and evaluated after predictions freeze'))
    write_json(target / 'manifest.json', manifest)
    write_json(target / 'callback_revision_log.json', repairs)
    return tables, partitions, manifest, hashes


def matrix_fingerprint(ids, x):
    return digest([list(ids), hashlib.sha256(np.ascontiguousarray(x, dtype=np.float32).tobytes()).hexdigest()])


def load_old_matrix(source, ids):
    positions = {identity: n for n, identity in enumerate(ids)}
    x, found = np.empty((len(ids), len(FEATURE_DESCRIPTIONS)), dtype=np.float32), set()
    for row in read_rows(Path(source) / 'features.csv'):
        identity = row['transaction_id']
        if identity not in positions:
            continue
        if identity in found:
            raise ValueError('Duplicate legacy feature row')
        found.add(identity)
        x[positions[identity]] = [float(row[c]) for c in FEATURE_DESCRIPTIONS]
    if found != set(ids) or not np.isfinite(x).all():
        raise ValueError('Incomplete/nonfinite legacy feature matrix')
    return x


def old_score_snapshot(baseline, ids):
    selected = []
    for row in read_rows(Path(baseline) / 'rule_scores.csv'):
        if row['transaction_id'] not in ids:
            continue
        for field in ('base_score', 'recurrence_points', 'rule_score', 'hard_trigger', 'operational_alert'):
            if field in row:
                row[field] = int(row[field])
        selected.append(row)
    selected.sort(key=lambda r: (r['posted_at'], r['transaction_id']))
    if {r['transaction_id'] for r in selected} != ids:
        raise ValueError('Legacy rule snapshot IDs differ')
    return selected


def active_hits(path, ids):
    result = defaultdict(set)
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['transaction_id'] in ids and row['points'] > 0:
                result[row['rule_id']].add(row['transaction_id'])
    return result


def top_capacity(values, ids, budget):
    k = int(np.ceil(len(ids) * budget))
    order = np.lexsort((np.array([hashlib.sha256(i.encode()).hexdigest() for i in ids]), -values))
    chosen = np.zeros(len(ids), dtype=bool)
    chosen[order[:k]] = True
    return chosen


def run_dataset(root, tag, budget=.003, jobs=4):
    started = time.monotonic()
    source, baseline = Path('data') / f'sme_fraud_{tag}', Path('reports/rules') / f'sme_fraud_{tag}'
    output, target = Path(root) / f'sme_fraud_{tag}', Path('data') / Path(root).name / f'sme_fraud_{tag}'
    if output.exists():
        raise FileExistsError(f'Output exists: {output}')
    output.mkdir(parents=True)
    original_model = Path('reports') / f'sme_fraud_{tag}' / 'isolation_forest.joblib'
    protected_reports = {str(p): sha(p) for p in (original_model, baseline / 'rule_scores.csv',
                        baseline / 'rule_hits.jsonl', baseline / 'case_queue.csv', baseline / 'case_events.csv',
                        baseline / 'rule_config.json')}
    print(f'{tag}: verify original sources; derive train/validation inputs', flush=True)
    tables, partitions, manifest, protected = derive(source, target)
    print(f'{tag}: rebuild causal feature cache ({len(tables["transactions"]):,} observations)', flush=True)
    features = build_features(tables)
    write_csv(target / 'features.csv', features, ['transaction_id', *FEATURE_DESCRIPTIONS])
    manifest['files']['features.csv'] = dict(rows=len(features), sha256=sha(target / 'features.csv'))
    manifest['feature_contract'] = cache_contract(manifest['files'])
    write_json(target / 'manifest.json', manifest)
    validate_cache(manifest)
    ids = [r['transaction_id'] for r in features]
    selected = set(ids)
    masks = {period: np.array([partitions[i] == period for i in ids]) for period in PERIODS}
    x = np.asarray([[r[c] for c in FEATURE_DESCRIPTIONS] for r in features], dtype=np.float32)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite rebuilt features')
    old_x = load_old_matrix(source, ids)
    delta = x != old_x
    feature_changes = dict(rows_changed=int(np.any(delta, axis=1).sum()), cells_changed=int(delta.sum()),
        columns={c: int(delta[:, j].sum()) for j, c in enumerate(FEATURE_DESCRIPTIONS) if delta[:, j].any()},
        ordered_columns_unchanged=True, matrix_fingerprint=matrix_fingerprint(ids, x),
        legacy_matrix_fingerprint=matrix_fingerprint(ids, old_x))
    write_json(output / 'feature_changes.json', feature_changes)
    old_artifact = joblib.load(original_model)
    legacy_compatibility = model_compatibility(old_artifact, manifest, sklearn.__version__)
    print(f'{tag}: legacy model incompatible={not legacy_compatibility["compatible"]}; fit train-only IF', flush=True)
    params = old_artifact['model'].get_params()
    params['n_jobs'] = jobs
    model = IsolationForest(**params).fit(x[masks['train']])
    new_if = -model.score_samples(x)
    old_if = -old_artifact['model'].score_samples(old_x)
    artifact = dict(model=model, feature_columns=list(FEATURE_DESCRIPTIONS),
        dataset_version=manifest['version'], seed=manifest['seed'], sklearn_version=sklearn.__version__,
        feature_contract_fingerprint=manifest['feature_contract']['fingerprint'],
        training_feature_fingerprint=matrix_fingerprint(np.array(ids)[masks['train']], x[masks['train']]),
        validation_feature_fingerprint=matrix_fingerprint(np.array(ids)[masks['validation']], x[masks['validation']]),
        score_direction='higher_is_more_anomalous', threshold=float(np.quantile(new_if[masks['validation']], 1-budget, method='higher')),
        requested_validation_alert_budget=budget, model_parameters=params)
    require_model(artifact, manifest, sklearn.__version__)
    joblib.dump(artifact, output / 'isolation_forest.joblib')
    restored = joblib.load(output / 'isolation_forest.joblib')
    require_model(restored, manifest, sklearn.__version__)
    if not np.array_equal(-restored['model'].score_samples(x[masks['validation']]), new_if[masks['validation']]):
        raise ValueError('Model serialization replay differs')
    del old_x, delta
    gc.collect()
    print(f'{tag}: score combined current rules; no labels loaded', flush=True)
    result = score_rules(tables, features=features)
    if [r['transaction_id'] for r in result['scores']] != ids:
        raise ValueError('Rule/model feature order differs')
    old_scores = old_score_snapshot(baseline, selected)
    current_rules = np.asarray([r['rule_score'] for r in result['scores']], dtype=float)
    previous_rules = np.asarray([r['rule_score'] for r in old_scores], dtype=float)
    values = {}
    for version, rules, forest in (('before', previous_rules, old_if), ('after', current_rules, new_if)):
        values[version] = dict(rules_graph=rules, isolation_forest=forest,
            ensemble=.8*empirical_rank(rules[masks['validation']], rules) + .2*empirical_rank(forest[masks['validation']], forest))
    thresholds = {v: {k: float(np.quantile(a[masks['validation']], 1-budget, method='higher'))
                      for k, a in modes.items()} for v, modes in values.items()}
    cases, events = review_queue(result, tables)
    old_result = dict(scores=old_scores, config=result['config'], batch_events=[])
    old_cases, old_events = review_queue(old_result, tables)
    # A review aid only: overlapping transactions do not authorize transfer of
    # feedback across changed scopes. Production migration uses R6 separately.
    owners = {i: c['case_id'] for c in cases for i in json.loads(c['transaction_ids'])}
    identity_changes = [dict(previous_case_id=c['case_id'],
        current_case_ids=sorted({owners[i] for i in json.loads(c['transaction_ids']) if i in owners}),
        previous_members=json.loads(c['transaction_ids']),
        automatic_feedback_transfer=False) for c in old_cases]
    write_json(output / 'case_identity_comparison.json', identity_changes)
    if {t for c in cases for t in json.loads(c['transaction_ids'])} != operational_members(result):
        raise ValueError('Queue membership does not reconcile')
    write_csv(output / 'rule_scores.csv', [{k:v for k,v in r.items() if k != 'known_risky_prior_ids'} for r in result['scores']])
    write_jsonl(output / 'rule_hits.jsonl', result['hits'])
    write_jsonl(output / 'batch_events.jsonl', result['batch_events'])
    write_jsonl(output / 'evidence_findings.jsonl', result['evidence_findings'])
    write_csv(output / 'case_queue.csv', cases)
    write_csv(output / 'case_events.csv', events)
    write_json(output / 'rule_config.json', result['config'])
    write_json(output / 'rule_coverage.json', result['coverage'])
    predictions = [dict(transaction_id=i, period=partitions[i],
        **{f'{v}_{k}': float(a[n]) for v, modes in values.items() for k, a in modes.items()}) for n, i in enumerate(ids)]
    write_csv(output / 'predictions_train_validation.csv', predictions)
    frozen = dict(thresholds=thresholds, validation_alert_budget=budget, model_parameters=params,
        train_rows=int(masks['train'].sum()), validation_rows=int(masks['validation'].sum()), test_rows=0,
        predictions_sha256=sha(output / 'predictions_train_validation.csv'),
        rule_scores_sha256=sha(output / 'rule_scores.csv'), rule_hits_sha256=sha(output / 'rule_hits.jsonl'),
        model_sha256=sha(output / 'isolation_forest.joblib'), labels_loaded=False)
    write_json(output / 'predictions_frozen.json', frozen)
    print(f'{tag}: predictions frozen; evaluate train/validation labels only', flush=True)
    labels = {r['transaction_id']: r for r in read_rows(source / 'labels.csv') if r['transaction_id'] in selected}
    if set(labels) != selected:
        raise ValueError('Label IDs differ from frozen observations')
    for name in ('labels.csv', 'splits.csv'):
        rows = [r for r in read_rows(source / name) if r['transaction_id'] in selected]
        write_csv(target / name, rows, list(rows[0]))
        manifest['files'][name] = dict(rows=len(rows), sha256=sha(target / name))
    manifest['splits'] = {p: dict(rows=int(masks[p].sum()), fraud_rows=sum(int(labels[i]['is_fraud']) for i in ids if partitions[i] == p)) for p in PERIODS}
    write_json(target / 'manifest.json', manifest)
    validate_cache(manifest)
    old_active = active_hits(baseline / 'rule_hits.jsonl', selected)
    new_active = defaultdict(set)
    for hit in result['hits']:
        if hit['suppressed_reason'] and (hit['points'] or hit['hard_trigger']):
            raise ValueError('Suppressed evidence contributes to score')
        if hit['points'] > 0:
            new_active[hit['rule_id']].add(hit['transaction_id'])
    tx = {r['transaction_id']: r for r in tables['transactions']}
    report = dict(dataset=str(target), original_source=str(source), baseline=str(baseline),
        legacy_model_compatibility=legacy_compatibility, new_model_compatibility=require_model(restored, manifest, sklearn.__version__),
        feature_changes=feature_changes, periods={}, rules=[], score_changes=[], workload=[], companies=[], queue_metrics=[],
        model_refitted=True, test_scored=False, label_rows_loaded=len(labels),
        policy='Preset 0.8/0.2 validation midrank ensemble; unlabeled validation quantiles; no label tuning',
        baseline_policy='Frozen original report/rules snapshot, not an isolated R1-R8 ablation',
        duration_seconds=0)
    changed_hits = []
    for period in PERIODS:
        mask = masks[period]
        period_ids = [i for i in ids if partitions[i] == period]
        y = np.array([int(labels[i]['is_fraud']) for i in period_ids])
        measured = dict(rows=len(y), fraud_rows=int(y.sum()), before={}, after={})
        for version, modes in values.items():
            for mode, a in modes.items():
                subset = a[mask]
                threshold = thresholds[version][mode]
                chosen = subset >= threshold
                measured[version][mode] = dict(average_precision=float(average_precision_score(y, subset)),
                    threshold_metrics=threshold_metrics(y, subset, threshold),
                    fixed_capacity=evaluate_scores(y, subset, top_capacity(subset, period_ids, budget), labels, tx, period_ids))
        for version, scores in (('before', old_scores), ('after', result['scores'])):
            operational = np.array([bool(r['operational_alert']) for r in scores])[mask]
            measured[version]['operational'] = evaluate_scores(y, current_rules[mask], operational, labels, tx, period_ids)
            for company in sorted({tx[i]['company_id'] for i in period_ids}):
                company_mask = np.array([tx[i]['company_id'] == company for i in period_ids])
                report['companies'].append(dict(version=version, period=period, company_id=company,
                    **threshold_metrics(y[company_mask], operational[company_mask].astype(float), 1.)))
        report['periods'][period] = measured
        for code in sorted(set(old_active) | set(new_active)):
            old, new = old_active[code] & set(period_ids), new_active[code] & set(period_ids)
            report['rules'].append(dict(period=period, rule_id=code,
                before=evaluate_scores(y, np.zeros(len(y)), np.array([i in old for i in period_ids]), labels, tx, period_ids),
                after=evaluate_scores(y, np.zeros(len(y)), np.array([i in new for i in period_ids]), labels, tx, period_ids),
                added=len(new-old), removed=len(old-new)))
            changed_hits.extend(dict(period=period, rule_id=code, direction=direction, transaction_id=i,
                is_fraud=labels[i]['is_fraud'], hard_negative_type=labels[i]['hard_negative_type'])
                for direction, members in (('added', new-old), ('removed', old-new)) for i in sorted(members))
        changed = [n for n, i in enumerate(ids) if partitions[i] == period and current_rules[n] != previous_rules[n]]
        report['score_changes'].append(dict(period=period, rows_changed=len(changed),
            before_cases=sum(c['opened_at'][:4] == ('2024' if period == 'train' else '2025') for c in old_cases),
            after_cases=sum(c['opened_at'][:4] == ('2024' if period == 'train' else '2025') for c in cases),
            batch_events=sum(partitions[e['transaction_ids'][0]] == period for e in result['batch_events'])))
        for version, queue, history in (('before', old_cases, old_events), ('after', cases, events)):
            selected_cases = [c for c in queue if c['opened_at'][:4] == ('2024' if period == 'train' else '2025')]
            member_sets = [set(json.loads(c['transaction_ids'])) & set(period_ids) for c in selected_cases]
            useful = sum(any(int(labels[i]['is_fraud']) for i in members) for members in member_sets)
            report['queue_metrics'].append(dict(version=version, period=period, cases=len(selected_cases),
                cases_with_fraud_at_cutoff=useful, cases_without_fraud_at_cutoff=len(selected_cases)-useful,
                precision_at_cutoff=useful/len(selected_cases) if selected_cases else None,
                note='Retrospective member labels, not independent reviewer conclusions; opening-time diagnostic is in workload.'))
            for capacity in (1, 3, 5):
                measure = budget_review(selected_cases, history, tx, labels, capacity)
                measure.pop('admissions')
                report['workload'].append(dict(version=version, period=period, **measure))
    write_csv(output / 'changed_hits_train_validation.csv', changed_hits)
    store = ReviewStore(target.parent, Path(root), Path(root) / f'review_{tag}.sqlite3', scenarios=[tag])
    store.prepare()
    report['review_cache_cases'] = store.list_cases(tag, status='all', limit=1)['total']
    report['review_cache_loaded'] = True
    report['duration_seconds'] = round(time.monotonic()-started, 3)
    report['original_sources_unchanged'] = all(sha(source / name) == value for name, value in protected.items())
    report['legacy_reports_and_model_sha256'] = protected_reports
    report['legacy_reports_and_model_unchanged'] = all(sha(Path(name)) == value for name, value in protected_reports.items())
    if not report['original_sources_unchanged'] or not report['legacy_reports_and_model_unchanged'] or sha(output / 'predictions_train_validation.csv') != frozen['predictions_sha256']:
        raise ValueError('Protected source/prediction changed during evaluation')
    write_json(output / 'comparison_train_validation.json', report)
    print(f'{tag}: completed in {report["duration_seconds"]:.1f}s; {len(cases):,} review cases', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('reports/feature_model_sync_20261016'))
    parser.add_argument('--tags', nargs='+', default=['001', '003', '005'], choices=['001', '003', '005'])
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        raise ValueError('jobs must be 1..8')
    args.output.mkdir(parents=True, exist_ok=True)
    code = Path(__file__).resolve().parent
    source_hashes = {str(p): sha(p) for p in code.glob('*.py')}
    source_hashes.update({str(p): sha(p) for p in code.glob('*.schema.json')})
    plan = dict(periods=list(PERIODS), cutoff_exclusive=CUTOFF, tags=args.tags, feature_contract=current_contract(),
        rule_config=DEFAULT_CONFIG, validation_alert_budget=.003, model_policy='Refit existing IF configuration on train only',
        threshold_policy='Unlabeled validation quantile, method higher; no test access for scoring',
        source_sha256=source_hashes, python=platform.python_version(), sklearn=sklearn.__version__, numpy=np.__version__,
        initial_stage='frozen_before_any_dataset_labels_are_loaded')
    plan_path = args.output / 'evaluation_plan.json'
    if plan_path.exists():
        previous = json.loads(plan_path.read_text(encoding='utf-8'))
        if previous != plan:
            raise ValueError('Evaluation plan/code differs; use a new output root')
    else:
        write_json(plan_path, plan)
    results = []
    for tag in args.tags:
        summary = args.output / f'sme_fraud_{tag}' / 'comparison_train_validation.json'
        if summary.exists():
            results.append(json.loads(summary.read_text(encoding='utf-8')))
        else:
            results.append(run_dataset(args.output, tag, jobs=args.jobs))
        gc.collect()
    if any(sha(Path(name)) != value for name, value in source_hashes.items()):
        raise ValueError('Implementation changed during the frozen evaluation')
    write_json(args.output / 'summary.json', dict(successful=True, test_scored=False, results=results,
        source_sha256=source_hashes, total_observations=sum(sum(p['rows'] for p in r['periods'].values()) for r in results)))


if __name__ == '__main__':
    main()
