"""Offline, equal-capacity IF reranking against frozen rules/graph/A5 case snapshots.

This is a synthetic technical study, not a source of human review outcomes.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from datetime import timedelta
import json
from pathlib import Path
import statistics

from .shadow_scoring import guarded, instant, scoring_scope, run_shadow, source_checks, output_guard
from .feature_contract import digest, sha
from .case_queue import review_queue
from .case_identity import scope_hash
from .review_capacity import ReviewCapacity
from .generate import TZ

VERSION = 'equal-capacity-if-shadow-v1'
PRIORITIES = dict(thap=0, trung_binh=1, cao=2, cao_nhat=3)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def write_csv(path, rows, fields):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r.get(k, '') for k in fields} for r in rows)


def baseline_key(case):
    return (-PRIORITIES[case['priority']], -int(case['max_score']), instant(case['opened_at']), case['case_id'])


def case_score(case, scores, transactions, cutoff):
    members = json.loads(case['transaction_ids']) if isinstance(case['transaction_ids'], str) else case['transaction_ids']
    if any(t not in transactions or instant(transactions[t]['posted_at']) >= cutoff for t in members):
        raise ValueError('Case contains unknown or future members at its daily cutoff')
    available = [scores[t] for t in members if t in scores]
    eligible = case['case_type'] == 'transaction' and bool(members)
    full = eligible and len(available) == len(members)
    return dict(if_score=max(available) if full else None, if_coverage='full' if full else
                'missing_or_partial' if eligible else 'outside_transaction_scope', member_count=len(members),
                scored_member_count=len(available))


def shadow_order(tasks):
    """Keep priority bands and missing-score positions; rerank full-coverage slots only."""
    ordered = sorted(tasks, key=lambda r: baseline_key(r['case']))
    for priority in PRIORITIES:
        positions = [i for i, task in enumerate(ordered) if task['case']['priority'] == priority
                     and priority != 'cao_nhat' and task['case']['case_type'] == 'transaction'
                     and task['case']['if_score'] is not None]
        ranked = sorted((ordered[i] for i in positions), key=lambda task:
                        (-task['case']['if_score'], baseline_key(task['case'])))
        for position, task in zip(positions, ranked):
            ordered[position] = task
    return ordered


def select(tasks, capacity, *, pins=(), shadow=False):
    selected, used, case_ids = [], 0, set()
    for task in pins:
        if task['case']['case_id'] in case_ids or not capacity.fits(len(selected), used, task['minutes']):
            raise ValueError('Mandatory baseline selections do not fit the shared capacity')
        selected.append(task); used += task['minutes']; case_ids.add(task['case']['case_id'])
    order = shadow_order(tasks) if shadow else sorted(tasks, key=lambda r: baseline_key(r['case']))
    pinned = {r['key'] for r in pins}
    for task in order:
        if task['key'] in pinned or task['case']['case_id'] in case_ids:
            continue
        if shadow and task['case']['case_type'] != 'transaction':
            continue  # Nontransaction selection stays with the baseline pinned slots.
        if capacity.fits(len(selected), used, task['minutes']):
            selected.append(task); used += task['minutes']; case_ids.add(task['case']['case_id'])
    if shadow:
        positions = {task['key']: i for i, task in enumerate(order)}
        selected.sort(key=lambda task: positions[task['key']])
    return selected


def source_work_scope(case, latest):
    """Source clock updates alone are not new evidence or a new review benefit."""
    evidence = dict(latest.get('evidence', {}))
    evidence.pop('overdue_days', None)
    return digest(dict(company_id=case['company_id'], case_id=case['case_id'],
                       opened_at=case['opened_at'], source_scope=case['source_scope'],
                       source_status=case['source_status'], priority=case['priority'],
                       rule_ids=case['rule_ids'], signal=latest.get('signal'), evidence=evidence))


def prepare_case(case, scores, transactions, cutoff, latest_findings):
    case = dict(case)
    case.update(case_score(case, scores, transactions, cutoff))
    case['production_scope_hash'] = scope_hash(case)
    case['work_scope'] = (source_work_scope(case, latest_findings[(case['company_id'], case['rule_ids'], case['source_scope'])])
                          if case['case_type'] == 'source' else case['production_scope_hash'])
    case['base_work_key'] = digest([case['company_id'], case['case_id'], case['work_scope']])
    return case


def pending(cases, ledger, first_seen, day):
    tasks = []
    for case in cases:
        key = case['base_work_key']
        is_followup = False
        ready = first_seen[key]
        if key in ledger['done']:
            due = case.get('rereview_due_at', '')
            if not int(case.get('requires_rereview', 0)) or not due or instant(due).astimezone(TZ).date() > day:
                continue
            key += ':scheduled_rereview'
            if key in ledger['done']:
                continue
            is_followup = True
            ready = max(ready, instant(due).astimezone(TZ).date())
        prior = case['case_id'] in ledger['case_ids']
        estimate = int(case['estimated_minutes'])
        minutes = max(10, (estimate+1)//2) if prior or is_followup else estimate
        tasks.append(dict(key=key, case=case, ready=ready, minutes=minutes,
                          work_type='scheduled_rereview' if is_followup else 'continued_review' if prior else 'initial_review'))
    return tasks


def simulation(snapshots, slots):
    capacity = ReviewCapacity.ui(slots)
    ledgers = {arm: dict(done=set(), case_ids=set()) for arm in ('baseline', 'if_shadow')}
    first_seen, selections, days, packets = {}, [], [], {}
    totals = {arm: Counter() for arm in ledgers}
    compared, changed, position_changed, mandatory_count = 0, 0, 0, 0
    coverage, scope_sizes = Counter(), []
    previous_pending = {arm: {} for arm in ledgers}
    for snapshot in snapshots:
        day, cutoff, cases = snapshot['day'], snapshot['cutoff'], snapshot['cases']
        for case in cases:
            first_seen.setdefault(case['base_work_key'], day)
            coverage[case['if_coverage']] += 1
            if case['case_type'] == 'transaction':
                scope_sizes.append(case['member_count'])
        tasks = {arm: pending(cases, ledger, first_seen, day) for arm, ledger in ledgers.items()}
        remaining_today = {arm: {} for arm in ledgers}
        case_ids_today = {c['case_id'] for c in cases}
        for arm in ledgers:
            current = {t['key'] for t in tasks[arm]}
            removed = [t for k, t in previous_pending[arm].items() if k not in current]
            totals[arm]['superseded_unreviewed_scopes'] += sum(t['case']['case_id'] in case_ids_today for t in removed)
            totals[arm]['withdrawn_unreviewed_scopes'] += sum(t['case']['case_id'] not in case_ids_today for t in removed)
        for company in snapshot['companies']:
            company_tasks = {arm: [t for t in rows if t['case']['company_id'] == company] for arm, rows in tasks.items()}
            baseline = select(company_tasks['baseline'], capacity)
            candidate_by_key = {t['key']: t for t in company_tasks['if_shadow']}
            mandatory = [t for t in baseline if t['case']['priority'] == 'cao_nhat' or t['case']['case_type'] != 'transaction']
            pins = [candidate_by_key[t['key']] for t in mandatory if t['key'] in candidate_by_key]
            candidate = select(company_tasks['if_shadow'], capacity, pins=pins, shadow=True)
            selected = dict(baseline=baseline, if_shadow=candidate)
            bkeys, ckeys = ({t['key'] for t in selected[arm]} for arm in ('baseline', 'if_shadow'))
            if not {t['key'] for t in pins} <= ckeys:
                raise AssertionError('A mandatory selected baseline scope was displaced')
            compared += bool(bkeys or ckeys)
            changed += bkeys != ckeys
            position_changed += [t['key'] for t in baseline] != [t['key'] for t in candidate]
            mandatory_count += len(pins)
            daily = dict(day=day.isoformat(), company_id=company, capacity_slots=capacity.slots,
                         capacity_minutes=capacity.minutes, same_day_selected_overlap=len(bkeys & ckeys),
                         baseline_only=len(bkeys-ckeys), candidate_only=len(ckeys-bkeys),
                         mandatory_pins=len(pins), mandatory_preserved=True)
            for arm, chosen in selected.items():
                remaining = [t for t in company_tasks[arm] if t['key'] not in {s['key'] for s in chosen}]
                remaining_today[arm].update({t['key']: t for t in remaining})
                used = sum(t['minutes'] for t in chosen)
                if len(chosen) > capacity.slots or used > capacity.minutes:
                    raise AssertionError('Case or minute budget exceeded')
                daily.update({arm+'_selected': len(chosen), arm+'_minutes': used,
                              arm+'_backlog': len(remaining), arm+'_backlog_minutes': sum(t['minutes'] for t in remaining)})
                totals[arm].update(selected=len(chosen), estimated_minutes=used,
                                   backlog_case_days=len(remaining), mandatory_overflow=sum(
                                       t['case']['priority'] == 'cao_nhat' for t in remaining))
                totals[arm]['peak_backlog_per_company'] = max(totals[arm]['peak_backlog_per_company'], len(remaining))
                for rank, task in enumerate(chosen, 1):
                    case = task['case']
                    if task['key'] in ledgers[arm]['done']:
                        raise AssertionError('An unchanged completed work scope was counted again')
                    wait = (day-task['ready']).days
                    record = dict(day=day.isoformat(), cutoff_exclusive=cutoff, company_id=company, arm=arm,
                        work_key=task['key'], case_id=case['case_id'], case_scope_hash=case['production_scope_hash'],
                        study_work_scope=case['work_scope'], case_type=case['case_type'], priority=case['priority'],
                        baseline_score=case['max_score'], if_score=case['if_score'], if_coverage=case['if_coverage'],
                        rank=rank, work_type=task['work_type'], estimated_minutes=task['minutes'], wait_days=wait,
                        member_count=case['member_count'], awaiting_information=(case['case_type'] == 'information_request'
                            or case['source_status'] == 'information_gap'))
                    selections.append(record)
                    totals[arm].update(wait_days=wait, awaiting_information=int(record['awaiting_information']))
                    ledgers[arm]['done'].add(task['key']); ledgers[arm]['case_ids'].add(case['case_id'])
                    packets.setdefault(task['key'], dict(case_id=case['case_id'], company_id=company,
                        cutoff_exclusive=cutoff, case_scope_hash=case['production_scope_hash'],
                        transaction_ids=case['transaction_ids'], source_scope=case['source_scope'],
                        rule_ids=case['rule_ids'], case_type=case['case_type']))
            days.append(daily)
        previous_pending = remaining_today
    # End-of-period backlog is summed over all companies on the final day.
    final_day = snapshots[-1]['day'].isoformat() if snapshots else None
    for arm in totals:
        totals[arm]['backlog_at_end'] = sum(d[arm+'_backlog'] for d in days if d['day'] == final_day)
        totals[arm]['backlog_minutes_at_end'] = sum(d[arm+'_backlog_minutes'] for d in days if d['day'] == final_day)
        totals[arm]['unique_cases_selected'] = len(ledgers[arm]['case_ids'])
        totals[arm]['awaiting_information_at_end'] = sum(
            c['base_work_key'] in ledgers[arm]['done'] and (c['case_type'] == 'information_request'
            or c['source_status'] == 'information_gap') for c in (snapshots[-1]['cases'] if snapshots else []))
    matched = {arm: {r['work_key']: r['day'] for r in selections if r['arm'] == arm} for arm in ledgers}
    common = set(matched['baseline']) & set(matched['if_shadow'])
    delays = [(instant(matched['if_shadow'][k]+'T00:00:00+07:00')-instant(matched['baseline'][k]+'T00:00:00+07:00')).days for k in common]
    summary = dict(daily_slots=slots, daily_minutes=capacity.minutes, calendar='all_calendar_days',
        company_days=len(days), active_company_days=compared, company_days_with_changed_selection=changed,
        company_days_with_changed_order=position_changed, mandatory_selected_scopes_pinned=mandatory_count,
        same_day_selection_overlap=sum(d['same_day_selected_overlap'] for d in days),
        baseline_only_selections=sum(d['baseline_only'] for d in days),
        candidate_only_selections=sum(d['candidate_only'] for d in days),
        mandatory_displacements=0, budget_violations=0, coverage_daily_case_snapshots=dict(coverage),
        transaction_scope_sizes=dict(count=len(scope_sizes), median=statistics.median(scope_sizes) if scope_sizes else None,
                                     maximum=max(scope_sizes, default=0)),
        arms={arm: dict(values, mean_wait_days=values['wait_days']/values['selected'] if values['selected'] else None)
              for arm, values in totals.items()},
        common_review_work_scopes=len(common), common_scopes_earlier_by_if=sum(d < 0 for d in delays),
        common_scopes_later_by_if=sum(d > 0 for d in delays),
        max_common_scope_delay_days=max([0, *delays]),
        actionable_gain=None, fraud_precision=None, fraud_recall=None, independent_reviews=0)
    return dict(summary=summary, daily=days, selections=selections, packets=packets)


def load_baseline(dataset, baseline):
    commitment = read_json(baseline/'predictions_frozen.json')
    if commitment['source_manifest_sha256'] != sha(dataset/'manifest.json'):
        raise ValueError('Baseline and IF must use the identical source manifest')
    inputs = {str(baseline/'predictions_frozen.json'): sha(baseline/'predictions_frozen.json')}
    for name, expected in commitment['files'].items():
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Frozen baseline filenames must be plain names')
        path = guarded(baseline/name)
        if sha(path) != expected:
            raise ValueError('Frozen baseline checksum mismatch: '+name)
        inputs[str(path)] = expected
    config = read_json(baseline/'rule_config.json')
    if config.get('enable_graph') is not True or config.get('amount_baseline') != 'rolling_account':
        raise ValueError('Comparison requires the frozen rules + graph + rolling A5 baseline')
    plan_path = baseline.parent/'evaluation_plan.json'
    if commitment['plan_sha256'] != sha(plan_path):
        raise ValueError('Frozen baseline plan checksum mismatch')
    inputs[str(plan_path)] = sha(plan_path)
    code_plan = read_json(plan_path)
    root = Path(__file__).resolve().parents[1]
    code_audit = {}
    for name in ('case_queue.py', 'case_identity.py', 'case_admission.py', 'temporal_evidence.py', 'a4_pattern_queue.py'):
        expected, actual = code_plan['code_sha256'].get('sme_fraud/'+name), sha(root/'sme_fraud'/name)
        code_audit[name] = dict(recorded_sha256=expected, current_sha256=actual, unchanged=expected == actual)
        if expected != actual and name != 'case_queue.py':
            raise ValueError('Case reconstruction code changed since the frozen baseline: '+name)
    scores = read_csv(baseline/'rule_scores.csv')
    for row in scores:
        for field in ('rule_score', 'base_score', 'recurrence_points', 'hard_trigger', 'operational_alert'):
            row[field] = int(row[field])
    collections = dict(scores=(scores, 'posted_at'))
    for name, field in (('hits', 'detected_at'), ('batch_events', 'detected_at'), ('evidence_findings', 'cutoff_at')):
        filename = 'rule_hits.jsonl' if name == 'hits' else name+'.jsonl'
        with (baseline/filename).open(encoding='utf-8') as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        if name == 'hits':
            rows = [r for r in rows if r['rule_id'] == 'P2']
        collections[name] = (rows, field)
    indexed = {}
    for name, (rows, field) in collections.items():
        ordered = sorted(rows, key=lambda r: instant(r[field]))
        indexed[name] = (ordered, [instant(r[field]) for r in ordered])
    # The study pins the current case builder, rather than silently treating a
    # changed file as the old implementation. Its complete output must still
    # reproduce every frozen case scope before any shadow scores are computed.
    complete, _ = review_queue(dict(config=config, **{name: rows for name, (rows, _) in indexed.items()}),
                               dict(employees=read_csv(dataset/'employees.csv')))
    frozen = {r['case_id']: r['scope_hash'] for r in read_csv(baseline/'case_queue.csv')}
    if frozen != {r['case_id']: r['scope_hash'] for r in complete}:
        raise ValueError('Current case reconstruction does not reproduce all frozen baseline scopes')
    reconstruction = dict(policy='current_case_builder_on_frozen_detector_outputs', code=code_audit,
                          frozen_final_cases=len(frozen), frozen_final_scopes_reproduced=True,
                          historical_intermediate_snapshots_available=False)
    return config, indexed, inputs, reconstruction


def build_snapshots(dataset, baseline, scope, scores):
    scope, start, end = scoring_scope(scope)
    if start.astimezone(TZ).time().isoformat() != '00:00:00' or end.astimezone(TZ).time().isoformat() != '00:00:00':
        raise ValueError('Comparison boundaries must be midnight in Vietnam')
    config, indexed, inputs, reconstruction = load_baseline(dataset, baseline)
    transactions = {r['transaction_id']: r for r in read_csv(dataset/'transactions.csv')}
    raw_scores = indexed['scores'][0]
    if (len(raw_scores) != len(transactions) or {r['transaction_id'] for r in raw_scores} != set(transactions)
            or any((r['company_id'], instant(r['posted_at'])) !=
                   (transactions[r['transaction_id']]['company_id'], instant(transactions[r['transaction_id']]['posted_at']))
                   for r in raw_scores)):
        raise ValueError('Frozen baseline transaction coverage or scope differs from source')
    tables = dict(employees=read_csv(dataset/'employees.csv'))
    snapshots, day = [], start.astimezone(TZ).date()
    while day < end.astimezone(TZ).date():
        cutoff = instant((day+timedelta(days=1)).isoformat()+'T00:00:00+07:00')
        result = dict(config=config)
        for name, (rows, times) in indexed.items():
            result[name] = rows[:bisect_left(times, cutoff)]
        cases, _ = review_queue(result, tables)
        latest = {(r['company_id'], r['rule_id'], r['scope']): r for r in result['evidence_findings']
                  if r.get('scope') and r['rule_id'] in {'F3', 'F4'}}
        if cutoff == end and all(not times or times[-1] < cutoff for _, times in indexed.values()):
            frozen = {r['case_id']: r['scope_hash'] for r in read_csv(baseline/'case_queue.csv')}
            if frozen != {r['case_id']: r['scope_hash'] for r in cases}:
                raise ValueError('Final as-of reconstruction differs from the frozen case queue')
        selected = [prepare_case(c, scores, transactions, cutoff, latest) for c in cases
                    if c['company_id'] in scope['company_ids']]
        snapshots.append(dict(day=day, cutoff=cutoff.isoformat(), companies=scope['company_ids'], cases=selected))
        if len(snapshots) % 30 == 0:
            print(f'As-of snapshots: {len(snapshots)} days rebuilt through {day}', flush=True)
        day += timedelta(days=1)
    return snapshots, inputs, reconstruction


def run_comparison(dataset, baseline, model, output, *, model_sha256, scope):
    dataset, baseline, model, output = (guarded(p) for p in (dataset, baseline, model, output))
    if output.exists():
        raise FileExistsError('Use a new output directory for the shadow comparison')
    output_guard(output, dataset, model)
    for parent in (dataset, baseline, model.parent):
        if output.is_relative_to(parent) or parent.is_relative_to(output):
            raise ValueError('Comparison output must be separate from its inputs')
    metadata = read_json(dataset/'manifest.json')
    if metadata.get('role') != 'reporting' or metadata.get('is_synthetic') is not True:
        raise ValueError('This comparison is restricted to synthetic reporting snapshots')
    scope, _, _ = scoring_scope(scope)
    # Freeze technical decisions before any scores/selections are produced.
    _, _, inputs, reconstruction = load_baseline(dataset, baseline)
    plan = dict(version=VERSION, mode='synthetic_technical_shadow_only', scope=scope,
        primary_capacity=dict(cases=5, minutes=120), sensitivity_capacity=dict(cases=10, minutes=240),
        calendar='all_calendar_days_no_holidays_inferred', daily_cutoff='next_Vietnam_midnight_exclusive',
        baseline_order='priority DESC, rule_score DESC, opened_at, case_id',
        candidate_order='IF maximum full-coverage member score within the same priority; missing slots anchored',
        mandatory='Pin baseline-selected cao_nhat and nontransaction work still pending in the candidate arm',
        shared_initial_state='All pre-existing unresolved baseline case scopes enter the starting backlog',
        scope_updates='Coalesce unselected old versions into current scope; selected changed scope requires continued review',
        source_work_identity='Same source evidence/episode stays one work scope; cutoff and derived overdue_days alone do not reopen it',
        information_gaps='Simulated request/review once per work scope; park awaiting information; one existing scheduled rereview if due',
        effort='Current as-of estimate; continued review max(10, ceil(base/2)); estimates are not measured human minutes',
        completion='Study ledger only; no business conclusion or production feedback',
        labels_or_oracle_used=False, models_fitted=0, production_queue_write=False, external_notifications=0,
        real_protocol_approval='not_asserted', actionable_gain_reportable=False,
        model_sha256=model_sha256, source_manifest_sha256=sha(dataset/'manifest.json'),
        baseline_input_sha256=inputs,
        baseline_reconstruction=reconstruction,
        code_sha256={str(Path(__file__).resolve().with_name(name)): sha(Path(__file__).resolve().with_name(name))
                     for name in ('compare_shadow.py', 'case_queue.py', 'case_identity.py', 'case_admission.py',
                                  'temporal_evidence.py', 'a4_pattern_queue.py')})
    output.mkdir(parents=True)
    write_json(output/'evaluation_plan.json', plan)
    write_json(output/'status.json', dict(status='running', plan_sha256=sha(output/'evaluation_plan.json')))
    try:
        shadow = run_shadow(dataset, model, output/'if_scores', model_sha256=model_sha256, scope=scope)
        if not shadow['model_training_window_disjointness_verified']:
            raise ValueError('Comparison requires verified train/calibration/evaluation model windows')
        transactions = {r['transaction_id']: r for r in read_csv(dataset/'transactions.csv')}
        score_rows = read_csv(output/'if_scores/shadow_scores.csv')
        import math
        scores = {}
        for row in score_rows:
            tid = row['transaction_id']
            if tid in scores or tid not in transactions or row['company_id'] != transactions[tid]['company_id'] or instant(row['posted_at']) != instant(transactions[tid]['posted_at']):
                raise ValueError('Shadow score scope/ID differs from source')
            value = float(row['anomaly_score'])
            if not math.isfinite(value):
                raise ValueError('Shadow score must be finite')
            scores[tid] = value
        snapshots, _, _ = build_snapshots(dataset, baseline, scope, scores)
        summaries, union = [], {}
        for slots in (5, 10):
            measured = simulation(snapshots, slots)
            target = output/('budget_'+str(slots)); target.mkdir()
            write_json(target/'summary.json', measured['summary'])
            write_csv(target/'daily_comparison.csv', measured['daily'], list(measured['daily'][0]))
            write_csv(target/'selections.private.csv', measured['selections'], list(measured['selections'][0]) if measured['selections'] else ['day','company_id','arm','work_key'])
            for key, packet in measured['packets'].items():
                if key not in union or instant(packet['cutoff_exclusive']) < instant(union[key]['cutoff_exclusive']):
                    union[key] = packet
            summaries.append(measured['summary'])
        packets = [dict(review_id='RV_'+digest([VERSION, k])[:20], **row,
                        actionable='', review_minutes='', reviewer='', decision='', note='') for k, row in sorted(union.items())]
        write_csv(output/'review_union.blind.csv', packets, list(packets[0]) if packets else ['review_id','actionable','review_minutes','reviewer'])
        if (sha(model) != model_sha256 or sha(dataset/'manifest.json') != plan['source_manifest_sha256']
                or source_checks(dataset, metadata) != shadow['input_sha256']
                or any(sha(p) != h for p, h in {**inputs, **plan['code_sha256']}.items())):
            raise ValueError('Comparison inputs changed after freezing the plan')
        report = dict(version=VERSION, status='technical_comparison_complete_awaiting_independent_review',
            plan_sha256=sha(output/'evaluation_plan.json'), scope=scope, shadow_rows=shadow['rows_scored'],
            shadow_run_id=shadow['run_id'], scores_sha256=shadow['scores_sha256'], summaries=summaries,
            blind_review_units=len(packets), independent_reviews=0, actionable_gain=None,
            models_fitted=0, queue_changed=False, labels_loaded=False, oracle_loaded=False,
            external_notifications=0, holdout_005_loaded_or_scored=False,
            limitations=['Same daily capacity caps; spent minutes are simulated estimates, not measured effort',
                         'Daily cutoff is retrospective; no source ERP ingestion/arrival latency is measured',
                         'Case selections are study work scopes, not independently useful or fraudulent outcomes',
                         'No random reference sample or blinded adjudication has been executed in this technical run',
                         'Evaluation source was previously scored technically; no untouched field performance claim'])
        write_json(output/'comparison.json', report)
        write_json(output/'predictions_frozen.json', {p.relative_to(output).as_posix(): sha(p)
            for p in output.rglob('*') if p.is_file() and p.name != 'status.json'})
        write_json(output/'status.json', dict(status='complete', comparison_sha256=sha(output/'comparison.json')))
        return report
    except Exception as error:
        write_json(output/'status.json', dict(status='failed', error_type=type(error).__name__, error=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--model-sha256', required=True)
    parser.add_argument('--scope', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run_comparison(args.dataset, args.baseline, args.model, args.output,
        model_sha256=args.model_sha256, scope=read_json(guarded(args.scope)))
    print(json.dumps(dict(status=result['status'], shadow_rows=result['shadow_rows'], summaries=result['summaries'])))


if __name__ == '__main__':
    main()
