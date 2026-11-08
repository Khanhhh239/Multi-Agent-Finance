"""Fresh synthetic source rehearsal, distinct from real-data acceptance."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gc
import json
from pathlib import Path
import shutil

from .synthetic_dataset import export_world, write_json
from .synthetic_world import AS_OF, VARIANTS
from .feature_contract import sha
from .generate import write_csv
from .rules import load_inputs, score_rules, DEFAULT_CONFIG
from .real_source_acceptance import (review_universe, predictions_from_result,
    PACKET_FIELDS, inventory_ready, RULES, _looks_synthetic)
from .source_snapshot import inspect_sources
from .case_queue import review_queue
from .review_store import ReviewStore
from .review_capacity import ReviewCalendar, workload_scenarios
from .evidence_evaluation import boolean_metrics, budget_review
from .run_rule_repairs import write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def key(row):
    return tuple(row[name] for name in ('company_id', 'rule_id', 'unit_type', 'unit_id'))


def select_packet(universe, controls, per_stratum=20):
    """Source-defined controls plus a hash sample of unlabelled background."""
    wanted = {key(row) for row in controls}
    available = {key(row) for row in universe}
    if wanted - available:
        raise ValueError(f'Oracle units outside source-defined universe: {sorted(wanted-available)[:3]}')
    packet = [row for row in universe if key(row) in wanted]
    groups = defaultdict(list)
    for row in universe:
        if key(row) not in wanted:
            groups[(row['company_id'], row['rule_id'], row['unit_type'])].append(row)
    for rows in groups.values():
        packet.extend(sorted(rows, key=lambda row: row['review_id'])[:per_stratum])
    return sorted(packet, key=key)


def metrics(comparisons):
    result = boolean_metrics(comparisons)
    result['all_unit_matches'] = sum(row['expected'] is row['actual'] for row in comparisons)
    result['all_unit_agreement'] = result['all_unit_matches']/len(comparisons) if comparisons else None
    # Do not hide abstentions or unknown-condition false positives in TP/FP.
    result['mismatches_including_unknown'] = len(comparisons)-result['all_unit_matches']
    result['known_expected_abstentions'] = sum(row['expected'] is not None and row['actual'] is None for row in comparisons)
    result['unknown_expected_nonabstentions'] = sum(row['expected'] is None and row['actual'] is not None for row in comparisons)
    return result


def migration_rehearsal(data_root, reports_root, output, tag, cases):
    """Isolated SQLite and simulated feedback only; never touch user history."""
    root = output/'migration_rehearsal'
    data = root/'data'/f'sme_fraud_{tag}'
    report = root/'reports'/f'sme_fraud_{tag}'
    data.mkdir(parents=True)
    report.mkdir(parents=True)
    for name in ('transactions', 'companies', 'employees', 'vendors', 'customers', 'journal_documents', 'journal_lines'):
        shutil.copy2(data_root/f'sme_fraud_{tag}'/f'{name}.csv', data/f'{name}.csv')
    for name in ('case_queue.csv', 'case_events.csv', 'rule_hits.jsonl', 'rule_coverage.json', 'batch_events.jsonl', 'evidence_findings.jsonl'):
        shutil.copy2(reports_root/f'sme_fraud_{tag}'/name, report/name)
    store = ReviewStore(root/'data', root/'reports', root/'review.sqlite3', scenarios=[tag],
        clock=lambda: datetime.fromisoformat('2026-01-10T10:00:00+07:00'))
    store.prepare()
    chosen = next(case for case in cases if case['case_type'] != 'source')
    old_id = chosen['case_id']
    detail = store.detail(tag, old_id)
    old_owner = detail['case']['owner_id']
    event = store.save_feedback(tag, old_id, 'information_gap', 'SIM_REHEARSAL_BOT',
        'Synthetic migration exercise; not a reviewer conclusion', '')
    audit_before = sha(report/'feedback_audit.jsonl')
    # Export order changes; one exact-equivalent ID is migrated explicitly.
    for name in ('employees', 'vendors'):
        from .real_source_acceptance import read_csv
        rows = read_csv(data/f'{name}.csv')
        write_csv(data/f'{name}.csv', list(reversed(rows)), list(rows[0]))
    current = json.loads(json.dumps(cases))
    new_id = 'SIM_EQ_'+old_id
    for case in current:
        if case['case_id'] == old_id:
            case.update(case_id=new_id, owner_id='SIM_DIFFERENT_DEFAULT')
    write_csv(report/'case_queue.csv', current)
    store.prepare()
    after = store.detail(tag, new_id)['case']
    admitted = store.admissions(tag)[0]
    checks = dict(equivalent_feedback_preserved=after['feedback']['event_hash'] == event['event_hash'],
        equivalent_assignment_preserved=after['owner_id'] == old_owner,
        equivalent_admission_preserved=new_id in admitted and old_id not in admitted,
        audit_chain_unchanged=sha(report/'feedback_audit.jsonl') == audit_before)
    # Changed evidence with a new ID must not inherit the synthetic conclusion.
    hits = [json.loads(line) for line in (report/'rule_hits.jsonl').read_text(encoding='utf-8').splitlines()]
    tids = json.loads(chosen['transaction_ids'])
    hit = next(row for row in hits if row['transaction_id'] in tids)
    hit['evidence']['synthetic_revision_probe'] = 'changed source evidence'
    write_jsonl(report/'rule_hits.jsonl', hits)
    changed_id = 'SIM_CHANGED_'+old_id
    for case in current:
        if case['case_id'] == new_id:
            case.update(case_id=changed_id, owner_id=old_owner)
    write_csv(report/'case_queue.csv', current)
    store.prepare()
    changed = store.detail(tag, changed_id)['case']
    checks.update(changed_scope_no_feedback=changed['feedback'] is None,
        changed_scope_no_admission=changed_id not in store.admissions(tag)[0],
        audit_chain_still_unchanged=sha(report/'feedback_audit.jsonl') == audit_before)
    if not all(checks.values()):
        raise AssertionError(f'Synthetic R6 migration mismatch: {checks}')
    return dict(status='synthetic_rehearsal_passed', real_history_migrated=False,
        simulated_reviewer='SIM_REHEARSAL_BOT', independent_reviewed_units=0,
        audit_sha256=audit_before, old_case_id=old_id, equivalent_case_id=new_id,
        changed_case_id=changed_id, checks=checks)


def run(data_root, output, *, seeds=(2026101701, 2026101702, 2026101703), companies=8, background_rows=12000):
    data_root, output = Path(data_root).resolve(), Path(output).resolve()
    if data_root.exists() or output.exists():
        raise FileExistsError('Use fresh data and report roots')
    if len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError('Three distinct seeds required: two reporting, one unscored holdout')
    protected = {}
    baseline = ROOT/'reports/a4_pattern_trial_20261017_v2/summary.json'
    if baseline.exists():
        protected.update(read(baseline)['protected_sha256'])
        protected[str(baseline.relative_to(ROOT))] = sha(baseline)
    for tag in ('001', '003', '005'):
        manifest = ROOT/f'data/feature_model_sync_20261017/sme_fraud_{tag}/manifest.json'
        if manifest.exists():
            protected.update({f'data/sme_fraud_{tag}/{name}': expected for name, expected
                in read(manifest)['derivation']['source_sha256'].items()})
        previous = ROOT/f'reports/feature_model_sync_20261017/sme_fraud_{tag}/comparison_train_validation.json'
        if previous.exists():
            protected.update(read(previous)['legacy_reports_and_model_sha256'])
    for name, expected in protected.items():
        if sha(ROOT/name) != expected:
            raise ValueError(f'Protected baseline changed before rehearsal: {name}')
    output.mkdir(parents=True)
    source_code = {str(path.relative_to(ROOT)): sha(path) for path in (ROOT/'sme_fraud').glob('*.py')}
    plan = dict(version='synthetic-source-rehearsal-v1', seeds=list(seeds),
        seed_roles=['reporting', 'reporting', 'blind_holdout_unscored'], companies=companies,
        background_random_rows_per_seed=background_rows, control_repetitions=2,
        priors='Illustrative heterogeneous SME process assumptions, not calibrated real-world rates',
        source_scenarios=VARIANTS, configuration=DEFAULT_CONFIG,
        criterion='All declared source-condition outcomes including unknown must match; failures remain visible',
        criteria_scope='frozen_for_synthetic_exercise_only',
        packet_selection='All enriched source controls plus 20 hash-selected background units per company/rule/type',
        sample_weights='1; enriched packet is diagnostic, no population extrapolation',
        holdout_policy='Generate sources/cache/packet; do not score detector or model',
        background_truth='unlabelled; never assume ordinary background is a true negative',
        model_fit=False, model_scored=False, real_gate='awaiting_real_data',
        independent_reviewed_units=0, code_sha256=source_code)
    write_json(output/'evaluation_plan.json', plan)
    # Every cohort, its scenario registry and its truth are frozen before scoring.
    tags = ('001', '003', '005')
    for tag, seed, role in zip(tags, seeds, plan['seed_roles']):
        export_world(data_root/f'sme_fraud_{tag}', output/f'sme_fraud_{tag}', seed,
            role=role, companies=companies, background_rows=background_rows)
        print(f'{tag}: synthetic sources and causal feature cache frozen, seed={seed}, role={role}', flush=True)
        gc.collect()
    summaries = []
    for tag in tags:
        data, target = data_root/f'sme_fraud_{tag}', output/f'sme_fraud_{tag}'
        tables, features, manifest = load_inputs(data)
        controls = read(target/'sealed_truth/oracle.json')
        universe = review_universe(tables, '2025-01-01T00:00:00+07:00', AS_OF, sha(data/'manifest.json'))
        packet = select_packet(universe, controls)
        write_csv(target/'review_packet.csv', packet, list(PACKET_FIELDS))
        write_json(target/'packet_commitment.json', dict(packet_sha256=sha(target/'review_packet.csv'),
            universe_units=len(universe), packet_units=len(packet), before_predictions=True,
            reviewer_conclusions=0, role=manifest['role']))
        if tag == '005':
            write_json(target/'holdout_status.json', dict(status='sealed_unscored', detector_scored=False,
                model_scored=False, human_reviewed_units=0, real_acceptance=False))
            summaries.append(dict(tag=tag, seed=manifest['seed'], role=manifest['role'],
                transactions=len(tables['transactions']), packet_units=len(packet), detector_scored=False))
            continue
        del controls, universe
        print(f'{tag}: scoring fresh reporting cohort with unchanged rule configuration', flush=True)
        result = score_rules(tables, config=dict(plan['configuration']), features=features)
        # Explicit snapshot inspection closes series even without a payment at midnight.
        result['evidence_findings'].extend(inspect_sources(tables, AS_OF))
        predictions = predictions_from_result(result, tables, packet, AS_OF)
        cases, events = review_queue(result, tables)
        for name, records in (('rule_scores', result['scores']), ('case_queue', cases), ('case_events', events)):
            write_csv(target/f'{name}.csv', records)
        for name, records in (('rule_hits', result['hits']), ('batch_events', result['batch_events']),
                              ('evidence_findings', result['evidence_findings'])):
            write_jsonl(target/f'{name}.jsonl', records)
        write_json(target/'rule_config.json', result['config'])
        write_json(target/'rule_coverage.json', result['coverage'])
        write_json(target/'predictions.json', predictions)
        frozen_names = ('review_packet.csv', 'rule_scores.csv', 'rule_hits.jsonl', 'case_queue.csv',
            'case_events.csv', 'batch_events.jsonl', 'evidence_findings.jsonl', 'predictions.json',
            'rule_config.json', 'rule_coverage.json')
        frozen = {name: sha(target/name) for name in frozen_names}
        write_json(target/'predictions_frozen.json', dict(sha256=frozen, financial_fraud_labels_loaded=False,
            oracle_joined=False, plan_sha256=sha(output/'evaluation_plan.json'),
            source_commitment_sha256=sha(target/'source_commitment.json')))
        # Only now join the generator's independently declared control oracle.
        controls = read(target/'sealed_truth/oracle.json')
        prediction_by_key = {key(row): row for row in predictions}
        comparisons = [dict(row, actual=prediction_by_key[key(row)]['prediction'],
            detector_status=prediction_by_key[key(row)]['detector_status'],
            evidence_ids=prediction_by_key[key(row)]['evidence_ids']) for row in controls]
        write_json(target/'control_comparison.json', comparisons)
        rule_metrics = {rule: metrics([row for row in comparisons if row['rule_id'] == rule]) for rule in RULES}
        mismatch = [row for row in comparisons if row['actual'] is not row['expected']]
        write_json(target/'mismatches.json', mismatch)
        groups = defaultdict(list)
        for row in comparisons:
            groups[(row['rule_id'], row['company_id'], row['scenario'])].append(row)
        write_json(target/'control_metrics.json', dict(overall=metrics(comparisons), by_rule=rule_metrics,
            by_company_scenario=[dict(rule_id=k[0], company_id=k[1], scenario=k[2], **metrics(rows)) for k, rows in sorted(groups.items())],
            background_labelled=False, financial_fraud_precision=None, reviewer_precision=None))
        workloads = []
        for calendar_name, calendar in (('all_calendar_days', ReviewCalendar()), ('monday_friday_no_holidays', ReviewCalendar((0, 1, 2, 3, 4)))):
            for name, kind, capacity in workload_scenarios():
                workload = budget_review(cases, events, {r['transaction_id']: r for r in tables['transactions']},
                    None, capacity.slots, capacity_minutes=capacity.minutes, calendar=calendar, period_end='2025-12-31')
                workloads.append(dict(scenario=name, kind=kind, calendar_name=calendar_name, **workload))
        write_json(target/'workload.json', workloads)
        store = ReviewStore(data_root, output, output/f'review_{tag}.sqlite3', scenarios=[tag])
        store.prepare()
        store.prepare()
        if tag == '001':
            write_json(target/'migration_rehearsal.json', migration_rehearsal(data_root, output, target, tag, cases))
        inventory = read(target/'source_inventory.json')
        summary = dict(tag=tag, seed=manifest['seed'], role=manifest['role'],
            transactions=len(tables['transactions']), packet_units=len(packet), detector_scored=True,
            controlled_units=len(controls), mismatches=len(mismatch), by_rule=rule_metrics,
            cases=len(cases), source_cases=sum(case['case_type'] == 'source' for case in cases),
            synthetic_schema_inventory_ready={rule: inventory_ready(inventory, rule) for rule in RULES},
            synthetic_exercise_status='passed' if not mismatch else 'mismatches_require_review',
            real_source_status='awaiting_real_data', human_reviewed_units=0,
            criteria_status='frozen_for_synthetic_exercise_only', model_refitted=False)
        write_json(target/'summary.json', summary)
        if not _looks_synthetic(manifest) or any(sha(target/name) != expected for name, expected in frozen.items()):
            raise AssertionError('Frozen predictions changed or synthetic provenance lost')
        summaries.append(summary)
        print(f'{tag}: {len(cases)} cases, {len(controls)} controlled units, {len(mismatch)} mismatches (all visible)', flush=True)
        del result, features, tables, cases, events, workloads
        gc.collect()
    for name, expected in protected.items():
        if sha(ROOT/name) != expected:
            raise AssertionError(f'Protected baseline changed: {name}')
    if any(sha(ROOT/name) != expected for name, expected in source_code.items()):
        raise AssertionError('Implementation changed during the frozen experiment')
    summary = dict(status='synthetic_rehearsal_complete', cohorts=summaries,
        real_source_status='awaiting_real_data', real_reviewed_units=0, real_criteria_status='not_frozen',
        synthetic_criteria_status='frozen_for_synthetic_exercise_only',
        protected_sha256=protected, model_refitted=False, production_history_migrated=False,
        holdout_scored=False, default_rule_or_queue_policy_changed=False)
    write_json(output/'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=ROOT/'data/synthetic_sources_20261017')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/synthetic_sources_20261017')
    parser.add_argument('--companies', type=int, default=8)
    parser.add_argument('--background-rows', type=int, default=12000)
    args = parser.parse_args()
    result = run(args.data_root, args.output, companies=args.companies, background_rows=args.background_rows)
    print(json.dumps(dict(status=result['status'], holdout_scored=result['holdout_scored'],
        real_source_status=result['real_source_status']), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
