"""Freeze an opt-in A4 queue trial before joining train/validation labels.

No detector or model is run. Existing scores, hits, batch events and source
snapshots are immutable inputs. Reviewer confirmation remains a separate gate.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import shutil

from .a4_pattern_queue import A4_PATTERN_TRIAL
from .case_identity import values
from .case_queue import review_queue, operational_members
from .evidence_evaluation import budget_review
from .feature_contract import validate_cache
from .generate import write_csv
from .replay_review_workload import ROOT, read, rows, sha, write, PERIOD_ENDS, CALENDARS
from .review_capacity import workload_scenarios
from .review_store import ReviewStore


BASELINE = ROOT/'reports/split_pattern_admission_20261017_v2'
DATA = ROOT/'data/feature_model_sync_20261017'


def jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def signature(records):
    return [{key: str(value) for key, value in row.items()} for row in records]


def run(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new output root for a new A4 trial')
    protected = {}
    for tag in ('001', '003', '005'):
        source = BASELINE/f'sme_fraud_{tag}'
        for name, expected in read(source/'comparison.json')['protected_sha256'].items():
            path = (ROOT/name).resolve()
            if sha(path) != expected:
                raise ValueError(f'Baseline input changed: {path}')
            protected[path] = expected
        for path in [*source.glob('*'), BASELINE/f'review_{tag}.sqlite3']:
            if path.is_file() and path.name != '.feedback.lock':
                protected[path] = sha(path)
        for name, expected in read(source/'predictions_frozen.json')['sha256'].items():
            if sha(source/name) != expected:
                raise ValueError('Frozen baseline differs')
        validate_cache(read(DATA/f'sme_fraud_{tag}'/'manifest.json'))
    production = ROOT/'.runtime/review/review.sqlite3'
    if production.exists():
        protected[production] = sha(production)
    code = {str(path.relative_to(ROOT)): sha(path) for path in (ROOT/'sme_fraud').glob('*.py')}
    code['review_ui/app.js'] = sha(ROOT/'review_ui/app.js')
    plan = dict(policy=A4_PATTERN_TRIAL, default_changed=False, test_scored=False,
        detector_scored=False, model_refitted=False, labels_used_for_policy=False,
        routing='Only weak A4-only rows/batches; strong, hard, A2/mixed and mixed batches retain entity path',
        scope='company + maker + calendar month + frozen A4 predicate configuration',
        required_invariants=['same operational members', 'same observation timestamps',
            'same scores/hits/hard triggers', 'stable order-independent pattern IDs',
            'hard priority available at each hard observation', 'no feedback or assignment transfer across changed scope'],
        effort_assumptions=['existing 20-45 minute initial-review heuristic',
            'sensitivity: retain total baseline minute demand by proportional allocation; no assumed minute savings'],
        acceptance_status='awaiting_independent_review', reviewer_confirmed_units=0,
        calendars={name: calendar.as_dict() for name, calendar in CALENDARS.items()},
        source_sha256=code)
    output.mkdir(parents=True)
    write(output/'evaluation_plan.json', plan)
    summaries = []
    for tag in ('001', '003', '005'):
        source, data, target = BASELINE/f'sme_fraud_{tag}', DATA/f'sme_fraud_{tag}', output/f'sme_fraud_{tag}'
        target.mkdir()
        scores = rows(source/'rule_scores.csv')
        for row in scores:
            for field in ('rule_score', 'base_score', 'recurrence_points', 'operational_alert', 'hard_trigger'):
                row[field] = int(row[field])
        tables = dict(employees=rows(data/'employees.csv'), transactions=rows(data/'transactions.csv'))
        tx = {row['transaction_id']: row for row in tables['transactions']}
        splits = {row['transaction_id']: row['split'] for row in rows(data/'splits.csv')}
        if len(tx) != 75000 or set(splits) != set(tx) or set(splits.values()) != {'train', 'validation'}:
            raise ValueError('Only the frozen train/validation IDs are permitted')
        result = dict(scores=scores, hits=jsonl(source/'rule_hits.jsonl'),
            batch_events=jsonl(source/'batch_events.jsonl'), evidence_findings=jsonl(source/'evidence_findings.jsonl'),
            config=read(source/'rule_config.json'))
        before, old_events = review_queue(result, tables)
        if signature(before) != rows(source/'case_queue.csv') or signature(old_events) != rows(source/'case_events.csv'):
            raise ValueError(f'Default queue no longer replays the frozen snapshot: {tag}')
        after, events = review_queue(result, tables, policy=A4_PATTERN_TRIAL)
        old_owner = {tid: case for case in before for tid in values(case['transaction_ids'])}
        new_owner = {tid: case for case in after for tid in values(case['transaction_ids'])}
        if set(old_owner) != set(new_owner) or set(new_owner) != operational_members(result):
            raise ValueError('A4 trial changed operational coverage')
        if sum(len(values(case['transaction_ids'])) for case in after) != len(new_owner):
            raise ValueError('Duplicate transaction membership')
        changed_hard_scopes = []
        for row in scores:
            if row['hard_trigger'] and row['operational_alert']:
                before_case, after_case = old_owner[row['transaction_id']], new_owner[row['transaction_id']]
                if (after_case['case_type'] == 'pattern' or after_case['priority'] != 'cao_nhat'
                        or after_case['max_score'] < row['rule_score']
                        or not any(event['case_id'] == after_case['case_id'] and event['priority'] == 'cao_nhat'
                                   and event['event_at'] <= row['posted_at'] for event in events)):
                    raise ValueError(f'Hard-trigger priority or availability lost: {tag}/{row["transaction_id"]}')
                if before_case['case_id'] != after_case['case_id'] or before_case['scope_hash'] != after_case['scope_hash']:
                    changed_hard_scopes.append(dict(transaction_id=row['transaction_id'],
                        before_case_id=before_case['case_id'], after_case_id=after_case['case_id'],
                        automatic_feedback_transfer=False))
        # Proportional baseline-minute allocation is a sensitivity calculation,
        # not a new operational estimate. Preserve total demand exactly.
        conservative = {case['case_id']: 0 for case in after}
        for old in before:
            counts = Counter(new_owner[tid]['case_id'] for tid in values(old['transaction_ids']))
            if not counts:  # Source cases have no transaction membership.
                conservative[old['case_id']] += int(old['estimated_minutes'])
                continue
            total, cost = sum(counts.values()), int(old['estimated_minutes'])
            allocation = {key: cost*count//total for key, count in counts.items()}
            for key in sorted(counts, key=lambda key: (-(cost*counts[key] % total), key))[:cost-sum(allocation.values())]:
                allocation[key] += 1
            for key, minutes in allocation.items():
                conservative[key] += minutes
        if sum(conservative.values()) != sum(int(case['estimated_minutes']) for case in before):
            raise ValueError('Conservative demand allocation differs from baseline')
        if any(value <= 0 for value in conservative.values()):
            raise ValueError('Sensitivity allocation produced zero-minute work; inspect scope splitting')
        for name, records in (('case_queue', after), ('case_events', events)):
            write_csv(target/f'{name}.csv', records)
        for name in ('rule_scores.csv', 'rule_hits.jsonl', 'batch_events.jsonl', 'evidence_findings.jsonl', 'rule_config.json', 'rule_coverage.json'):
            shutil.copy2(source/name, target/name)
        write(target/'queue_policy.json', dict(policy=A4_PATTERN_TRIAL, acceptance_status='awaiting_independent_review'))
        links = [dict(previous_case_id=old['case_id'], current_case_ids=sorted(
            {new_owner[tid]['case_id'] for tid in values(old['transaction_ids'])}), automatic_feedback_transfer=False)
            for old in before]
        write(target/'case_identity_comparison.json', links)
        packet = []
        for case in after:
            if case['case_type'] != 'pattern':
                continue
            identifiers = sorted({*values(case['transaction_ids']), *values(case['pattern_context_ids'])})
            packet.append(dict(review_id=case['case_id'], scope=json.loads(case['pattern_scope']),
                opened_at=case['opened_at'], last_seen_at=case['last_seen_at'],
                member_ids=values(case['transaction_ids']), context_ids=values(case['pattern_context_ids']),
                baseline_case_ids=sorted({old_owner[tid]['case_id'] for tid in values(case['transaction_ids'])}),
                linked_case_ids=values(case['linked_case_ids']),
                evidence_ids=values(case['pattern_evidence_ids']), transactions=[tx[tid] for tid in identifiers],
                reviewer_1='', reviewer_2='', scope_acceptable=None, duplicate_review_confirmed=None,
                separate_obligation_review_required=None, measured_baseline_minutes=None,
                measured_trial_minutes=None, notes=''))
        write(target/'review_packet.json', packet)
        store = ReviewStore(DATA, output, output/f'review_{tag}.sqlite3', scenarios=[tag])
        store.prepare()
        store.prepare()
        frozen = {path.name: sha(path) for path in target.glob('*') if path.is_file() and path.name != '.feedback.lock'}
        write(target/'predictions_frozen.json', dict(labels_loaded=False, policy=A4_PATTERN_TRIAL, sha256=frozen))
        print(f'{tag}: trial frozen, cases {len(before)} -> {len(after)}; join labels for diagnostics only', flush=True)
        labels = {row['transaction_id']: row for row in rows(data/'labels.csv')}
        report = dict(tag=tag, baseline_cases=len(before), trial_cases=len(after),
            pattern_cases=sum(case['case_type'] == 'pattern' for case in after),
            reviewer_confirmed_units=0, review_packet_units=len(packet), acceptance_status='awaiting_independent_review',
            operational_members_unchanged=True, default_queue_replayed=True,
            hard_trigger_priority_and_observation_time_preserved=True, changed_hard_scopes=changed_hard_scopes,
            periods={}, workload=[])
        for period, cutoff in PERIOD_ENDS.items():
            ids = {tid for tid in tx if splits[tid] == period}
            selected = set(new_owner) & ids
            report['periods'][period] = dict(rows=len(ids), admitted_rows=len(selected),
                tp=sum(int(labels[tid]['is_fraud']) for tid in selected),
                fp=sum(not int(labels[tid]['is_fraud']) for tid in selected))
            for variant, queue, history in (('baseline', before, old_events), ('trial', after, events),
                    ('trial_without_assumed_minute_savings', [dict(case, estimated_minutes=conservative[case['case_id']]) for case in after], events)):
                subset = [case for case in queue if case['opened_at'].startswith('2024' if period == 'train' else '2025')]
                for calendar_name, calendar in CALENDARS.items():
                    for profile, kind, capacity in workload_scenarios():
                        load = budget_review(subset, history, tx, None, capacity.slots,
                            capacity_minutes=capacity.minutes, calendar=calendar, period_end=cutoff)
                        load.pop('admissions')
                        report['workload'].append(dict(variant=variant, period=period, calendar_name=calendar_name,
                            capacity_profile=profile, profile_kind=kind, **load))
        write(target/'comparison.json', report)
        if any(sha(target/name) != expected for name, expected in frozen.items()):
            raise ValueError('Frozen trial prediction or reviewer packet changed')
        summaries.append(report)
    if any(sha(path) != expected for path, expected in protected.items()):
        raise ValueError('Protected source/model/report/SQLite changed')
    if any(sha(ROOT/name) != expected for name, expected in code.items()):
        raise ValueError('Code changed during trial')
    summary = dict(successful=True, observations=225000, test_scored=False, model_refitted=False,
        detector_scored=False, default_policy_changed=False, independent_review_complete=False,
        reviewer_confirmed_units=0, acceptance_status='awaiting_independent_review',
        source_model_baseline_and_production_sqlite_unchanged=True,
        protected_sha256={str(path.relative_to(ROOT)): expected for path, expected in protected.items()},
        plan=plan, datasets=summaries)
    write(output/'summary.json', summary)
    print('A4 trial complete; technical comparison only, awaiting independent reviewer confirmation.', flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('reports/a4_pattern_trial_20261017_v2'))
    run(parser.parse_args().output)


if __name__ == '__main__':
    main()
