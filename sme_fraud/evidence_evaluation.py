"""Assessment units, workload budgets and block uncertainty; no model code."""
from collections import defaultdict
from datetime import timedelta
import json
import random

from .generate import parse
from .rule_audit import confusion
from .review_capacity import CAPACITY_VERSION, ReviewCapacity, ReviewCalendar, local_date, positive_int


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


def budget_review(cases, events, transactions, labels, budget, *, capacity_minutes,
                  calendar=None, period_end=None, max_drain_days=3660):
    """Simulate initial/source/re-review work, carrying unfinished tasks forward.

    Slots and minutes are independent, explicit limits. Only work due on/before
    period_end enters this cohort; unfinished work may drain after that date.
    Opening rank and final-snapshot effort estimates remain descriptive policy;
    labels are joined afterward for the limited opening-usefulness diagnostic.
    """
    capacity = ReviewCapacity(budget, capacity_minutes)
    calendar = calendar if calendar is not None else ReviewCalendar()
    if not isinstance(calendar, ReviewCalendar):
        raise ValueError('Review calendar must be a ReviewCalendar')
    positive_int(max_drain_days, 'Maximum drain days')
    cutoff = local_date(period_end, 'Period end') if period_end is not None else None
    opened = {e['case_id']: e for e in events if e['event']=='opened'}
    arrivals = defaultdict(list)
    priorities = dict(thap=0,trung_binh=1,cao=2,cao_nhat=3)
    scoped_cases, tasks = [], []
    future_cases = future_rereviews = 0
    for case in cases:
        event = opened[case['case_id']]
        if cutoff is not None and local_date(event['event_at'][:10]) > cutoff:
            future_cases += 1
            continue
        scoped_cases.append(case)
        raw_estimate = case.get('estimated_minutes', 20)
        estimate = int(raw_estimate) if isinstance(raw_estimate, str) and raw_estimate.isdecimal() else raw_estimate
        positive_int(estimate, 'Estimated work minutes')
        task = dict(case=case, event=event, due=event['event_at'][:10],
                    work_type='source_initial' if case.get('case_type') == 'source' else 'initial_review',
                    estimated_minutes=estimate)
        arrivals[(case['company_id'], task['due'])].append(task)
        tasks.append(task)
        if int(case.get('requires_rereview', 0)) and case.get('rereview_due_at'):
            followup = dict(case=case, event=event, due=case['rereview_due_at'][:10],
                work_type='scheduled_rereview', estimated_minutes=max(10, (estimate+1)//2))
            if cutoff is not None and local_date(followup['due']) > cutoff:
                future_rereviews += 1
                continue
            arrivals[(case['company_id'], followup['due'])].append(followup)
            tasks.append(followup)
    companies = sorted({case['company_id'] for case in scoped_cases})
    dates = sorted({day for _, day in arrivals})
    admitted, backlog = [], {company: [] for company in companies}
    cutoff = cutoff or (local_date(dates[-1]) if dates else None)
    period_backlog = {company: dict(work_items=0, minutes=0) for company in companies}
    last_admission = {}
    peak_items = peak_minutes = carryover = 0
    drain_limit_reached = False
    if dates:
        day = local_date(dates[0])
        while day <= cutoff or any(backlog.values()):
            if day > cutoff:
                if not any(item['estimated_minutes'] <= capacity.minutes
                           for group in backlog.values() for item in group):
                    break  # Oversized indivisible work remains visible; never spin forever.
                if (day-cutoff).days > max_drain_days:
                    drain_limit_reached = True
                    break
            day_text = day.isoformat()
            for company in companies:
                backlog[company].extend(arrivals.get((company, day_text), []))
                backlog[company].sort(key=lambda item: (-priorities[item['event']['priority']],
                    -int(item['event']['rule_score']), item['due'], item['case']['case_id'], item['work_type']))
                peak_items = max(peak_items, len(backlog[company]))
                peak_minutes = max(peak_minutes, sum(item['estimated_minutes'] for item in backlog[company]))
                used_minutes, selected, selected_ids = 0, [], set()
                for item in backlog[company]:
                    if (not calendar.is_working_day(day) or item['case']['case_id'] in selected_ids
                            or not capacity.fits(len(selected), used_minutes, item['estimated_minutes'])):
                        continue
                    selected.append(item)
                    selected_ids.add(item['case']['case_id'])
                    used_minutes += item['estimated_minutes']
                for item in selected:
                    backlog[company].remove(item)
                    case, event = item['case'], item['event']
                    identifiers = json.loads(case['transaction_ids']) if isinstance(case['transaction_ids'], str) else case['transaction_ids']
                    seen = [t for t in identifiers if t in transactions
                            and transactions[t]['posted_at'][:10] == event['event_at'][:10]
                            and transactions[t]['posted_at'] <= event['event_at']]
                    outcome = (any(int(labels[t]['is_fraud']) for t in seen)
                               if labels is not None and item['work_type'] == 'initial_review' else None)
                    wait = (day-local_date(item['due'])).days
                    carryover += wait > 0
                    last_admission[company] = day
                    admitted.append(dict(case_id=case['case_id'], company_id=company, day=day_text,
                        due_day=item['due'], work_type=item['work_type'],
                        estimated_minutes=item['estimated_minutes'], wait_days=wait,
                        observed_fraud=outcome, observed_transactions=len(seen)))
                if day == cutoff:
                    period_backlog[company] = dict(work_items=len(backlog[company]),
                        minutes=sum(item['estimated_minutes'] for item in backlog[company]))
            day += timedelta(days=1)
    remaining = sum(len(items) for items in backlog.values())
    drain = []
    for company in companies:
        complete = not backlog[company]
        completion = max(cutoff, last_admission.get(company, cutoff)) if complete else None
        drain.append(dict(company_id=company, **period_backlog[company],
            drain_completion_date=completion.isoformat() if completion else None,
            drain_calendar_days=(completion-cutoff).days if completion else None))
    completion = max((local_date(row['drain_completion_date']) for row in drain), default=cutoff) if not remaining else None
    oversized = [dict(case_id=item['case']['case_id'], company_id=item['case']['company_id'],
                      work_type=item['work_type'], due_day=item['due'], estimated_minutes=item['estimated_minutes'],
                      reason='work_item_exceeds_daily_minute_capacity')
                 for item in tasks if item['estimated_minutes'] > capacity.minutes]
    judged = [r for r in admitted if r['observed_fraud'] is not None]
    return dict(budget_per_company_day=budget, capacity_minutes_per_company_day=capacity_minutes,
        capacity_contract=CAPACITY_VERSION, review_calendar=calendar.as_dict(),
        diagnostic_labels_provided=labels is not None,
        period_end=cutoff.isoformat() if cutoff else None,
        unit='review_work_items_with_carryover', total_cases=len(scoped_cases),
        transaction_cases=sum(c.get('case_type', 'transaction') != 'source' for c in scoped_cases),
        source_cases=sum(c.get('case_type') == 'source' for c in scoped_cases),
        excluded_cases_after_period=future_cases, excluded_rereviews_after_period=future_rereviews,
        rereview_work_items=sum(r['work_type'] == 'scheduled_rereview' for r in admitted),
        total_work_items=len(admitted), total_demand_work_items=len(tasks),
        total_demand_minutes=sum(r['estimated_minutes'] for r in tasks),
        admitted_cases=sum(r['work_type'] in {'initial_review','source_initial'} for r in admitted),
        backlog_cases=peak_items, peak_backlog_work_items=peak_items,
        peak_backlog_minutes=peak_minutes, carryover_work_items=carryover,
        backlog_at_period_end_work_items=sum(row['work_items'] for row in period_backlog.values()),
        backlog_at_period_end_minutes=sum(row['minutes'] for row in period_backlog.values()),
        period_end_by_company=drain,
        reviewed_within_period=sum(r['day'] <= cutoff.isoformat() for r in admitted),
        reviewed_after_period=sum(r['day'] > cutoff.isoformat() for r in admitted),
        drain_completion_date=completion.isoformat() if completion else None,
        drain_calendar_days=(completion-cutoff).days if completion and cutoff else None,
        drain_limit_reached=drain_limit_reached, unschedulable_work_items=oversized,
        backlog_end_work_items=remaining,
        useful_cases=sum(r['observed_fraud'] is True for r in judged),
        precision=sum(r['observed_fraud'] is True for r in judged)/len(judged) if judged else None,
        policy='Opening rank and final-snapshot effort; explicit slot/minute limits and local work calendar; period-end backlog is distinct from subsequent drain. Oversized work is not split automatically.',
        admissions=admitted)
