"""Measure causal A5 coverage on reporting 001/003 and audit a matched baseline.

No oracle/labels, threshold tuning, feedback migration or notification transport.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gc
import json
from pathlib import Path
import shutil
import time

from .a5_coverage import write_coverage, coverage
from .case_queue import review_queue, operational_members
from .features import build_features, FEATURE_DESCRIPTIONS
from .feature_contract import sha
from .generate import write_csv
from .rules import load_inputs, score_rules
from .source_snapshot import inspect_sources
from .run_pipeline_rehearsal import (TAGS, CUTOFF, read_csv, read_json, write_json, jsonl,
                                     verify_manifest, verified_table)
from .run_p2_controls import PROTECTED, PROJECT


EXTRA_PROTECTED = tuple(PROJECT/name for name in (
    'data/p2_controls_20261018_v2', 'reports/p2_controls_20261018',
    'reports/p2_controls_20261018_baseline'))
SNAPSHOT_FILES = ('case_queue.csv', 'case_events.csv', 'rule_hits.jsonl', 'rule_scores.csv',
                  'rule_config.json', 'rule_coverage.json', 'batch_events.jsonl', 'evidence_findings.jsonl')


def fingerprints():
    return {str(p.relative_to(PROJECT)): sha(p) for root in (*PROTECTED, *EXTRA_PROTECTED)
            if root.exists() for p in sorted(root.rglob('*'))
            if p.is_file() and not p.name.endswith(('-wal', '-shm', '.lock'))}


def guard(output):
    output = Path(output).resolve()
    for source in (*PROTECTED, *EXTRA_PROTECTED):
        if output == source or output in source.parents or source in output.parents:
            raise ValueError('A5 output must be separate from all frozen source/report roots')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError('Use a fresh A5 output directory')
    return output


def read_hits(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def case_signature(row):
    return (row['company_id'], row['case_type'], row.get('source_scope', ''),
            tuple(sorted(json.loads(row['transaction_ids']))))


def compare(current, old, cases, old_cases, target, historic):
    current_a5 = {h['transaction_id']: h for h in current['hits'] if h['rule_id'] == 'A5'}
    old_a5 = {h['transaction_id']: h for h in old['hits'] if h['rule_id'] == 'A5'}
    added, removed = set(current_a5)-set(old_a5), set(old_a5)-set(current_a5)
    members = {tid: row for row in cases for tid in json.loads(row['transaction_ids'])}
    old_members = {tid: row for row in old_cases for tid in json.loads(row['transaction_ids'])}
    diagnostics = {row['transaction_id']: row for row in current['a5_evaluations']}
    other = {}
    for hit in current['hits']:
        if hit['rule_id'] != 'A5' and hit['points'] > 0:
            other.setdefault(hit['transaction_id'], []).append(hit['rule_id'])
    packet = []
    for tid, hit in sorted(current_a5.items()):
        selected = diagnostics[tid]['selected']
        case, old_case = members.get(tid, {}), old_members.get(tid, {})
        packet.append(dict(transaction_id=tid, company_id=hit['company_id'], detected_at=hit['detected_at'],
            a5_change='added' if tid in added else 'retained', points=hit['points'],
            suppressed_reason=hit['suppressed_reason'], other_scored_rules='|'.join(sorted(other.get(tid, []))),
            account_code=selected['account_code'], measurement=selected['measurement'], family=selected['family'],
            comparison_amount_vnd=selected['comparison_amount_vnd'], threshold_vnd=selected['threshold_vnd'],
            sample_count=selected['sample_count'], minimum_samples=selected['minimum_samples'],
            window_days=selected['window_days'], phase=selected['phase'], phase_anchor=selected['phase_anchor'],
            history_sha256=selected['history_sha256'], parameter_id=selected['parameter_id'],
            case_id=case.get('case_id', ''), case_type=case.get('case_type', ''), priority=case.get('priority', ''),
            old_case_id=old_case.get('case_id', ''), old_priority=old_case.get('priority', '')))
    write_csv(target/'a5_hit_review.csv', packet)
    impacted = []
    for case in cases:
        ids = set(json.loads(case['transaction_ids']))
        if ids & added:
            impacted.append(dict(case, added_a5_transaction_ids='|'.join(sorted(ids & added)),
                scored_added_a5_hits=sum(current_a5[tid]['points'] > 0 for tid in ids & added),
                old_member_case_ids='|'.join(sorted({old_members[tid]['case_id'] for tid in ids if tid in old_members}))))
    write_csv(target/'a5_added_hit_cases.csv', impacted, list(impacted[0]) if impacted else ['case_id'])
    signatures = {case_signature(row): row for row in cases}
    old_signatures = {case_signature(row): row for row in old_cases}
    priority_changes = [dict(case_id=signatures[key]['case_id'], before=old_signatures[key]['priority'],
        after=signatures[key]['priority'], before_score=old_signatures[key]['max_score'],
        after_score=signatures[key]['max_score']) for key in signatures.keys() & old_signatures.keys()
        if signatures[key]['priority'] != old_signatures[key]['priority']]
    current_members, prior_members = operational_members(current), operational_members(old)
    summary = dict(comparison='rolling_account vs log_mad; only amount_baseline differs; identical current P2 policy',
        historical_snapshot_a5_hits=Counter(h['rule_id'] for h in historic)['A5'],
        rolling_a5_hits=len(current_a5), matched_log_mad_a5_hits=len(old_a5),
        added_a5_hits=len(added), removed_a5_hits=len(removed),
        added_scored_hits=sum(current_a5[tid]['points'] > 0 for tid in added),
        added_zero_point_hits=sum(current_a5[tid]['points'] == 0 for tid in added),
        added_suppressed_hits=sum(bool(current_a5[tid]['suppressed_reason']) for tid in added),
        cases_containing_added_a5_hits=len(impacted),
        operational_cases_containing_added_a5_hits=sum(row['case_type'] != 'information_request' for row in impacted),
        before_cases=len(old_cases), after_cases=len(cases),
        added_case_scopes=len(signatures.keys()-old_signatures.keys()),
        removed_case_scopes=len(old_signatures.keys()-signatures.keys()),
        added_operational_transaction_ids=sorted(current_members-prior_members),
        removed_operational_transaction_ids=sorted(prior_members-current_members),
        priority_changes=sorted(priority_changes, key=lambda row: row['case_id']),
        removed_a5_transaction_ids=sorted(removed),
        conclusion='Counts describe detector behavior, not false positives or fraud precision. Human document review remains required.')
    write_json(target/'a5_baseline_comparison.json', summary)
    return summary


def cohort(tag, output):
    source = PROJECT/'data/synthetic_sources_20261017_v2'/f'sme_fraud_{tag}'
    frozen = PROJECT/'reports/cash_review_20261018_v2'/f'sme_fraud_{tag}'
    target = output/f'sme_fraud_{tag}'
    target.mkdir()
    manifest = verify_manifest(source)
    if manifest.get('role') != 'reporting' or tag not in TAGS:
        raise ValueError('Only reporting 001/003 are permitted')
    tables, cached, _ = load_inputs(source)
    for name in ('account_flow_edges', 'document_links', 'invoices'):
        tables[name] = verified_table(source, manifest, name)
    print(f'{tag}: building causal features and measuring all transactions', flush=True)
    features = build_features(tables)
    import numpy as np
    actual = np.asarray([[r[k] for k in FEATURE_DESCRIPTIONS] for r in features], dtype=np.float32)
    expected = np.asarray([[r[k] for k in FEATURE_DESCRIPTIONS] for r in cached], dtype=np.float32)
    if ([r['transaction_id'] for r in features] != [r['transaction_id'] for r in cached]
            or not np.isfinite(actual).all() or not np.array_equal(actual, expected)):
        raise AssertionError('Causal features differ from frozen source cache')
    del actual, expected
    config = read_json(frozen/'rule_config.json')
    result = score_rules(tables, config=config, features=features)
    result['evidence_findings'].extend(inspect_sources(tables, CUTOFF))
    cases, events = review_queue(result, tables)
    # Assert that observability has not changed a single hit, score or case.
    actual_hits = json.loads(json.dumps(result['hits'], ensure_ascii=False, allow_nan=False))
    frozen_hits = read_hits(frozen/'rule_hits.jsonl')
    if actual_hits != frozen_hits:
        jsonl(target/'actual_rule_hits.jsonl', actual_hits)
        write_json(target/'hit_mismatch.json', dict(actual_count=len(actual_hits), frozen_count=len(frozen_hits),
            first_differences=[dict(index=i, actual=a, frozen=b) for i,(a,b) in enumerate(zip(actual_hits,frozen_hits)) if a != b][:3]))
        raise AssertionError('Rule hits changed from the frozen current snapshot')
    def comparable(rows):
        return [{k: '' if v is None else str(v) for k, v in row.items() if k != 'known_risky_prior_ids'} for row in rows]
    if comparable(result['scores']) != read_csv(frozen/'rule_scores.csv'):
        raise AssertionError('Transaction scores changed')
    if comparable(cases) != read_csv(frozen/'case_queue.csv'):
        raise AssertionError('Queue changed')
    for name in SNAPSHOT_FILES:
        shutil.copyfile(frozen/name, target/name)
    write_coverage(target, result)
    # Transaction-facing snapshot intentionally starts with no review decisions.
    write_json(target/'snapshot_origin.json', dict(origin=str(frozen), detector_artifacts_unchanged=True,
        feedback_migrated=False, notifications_run=False))
    print(f'{tag}: matched log-MAD control, no threshold tuning', flush=True)
    old = score_rules(tables, config={**config, 'amount_baseline': 'log_mad'}, features=features)
    old['evidence_findings'].extend(inspect_sources(tables, CUTOFF))
    old_cases, _ = review_queue(old, tables)
    counterfactual = target/'matched_log_mad'
    counterfactual.mkdir()
    jsonl(counterfactual/'rule_hits.jsonl', old['hits'])
    write_csv(counterfactual/'case_queue.csv', old_cases)
    write_csv(counterfactual/'rule_scores.csv', [{k:v for k,v in row.items() if k != 'known_risky_prior_ids'} for row in old['scores']])
    write_json(counterfactual/'rule_config.json', old['config'])
    frozen_files = {str(p.relative_to(target)): sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
    write_json(target/'measurement_frozen.json', dict(files=frozen_files, no_truth_joined=True))
    historic = read_hits(PROJECT/'reports/synthetic_sources_20261017_v2'/f'sme_fraud_{tag}'/'rule_hits.jsonl')
    comparison = compare(result, old, cases, old_cases, target, historic)
    summary = dict(tag=tag, **coverage(result['a5_evaluations'])['totals'], comparison=comparison,
                   detector_artifacts_unchanged=True)
    write_json(target/'measurement_summary.json', summary)
    del tables, features, cached, result, old, cases, old_cases
    gc.collect()
    print(f'{tag}: coverage and case comparison exported', flush=True)
    return summary


def run(output):
    output = guard(output)
    before = fingerprints()
    output.mkdir(parents=True, exist_ok=True)
    code = {str(p.relative_to(PROJECT)): sha(p) for folder in ('sme_fraud', 'review_ui')
            for p in sorted((PROJECT/folder).rglob('*')) if p.suffix in {'.py', '.js', '.html', '.css'}}
    write_json(output/'evaluation_plan.json', dict(tags=TAGS, threshold_tuning=False,
        same_current_config_except_control_amount_baseline=True, holdout_005='opaque hashing only',
        truth_loaded=False, protected_files=before, code=code))
    start = time.perf_counter()
    summaries = [cohort(tag, output) for tag in TAGS]
    if fingerprints() != before or any(sha(PROJECT/path) != value for path, value in code.items()):
        raise AssertionError('Protected inputs or implementation changed during measurement')
    summary = dict(status='passed', cohorts=summaries, protected_files=len(before),
        protected_inputs_unchanged=True, threshold_tuning=False, holdout_005_scored=False,
        truth_loaded=False, external_messages_sent=0, elapsed_seconds=round(time.perf_counter()-start, 3))
    write_json(output/'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
