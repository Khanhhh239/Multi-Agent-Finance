"""Assessment units, workload budgets and block uncertainty; no model code."""
from collections import defaultdict
from datetime import timedelta
import json
import random

from .generate import parse
from .rule_audit import confusion


def boolean_metrics(rows):
    known = [r for r in rows if r['expected'] is not None and r['actual'] is not None]
    tp = sum(r['expected'] and r['actual'] for r in known)
    fp = sum(not r['expected'] and r['actual'] for r in known)
    fn = sum(r['expected'] and not r['actual'] for r in known)
    tn = sum(not r['expected'] and not r['actual'] for r in known)
    return dict(unit='declared_condition_not_financial_fraud', rows=len(rows), evaluable=len(known),
        tp=tp, fp=fp, fn=fn, tn=tn, precision=tp/(tp+fp) if tp+fp else None,
        recall=tp/(tp+fn) if tp+fn else None, unknown_expected=sum(r['expected'] is None for r in rows),
        missing_prediction=sum(r['expected'] is not None and r['actual'] is None for r in rows),
        correct_unknown=sum(r['expected'] is None and r['actual'] is None for r in rows))


def block_precision(ids, selected, labels, transactions, seed, repetitions=299):
    """Frozen predictions sampled by company/month, retaining within-block dependence."""
    blocks = defaultdict(lambda: [0,0])
    for tid in ids:
        if tid in selected:
            key = transactions[tid]['company_id'], transactions[tid]['posted_at'][:7]
            blocks[key][int(labels[tid]['is_fraud']) == 0] += 1
        else:
            blocks[(transactions[tid]['company_id'], transactions[tid]['posted_at'][:7])]
    values = list(blocks.values())
    rng, estimates = random.Random(seed), []
    for _ in range(repetitions):
        sample = [rng.choice(values) for _ in values]
        tp, fp = sum(x[0] for x in sample), sum(x[1] for x in sample)
        if tp+fp:
            estimates.append(tp/(tp+fp))
    estimates.sort()
    return dict(unit='company_calendar_month_blocks', blocks=len(values), repetitions=repetitions,
        interval95=[estimates[int(.025*(len(estimates)-1))], estimates[int(.975*(len(estimates)-1))]] if estimates else None,
        note='Descriptive uncertainty on frozen simulations; few companies/seeds remain a limitation.')


def budget_review(cases, events, transactions, labels, budget):
    """Simulate initial/source/re-review work, carrying unfinished tasks forward.

    Capacity is expressed in both case slots and minutes.  Opening rank only uses
    evidence available at that event; labels are read afterward for the limited
    transaction-case usefulness diagnostic.
    """
    if budget <= 0:
        raise ValueError('Review budget must be positive')
    opened = {e['case_id']: e for e in events if e['event']=='opened'}
    arrivals = defaultdict(list)
    priorities = dict(thap=0,trung_binh=1,cao=2,cao_nhat=3)
    for case in cases:
        event = opened[case['case_id']]
        estimate = int(case.get('estimated_minutes', 20))
        task = dict(case=case, event=event, due=event['event_at'][:10],
                    work_type='source_initial' if case.get('case_type') == 'source' else 'initial_review',
                    estimated_minutes=estimate)
        arrivals[(case['company_id'], task['due'])].append(task)
        if int(case.get('requires_rereview', 0)) and case.get('rereview_due_at'):
            followup = dict(case=case, event=event, due=case['rereview_due_at'][:10],
                work_type='scheduled_rereview', estimated_minutes=max(10, (estimate+1)//2))
            arrivals[(case['company_id'], followup['due'])].append(followup)
    companies = sorted({case['company_id'] for case in cases})
    dates = sorted({day for _, day in arrivals})
    admitted, backlog = [], {company: [] for company in companies}
    capacity_minutes = budget * 45
    peak_items = peak_minutes = carryover = 0
    if dates:
        day = parse(dates[0]+'T00:00:00+07:00')
        final_arrival = parse(dates[-1]+'T00:00:00+07:00')
        safety = 0
        while day <= final_arrival or any(backlog.values()):
            day_text = day.date().isoformat()
            for company in companies:
                backlog[company].extend(arrivals.get((company, day_text), []))
                backlog[company].sort(key=lambda item: (-priorities[item['event']['priority']],
                    -int(item['event']['rule_score']), item['due'], item['case']['case_id'], item['work_type']))
                peak_items = max(peak_items, len(backlog[company]))
                peak_minutes = max(peak_minutes, sum(item['estimated_minutes'] for item in backlog[company]))
                used_minutes, selected = 0, []
                for item in backlog[company]:
                    if len(selected) >= budget or used_minutes + item['estimated_minutes'] > capacity_minutes:
                        continue
                    selected.append(item)
                    used_minutes += item['estimated_minutes']
                for item in selected:
                    backlog[company].remove(item)
                    case, event = item['case'], item['event']
                    identifiers = json.loads(case['transaction_ids']) if isinstance(case['transaction_ids'], str) else case['transaction_ids']
                    seen = [t for t in identifiers if t in transactions
                            and transactions[t]['posted_at'][:10] == event['event_at'][:10]
                            and transactions[t]['posted_at'] <= event['event_at']]
                    outcome = (any(int(labels[t]['is_fraud']) for t in seen)
                               if item['work_type'] == 'initial_review' else None)
                    wait = (day.date()-parse(item['due']+'T00:00:00+07:00').date()).days
                    carryover += wait > 0
                    admitted.append(dict(case_id=case['case_id'], company_id=company, day=day_text,
                        due_day=item['due'], work_type=item['work_type'],
                        estimated_minutes=item['estimated_minutes'], wait_days=wait,
                        observed_fraud=outcome, observed_transactions=len(seen)))
            day += timedelta(days=1)
            safety += 1
            if safety > 3660:
                raise RuntimeError('Workload simulation did not converge')
    judged = [r for r in admitted if r['observed_fraud'] is not None]
    return dict(budget_per_company_day=budget, capacity_minutes_per_company_day=capacity_minutes,
        unit='review_work_items_with_carryover', total_cases=len(cases),
        transaction_cases=sum(c.get('case_type', 'transaction') != 'source' for c in cases),
        source_cases=sum(c.get('case_type') == 'source' for c in cases),
        rereview_work_items=sum(r['work_type'] == 'scheduled_rereview' for r in admitted),
        total_work_items=len(admitted), total_demand_minutes=sum(r['estimated_minutes'] for r in admitted),
        admitted_cases=sum(r['work_type'] in {'initial_review','source_initial'} for r in admitted),
        backlog_cases=peak_items, peak_backlog_work_items=peak_items,
        peak_backlog_minutes=peak_minutes, carryover_work_items=carryover,
        backlog_end_work_items=sum(len(items) for items in backlog.values()),
        useful_cases=sum(r['observed_fraud'] is True for r in judged),
        precision=sum(r['observed_fraud'] is True for r in judged)/len(judged) if judged else None,
        policy='Opening evidence only; source work and declared re-review are included; unfinished work carries to later days under both slot and minute capacity.',
        admissions=admitted)
