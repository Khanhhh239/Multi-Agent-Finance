"""Explain frozen baseline waiting/SLA debt; counterfactuals never change policy.

All clocks are daily retrospective simulation clocks, not human completion times.
Initial backlog, conditional rereview eligibility and superseded scopes stay explicit.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date, timedelta
import gzip
import json
import math
from pathlib import Path
import time

from .compare_shadow import (PRIORITIES, baseline_key, build_snapshots, load_baseline,
    pending, prepare_case, read_csv, read_json, write_csv, write_json, instant)
from .feature_contract import sha, digest
from .generate import TZ
from .review_capacity import ReviewCapacity
from .integrated_rehearsal import no_truth_access, fresh_output

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'baseline-sla-audit-20261028-v1'
CASE_FIELDS = ('case_id','company_id','case_type','priority','max_score','opened_at','last_seen_at',
    'sla_due_at','rereview_due_at','requires_rereview','estimated_minutes','production_scope_hash',
    'work_scope','base_work_key','rule_ids','source_status','source_scope','member_count')
FOUNDATION = ('compare_shadow.py','case_queue.py','case_identity.py','case_admission.py',
              'temporal_evidence.py','a4_pattern_queue.py')


def scenarios():
    def arm(name, slots=5, minutes=120, **extra):
        return dict(name=name, slots=slots, minutes=minutes, order='baseline',
                    opening_precleared=False, pin_mode='none', weekdays=False, unbounded=False) | extra
    return [arm('baseline_5_120'), arm('slots_10_120',10), arm('minutes_5_240',minutes=240),
        arm('capacity_10_240',10,240), arm('opening_precleared_5_120',opening_precleared=True),
        arm('opening_precleared_10_240',10,240,opening_precleared=True),
        arm('fifo_priority_mandatory_pinned',order='fifo',pin_mode='original'),
        arm('edf_priority_mandatory_pinned',order='edf',pin_mode='original'),
        arm('edf_priority_hard_only_diagnostic',order='edf',pin_mode='hard_only'),
        arm('unbounded_diagnostic',unbounded=True), arm('weekdays_5_120_diagnostic',weekdays=True)]


def pack(case):
    return {name:case.get(name,'') for name in CASE_FIELDS}


def deadline_status(value, day):
    if not value:
        return 'missing'
    due = instant(value)
    start = instant(day.isoformat()+'T00:00:00+07:00')
    end = start+timedelta(days=1)
    return ('definitely_late' if start > due else 'definitely_on_time' if end <= due
            else 'same_day_uncertain')


def task_deadline(task):
    case = task['case']
    return case.get('rereview_due_at','') if task['work_type']=='scheduled_rereview' else case.get('sla_due_at','')


def selected_order(task, order, first_pending):
    case = task['case']
    if order == 'baseline':
        return baseline_key(case)
    ready = first_pending[task['key']]
    tail = (ready, -int(case['max_score']), instant(case['opened_at']), case['case_id'])
    if order == 'fifo':
        return (-PRIORITIES[case['priority']], *tail)
    if order == 'edf':
        # Case SLA is the existing policy field. Do not reset an overdue deadline.
        due = case.get('sla_due_at')
        return (-PRIORITIES[case['priority']], instant(due) if due else instant('9998-01-01T00:00:00+07:00'), *tail)
    raise ValueError('Unknown diagnostic order')


def choose(tasks, capacity, order, first_pending, pins=()):
    chosen, used, cases, keys = [], 0, set(), set()
    def add(task):
        nonlocal used
        if task['case']['case_id'] in cases or not capacity.fits(len(chosen),used,task['minutes']):
            return False
        chosen.append(task); used += task['minutes']; cases.add(task['case']['case_id']); keys.add(task['key'])
        return True
    for task in sorted(pins,key=lambda t:baseline_key(t['case'])):
        if not add(task):
            raise ValueError('Current-day mandatory reservations do not fit')
    for task in sorted(tasks,key=lambda t:selected_order(t,order,first_pending)):
        if task['key'] not in keys:
            add(task)
    return chosen


def blocking_reason(task, chosen, capacity, working=True):
    if not working:
        return 'non_working_day'
    if task['minutes'] > capacity.minutes:
        return 'oversize_task'
    if any(t['case']['case_id']==task['case']['case_id'] for t in chosen):
        return 'same_case_daily_limit'
    slots = len(chosen) >= capacity.slots
    minutes = sum(t['minutes'] for t in chosen)+task['minutes'] > capacity.minutes
    return 'both_limits' if slots and minutes else 'slots_only' if slots else 'minutes_only' if minutes else 'unexplained'


def make_frames(study, tag, destination):
    dataset = study/'source'/('sme_fraud_'+tag)
    baseline = study/'baseline'/dataset.name
    metadata = read_json(dataset/'manifest.json')
    if metadata.get('is_synthetic') is not True or metadata.get('role') != 'reporting':
        raise ValueError('This audit is restricted to the frozen synthetic reporting study')
    for name in ('transactions.csv','employees.csv'):
        if sha(dataset/name)!=metadata['files'][name]['sha256']:
            raise ValueError('Source changed since its attested manifest: '+name)
    scope = read_json(study/'evaluation_plan.json')['evaluation_scope']
    config, indexed, inputs, reconstruction = load_baseline(dataset,baseline)
    start = instant(scope['start_at'])
    transactions = {r['transaction_id']:r for r in read_csv(dataset/'transactions.csv')}
    result = dict(config=config, **{name:data[:bisect_left(times,start)] for name,(data,times) in indexed.items()})
    from .case_queue import review_queue
    opening, _ = review_queue(result,dict(employees=read_csv(dataset/'employees.csv')))
    latest = {(r['company_id'],r['rule_id'],r['scope']):r for r in result['evidence_findings']
              if r.get('scope') and r['rule_id'] in {'F3','F4'}}
    opening = [pack(prepare_case(c,{},transactions,start,latest)) for c in opening if c['company_id'] in scope['company_ids']]
    # An empty IF map is intentional. Baseline ordering does not consume IF scores.
    snapshots, _, rebuilt = build_snapshots(dataset,baseline,scope,{})
    if rebuilt != reconstruction:
        raise ValueError('Opening and daily snapshot reconstruction differ')
    frames = [dict(day=s['day'],cutoff=s['cutoff'],companies=s['companies'],cases=[pack(c) for c in s['cases']]) for s in snapshots]
    destination.mkdir(parents=True)
    write_json(destination/'opening.json',opening)
    with gzip.open(destination/'frames.jsonl.gz','wt',encoding='utf-8') as stream:
        for frame in frames:
            stream.write(json.dumps(dict(frame,day=frame['day'].isoformat()),ensure_ascii=False)+'\n')
    inputs.update({str(dataset/name):sha(dataset/name) for name in ('manifest.json','transactions.csv','employees.csv')})
    write_json(destination/'manifest.json',dict(version=VERSION,study=str(study),cohort=tag,scope=scope,
        frames=len(frames),opening_cases=len(opening),input_sha256=inputs,
        foundation_sha256={name:sha(ROOT/'sme_fraud'/name) for name in FOUNDATION},
        files={name:sha(destination/name) for name in ('opening.json','frames.jsonl.gz')},
        reconstruction=reconstruction,if_scores_loaded=False,models_loaded=False))
    return frames,opening


def load_frames(directory, study, tag):
    meta = read_json(directory/'manifest.json')
    if Path(meta['study']).resolve()!=study or meta['cohort']!=tag:
        raise ValueError('Cached frames belong to another study/cohort')
    if any(sha(directory/name)!=value for name,value in meta['files'].items()):
        raise ValueError('Cached frame content changed')
    if any(sha(Path(path))!=value for path,value in meta['input_sha256'].items()):
        raise ValueError('Frozen frame inputs changed')
    if any(sha(ROOT/'sme_fraud'/name)!=value for name,value in meta['foundation_sha256'].items()):
        raise ValueError('Case reconstruction implementation changed')
    with gzip.open(directory/'frames.jsonl.gz','rt',encoding='utf-8') as stream:
        frames = [dict(row,day=date.fromisoformat(row['day'])) for row in (json.loads(line) for line in stream)]
    return frames,read_json(directory/'opening.json')


def simulate(frames, opening, settings, reference=()):
    if not frames:
        raise ValueError('Need at least one daily snapshot')
    ledger = dict(done=set(),case_ids=set())
    initial = {c['base_work_key']:c for c in opening}
    initial_cases = {c['case_id'] for c in opening}
    start_day, last_day = frames[0]['day'], frames[-1]['day']
    window_start = instant(start_day.isoformat()+'T00:00:00+07:00')
    if settings['opening_precleared']:
        for key,case in initial.items():
            ledger['done'].add(key); ledger['case_ids'].add(case['case_id'])
            due = case.get('rereview_due_at')
            if due and instant(due) <= window_start:
                ledger['done'].add(key+':scheduled_rereview')
    reference_by_day = defaultdict(list)
    for row in reference:
        reference_by_day[(row['day'],row['company_id'])].append(row)
    first_seen, first_pending, tracked = {}, {}, {}
    selected, daily, blocked, previous = [], [], [], {}
    counts = Counter()
    for frame in frames:
        day = frame['day']
        for case in frame['cases']:
            first_seen.setdefault(case['base_work_key'],day)
        tasks = pending(frame['cases'],ledger,first_seen,day)
        current_keys = {t['key'] for t in tasks}
        case_ids = {c['case_id'] for c in frame['cases']}
        for key,old in previous.items():
            if key not in current_keys and key not in ledger['done']:
                status = 'superseded' if old['case']['case_id'] in case_ids else 'withdrawn'
                counts[status+'_unreviewed_scope_events'] += 1
                tracked[key]['disposition'] = status
        for task in tasks:
            key,case = task['key'],task['case']
            first_pending.setdefault(key,day)
            if key not in tracked:
                due = case.get('sla_due_at','')
                tracked[key] = dict(work_key=key,case_id=case['case_id'],company_id=case['company_id'],
                    case_type=case['case_type'],work_type=task['work_type'],first_pending_day=day.isoformat(),
                    recorded_ready_day=task['ready'].isoformat(),work_scope=case['work_scope'],
                    opened_at=case['opened_at'],initial_case_sla_due_at=due,
                    initial_task_deadline=task_deadline(task),source_status=case.get('source_status',''),
                    opening_work=case['base_work_key'] in initial,case_existed_at_start=case['case_id'] in initial_cases,
                    historical_opening_age_days=max(0,(window_start-instant(case['opened_at'])).total_seconds()/86400),
                    first_cost_minutes=task['minutes'],pending_wait_days=0,disposition='pending',reentries=0)
            elif tracked[key]['disposition'] in {'superseded','withdrawn'}:
                tracked[key]['reentries'] += 1
            tracked[key]['disposition'] = 'pending'
        remaining_today = {}
        for company in frame['companies']:
            available = [t for t in tasks if t['case']['company_id']==company]
            working = not settings['weekdays'] or day.weekday() < 5
            capacity = (ReviewCapacity(max(1,len(available)),max(1,sum(t['minutes'] for t in available)))
                        if settings['unbounded'] else ReviewCapacity(settings['slots'],settings['minutes']))
            pins = []
            if settings['pin_mode'] != 'none' and working:
                by_key = {t['key']:t for t in available}
                for row in reference_by_day[(day.isoformat(),company)]:
                    required = row['priority']=='cao_nhat' or (settings['pin_mode']=='original' and row['case_type']!='transaction')
                    if not required or row['work_key'] in ledger['done']:
                        continue
                    if row['work_key'] not in by_key:
                        raise ValueError('A current-day mandatory reference scope is neither pending nor completed')
                    pins.append(by_key[row['work_key']])
            chosen = choose(available,capacity,settings['order'],first_pending,pins) if working else []
            used = sum(t['minutes'] for t in chosen)
            if len(chosen)>capacity.slots or used>capacity.minutes:
                raise AssertionError('Diagnostic capacity exceeded')
            keys = {t['key'] for t in chosen}
            waiting = [t for t in available if t['key'] not in keys]
            day_counts = Counter()
            for task in waiting:
                reason = blocking_reason(task,chosen,capacity,working)
                if reason == 'unexplained':
                    raise AssertionError('An eligible unselected task fits unused capacity')
                day_counts[reason] += 1
                tracked[task['key']]['pending_wait_days'] += 1
                blocked.append(dict(day=day.isoformat(),company_id=company,work_key=task['key'],case_id=task['case']['case_id'],
                    reason=reason,minutes=task['minutes'],selected_cases=len(chosen),selected_minutes=used,
                    remaining_slots=capacity.slots-len(chosen),remaining_minutes=capacity.minutes-used))
                remaining_today[task['key']] = task
            for rank,task in enumerate(chosen,1):
                key,case = task['key'],task['case']
                trace = tracked[key]
                observed = (day-task['ready']).days
                eligible_elapsed = (day-first_pending[key]).days
                offset = (first_pending[key]-task['ready']).days
                gap = eligible_elapsed-trace['pending_wait_days']
                if min(offset,gap)<0 or observed != offset+gap+trace['pending_wait_days']:
                    raise AssertionError('Wait-clock decomposition does not reconcile')
                due = case.get('sla_due_at','')
                record = dict(trace,day=day.isoformat(),rank=rank,priority=case['priority'],baseline_score=case['max_score'],
                    case_scope_hash=case['production_scope_hash'],estimated_minutes=task['minutes'],
                    wait_days=observed,eligibility_elapsed_days=eligible_elapsed,
                    wait_clock_offset_days=offset,off_queue_gap_days=gap,
                    sla_due_at=due,task_deadline=task_deadline(task),
                    case_sla_status=deadline_status(due,day),task_sla_status=deadline_status(task_deadline(task),day),
                    sla_already_due_before_window=bool(due and instant(due)<window_start),
                    sla_already_due_before_eligibility=bool(due and instant(due)<instant(first_pending[key].isoformat()+'T00:00:00+07:00')),
                    initial_deadline_changed=due!=trace['initial_case_sla_due_at'],
                    awaiting_information=case['case_type']=='information_request' or case.get('source_status')=='information_gap',
                    disposition='reviewed')
                selected.append(record)
                trace.update(disposition='reviewed',selected_day=day.isoformat())
                ledger['done'].add(key); ledger['case_ids'].add(case['case_id'])
            daily.append(dict(day=day.isoformat(),company_id=company,working_day=working,
                available_cases=len(available),available_minutes=sum(t['minutes'] for t in available),
                selected_cases=len(chosen),selected_minutes=used,pending_cases=len(waiting),
                pending_minutes=sum(t['minutes'] for t in waiting),
                unused_slots=capacity.slots-len(chosen) if working else 0,
                unused_minutes=capacity.minutes-used if working else 0,
                pinned_scopes=len(pins),**{r:day_counts[r] for r in ('slots_only','minutes_only','both_limits','oversize_task','same_case_daily_limit','non_working_day')}))
        previous = remaining_today
    censored = []
    for key,task in previous.items():
        trace = tracked[key];case = task['case']
        censored.append(dict(trace,priority=case['priority'],estimated_minutes=task['minutes'],
            censored_at=frames[-1]['cutoff'],wait_days_lower=(last_day-task['ready']).days,
            eligibility_wait_days_lower=(last_day-first_pending[key]).days,
            case_sla_status=deadline_status(case.get('sla_due_at',''),last_day),disposition='pending_at_end'))
        trace['disposition'] = 'pending_at_end'
    final_cases = frames[-1]['cases']
    awaiting = [c for c in final_cases if c['base_work_key'] in ledger['done'] and
                (c['case_type']=='information_request' or c.get('source_status')=='information_gap')]
    waiting_cases = {t['case']['case_id'] for t in previous.values()}
    working_days = sum(r['working_day'] for r in daily)
    summary = dict(scenario=settings,selected_work=len(selected),selected_minutes=sum(r['estimated_minutes'] for r in selected),
        selected_by_work_type=dict(Counter(r['work_type'] for r in selected)),
        reported_max_wait_days=max((r['wait_days'] for r in selected),default=0),
        max_eligibility_elapsed_days=max((r['eligibility_elapsed_days'] for r in selected),default=0),
        max_pending_wait_days=max((r['pending_wait_days'] for r in selected),default=0),
        clock_offset_work=sum(r['wait_clock_offset_days']>0 for r in selected),
        clock_offset_days=sum(r['wait_clock_offset_days'] for r in selected),
        pending_wait_days=sum(r['pending_wait_days'] for r in selected),
        off_queue_gap_days=sum(r['off_queue_gap_days'] for r in selected),
        opening_work_selected=sum(r['opening_work'] for r in selected),
        nonopening_selected_max_pending_wait=max((r['pending_wait_days'] for r in selected if not r['opening_work']),default=0),
        pending_at_end=len(censored),pending_minutes_at_end=sum(r['estimated_minutes'] for r in censored),
        pending_max_wait_lower=max((r['eligibility_wait_days_lower'] for r in censored),default=0),
        case_sla_selected=dict(Counter(r['case_sla_status'] for r in selected)),
        task_sla_selected=dict(Counter(r['task_sla_status'] for r in selected)),
        selected_deadline_already_due_before_window=sum(r['sla_already_due_before_window'] for r in selected),
        selected_deadline_already_due_before_eligibility=sum(r['sla_already_due_before_eligibility'] for r in selected),
        newly_definitely_late_selected=sum(r['case_sla_status']=='definitely_late' and not r['sla_already_due_before_eligibility'] for r in selected),
        awaiting_information_reviewed_base_scopes=len(awaiting),
        awaiting_information_without_pending_review=sum(c['case_id'] not in waiting_cases for c in awaiting),
        awaiting_information_with_pending_rereview=sum(c['case_id'] in waiting_cases for c in awaiting),
        dispositions=dict(Counter(r['disposition'] for r in tracked.values())),
        removed_scope_events=dict(counts),blocked_task_days=dict(Counter(r['reason'] for r in blocked)),
        company_days=len(daily),working_company_days=working_days,
        backlog_company_days=sum(r['pending_cases']>0 for r in daily),
        backlog_days_with_unused_slots=sum(r['pending_cases']>0 and r['unused_slots']>0 for r in daily),
        backlog_days_with_unused_minutes=sum(r['pending_cases']>0 and r['unused_minutes']>0 for r in daily),
        case_slot_utilization=None if settings['unbounded'] else len(selected)/(working_days*settings['slots']) if working_days else None,
        minute_utilization=None if settings['unbounded'] else sum(r['estimated_minutes'] for r in selected)/(working_days*settings['minutes']) if working_days else None,
        policy_changed=False,models_fitted=0,actual_review_minutes=None)
    return dict(summary=summary,selected=selected,daily=daily,blocked=blocked,censored=censored,work_scopes=list(tracked.values()))


def compare_reference(result, reference):
    fields = ('day','company_id','work_key','case_id','case_scope_hash','priority','baseline_score',
              'rank','work_type','estimated_minutes','wait_days','case_type','awaiting_information')
    def normalized(row):
        return tuple(str(row[k]) for k in fields)
    if [normalized(r) for r in result['selected']] != [normalized(r) for r in reference]:
        raise AssertionError('Replayed baseline work/ordering/cost/wait differs from the frozen reference')
    return dict(selected_rows=len(reference),exact_reference_fields=list(fields),passed=True)


def comparison(reference, alternative):
    left = {r['work_key']:r for r in reference['selected']}
    right = {r['work_key']:r for r in alternative['selected']}
    common = left.keys() & right.keys()
    diffs = [(date.fromisoformat(right[k]['day'])-date.fromisoformat(left[k]['day'])).days for k in common]
    mandatory = {k for k,r in left.items() if r['priority']=='cao_nhat' or r['case_type']!='transaction'}
    hard = {k for k,r in left.items() if r['priority']=='cao_nhat'}
    def harms(keys):
        return dict(not_selected=len(keys-right.keys()),selected_later=sum(k in right and right[k]['day']>left[k]['day'] for k in keys))
    return dict(common_selected_work=len(common),reference_only_work=len(left.keys()-right.keys()),
        alternative_only_work=len(right.keys()-left.keys()),earlier=sum(d<0 for d in diffs),later=sum(d>0 for d in diffs),
        maximum_additional_days=max([0,*diffs]),mandatory_reference=harms(mandatory),hard_reference=harms(hard),
        caveat='Different capacities/opening history can expose or coalesce different scopes; differences are not additive causal shares')


def write_result(directory, result):
    directory.mkdir(parents=True)
    write_json(directory/'summary.json',result['summary'])
    for name in ('selected','daily','blocked','censored','work_scopes'):
        data = result[name]
        fields = list(dict.fromkeys(k for r in data for k in r)) or ['work_key']
        write_csv(directory/(name+'.csv'),data,fields)


def run(study, output, frames_root=None):
    study = Path(study).resolve()
    output = fresh_output(output,(study,))
    if frames_root:
        frames_root = Path(frames_root).resolve()
        if output.is_relative_to(frames_root) or frames_root.is_relative_to(output):
            raise ValueError('Frame cache and new outputs must be separate')
    output.mkdir(parents=True)
    commitment = read_json(study/'commitment.json')
    consumed = {}
    for tag in ('001','003'):
        name = 'sme_fraud_'+tag
        paths = [study/'source'/name/file for file in ('manifest.json','transactions.csv','employees.csv')]
        paths.append(study/'baseline'/name/'predictions_frozen.json')
        paths += [study/'comparison'/name/f'budget_{slots}'/'selections.private.csv' for slots in (5,10)]
        for path in paths:
            expected = commitment.get(path.relative_to(ROOT).as_posix())
            if expected is None or sha(path)!=expected:
                raise ValueError('Consumed input differs from the sealed integrated study: '+str(path))
            consumed[str(path)] = expected
    plan = dict(version=VERSION,study=str(study),scope=read_json(study/'evaluation_plan.json')['evaluation_scope'],
        scenarios=scenarios(),initial_state='Unresolved pre-window scopes from a strict cutoff before evaluation start',
        wait_clocks='Legacy ready clock, first actual pending eligibility, waiting-cutoff days and off-queue gaps reported separately',
        sla='Case SLA and scheduled-rereview deadline retained; selected day is an interval, never a fabricated completion timestamp',
        pins='Only same-day reference mandatory work gates pinned variants; no future selections used',
        opening_precleared='Hypothetical prior completion of opening scopes and already-due rereviews; changes continued-review effort history',
        workload='Same scope coalescing and effort rules as frozen reference; expose different selected universes and right censoring',
        if_scores_loaded=False,models_loaded=False,models_fitted=0,rules_rescored=False,
        production_policy_changed=False,notifications_sent=0,actual_review_minutes=None,
        code_sha256={name:sha(ROOT/'sme_fraud'/name) for name in (*FOUNDATION,Path(__file__).name)},
        study_commitment_sha256=sha(study/'commitment.json'),input_sha256=consumed,
        cached_frames=str(frames_root) if frames_root else None)
    write_json(output/'evaluation_plan.json',plan)
    outputs = []
    with no_truth_access() as attempted:
        for tag in ('001','003'):
            print(tag+': reconstructing frozen baseline availability, without models/rule scoring',flush=True)
            cache = (frames_root/('sme_fraud_'+tag)/'frames') if frames_root else output/('sme_fraud_'+tag)/'frames'
            frames,opening = load_frames(cache,study,tag) if frames_root else make_frames(study,tag,cache)
            refs = {}
            for slots in (5,10):
                refs[slots] = [r for r in read_csv(study/'comparison'/('sme_fraud_'+tag)/f'budget_{slots}/selections.private.csv') if r['arm']=='baseline']
            target = output/('sme_fraud_'+tag)
            target.mkdir(exist_ok=True)
            measured, exact = {}, []
            for settings in scenarios():
                result = simulate(frames,opening,settings,refs[5])
                if settings['name'] in {'baseline_5_120','capacity_10_240'}:
                    slots = 5 if settings['name']=='baseline_5_120' else 10
                    exact.append(dict(slots=slots,**compare_reference(result,refs[slots])))
                if settings['name']!='baseline_5_120':
                    result['summary']['versus_baseline_5_120'] = comparison(measured['baseline_5_120'],result)
                measured[settings['name']] = result
                write_result(target/settings['name'],result)
                print(tag+' '+settings['name']+': '+str(result['summary']['selected_work'])+' work reviews; max eligible wait '+str(result['summary']['max_pending_wait_days']),flush=True)
            opening_stats=[]
            for company in frames[0]['companies']:
                cases=[c for c in opening if c['company_id']==company]
                minutes=sum(int(c['estimated_minutes']) for c in cases)
                opening_stats.append(dict(company_id=company,scopes=len(cases),minutes=minutes,
                    minimum_5_120_working_days=max(math.ceil(len(cases)/5),math.ceil(minutes/120)),
                    sla_already_before_start=sum(bool(c.get('sla_due_at')) and instant(c['sla_due_at'])<instant(frames[0]['day'].isoformat()+'T00:00:00+07:00') for c in cases)))
            write_json(target/'opening_load.json',opening_stats)
            write_json(target/'reference_reproduction.json',exact)
            item=dict(cohort=tag,opening=opening_stats,reference_reproductions=exact,
                      scenarios={name:r['summary'] for name,r in measured.items()})
            write_json(target/'summary.json',item);outputs.append(item)
    if (attempted or any(sha(ROOT/'sme_fraud'/name)!=value for name,value in plan['code_sha256'].items())
            or any(sha(Path(path))!=value for path,value in consumed.items())):
        raise ValueError('Inputs/code changed or a forbidden data access was attempted')
    summary=dict(version=VERSION,status='diagnostic_audit_complete_policy_unchanged',cohorts=outputs,
        scenarios=len(outputs)*len(scenarios()),frozen_baselines_exactly_reproduced=4,
        models_loaded=0,models_fitted=0,if_scores_loaded=False,rules_rescored=False,production_policy_changed=False,
        source='synthetic retrospective snapshots',independent_reviews=0,actual_review_minutes=None,
        sla_completion_verified=False,limitations=plan['workload'])
    write_json(output/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,default=ROOT/'reports/integrated_rehearsal_20261028_v2')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--frames-root',type=Path)
    args=parser.parse_args()
    result=run(args.study,args.output,args.frames_root)
    print(json.dumps({k:v for k,v in result.items() if k!='cohorts'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
