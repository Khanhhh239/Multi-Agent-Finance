"""Review queue construction shared by rule-only and ML comparison runners."""
import hashlib
import json
from datetime import timedelta

from .generate import parse


def _source_cases(findings, staff):
    """Turn the latest actionable F3/F4 source state into a review case.

    A source scope has at most one open case.  A later evaluated/false snapshot
    resolves it; an information gap remains actionable and schedules re-review.
    """
    histories = {}
    for finding in findings:
        if finding.get('rule_id') not in {'F3', 'F4'} or not finding.get('scope'):
            continue
        key = finding['company_id'], finding['rule_id'], finding['scope']
        histories.setdefault(key, []).append(finding)
    cases, events = [], []
    for (company, rule, scope), rows in sorted(histories.items()):
        rows.sort(key=lambda r: r['cutoff_at'])
        latest = rows[-1]
        actionable = latest.get('signal') is True or latest.get('status') == 'information_gap'
        if not actionable:
            continue
        run = []
        for item in reversed(rows):
            if item.get('signal') is True or item.get('status') == 'information_gap':
                run.append(item)
            else:
                break
        opened_at, last_seen = run[-1]['cutoff_at'], latest['cutoff_at']
        gap = latest.get('status') == 'information_gap'
        case_id = 'SC_' + hashlib.sha256(f'{company}|{rule}|{scope}'.encode()).hexdigest()[:16]
        owners = [r for r in staff if r['company_id'] == company and r['recorded_at'] <= last_seen]
        explanation = ('Thiếu coverage hoặc bằng chứng nguồn để đánh giá ' +
                       ('dải số chứng từ' if rule == 'F3' else 'công nợ hóa đơn')) if gap else (
                       'Dải số chứng từ có khoảng trống chưa giải trình' if rule == 'F3' else
                       'Công nợ hóa đơn quá hạn còn dư và chưa có giải trình')
        priority = 'thap' if gap else 'trung_binh'
        estimate = 35 if gap else 30 if rule == 'F3' else 25
        due_hours = 336 if gap else 168
        rereview = (parse(opened_at) + timedelta(days=7)).isoformat() if gap else ''
        cases.append(dict(case_id=case_id, company_id=company, entity=f'source:{scope}',
            opened_at=opened_at, last_seen_at=last_seen, priority=priority, max_score=0,
            owner_id=owners[0]['employee_id'] if owners else '', status='new', conclusion='',
            reviewer_note='', transaction_ids=[], rule_ids={rule}, explanation_vi=explanation,
            case_type='source', source_scope=scope, source_status=latest.get('status', ''),
            estimated_minutes=estimate, requires_rereview=int(gap), rereview_due_at=rereview,
            sla_due_at=(parse(opened_at)+timedelta(hours=due_hours)).isoformat(),
            sla_basis='calendar_hours_from_source_finding_policy', observation_count=1))
        events.append(dict(case_id=case_id, event_at=opened_at, event='opened',
            transaction_id='', rule_score=0, priority=priority))
        if len(run) > 1 and any(item.get('status') != run[-1].get('status') or
                                item.get('signal') != run[-1].get('signal') for item in run[:-1]):
            events.append(dict(case_id=case_id, event_at=last_seen, event='source_state_changed',
                transaction_id='', rule_score=0, priority=priority))
    return cases, events


def review_queue(result, tables):
    staff = [r for r in tables['employees'] if r['role'] == 'chief_accountant']
    cases, events, active = [], [], {}
    for score in result['scores']:
        if not score['operational_alert']:
            continue
        key = (score['company_id'], score['case_entity'])
        previous = active.get(key)
        when = parse(score['posted_at'])
        if previous is None or (when - parse(previous['opened_at'])).total_seconds() > 30 * 86400:
            case_id = 'RC_' + hashlib.sha256(f"{key}|{score['transaction_id']}".encode()).hexdigest()[:16]
            owners = [r for r in staff if r['company_id'] == key[0] and r['recorded_at'] <= score['posted_at']]
            previous = dict(case_id=case_id, company_id=key[0], entity=key[1], opened_at=score['posted_at'],
                            last_seen_at=score['posted_at'], priority=score['priority'], max_score=score['rule_score'],
                            owner_id=owners[0]['employee_id'] if owners else '', status='new',
                            conclusion='', reviewer_note='', transaction_ids=[], rule_ids=set(), explanation_vi='',
                            case_type='transaction', source_scope='', source_status='', estimated_minutes=20,
                            requires_rereview=0, rereview_due_at='')
            active[key] = previous
            cases.append(previous)
            events.append(dict(case_id=case_id, event_at=score['posted_at'], event='opened',
                               transaction_id=score['transaction_id'], rule_score=score['rule_score'], priority=score['priority']))
        previous['last_seen_at'] = score['posted_at']
        previous['transaction_ids'].append(score['transaction_id'])
        previous['rule_ids'].update(score['rule_ids'].split('|'))
        priority_order = {'thap': 0, 'trung_binh': 1, 'cao': 2, 'cao_nhat': 3}
        if priority_order[score['priority']] > priority_order[previous['priority']]:
            previous['priority'] = score['priority']
            events.append(dict(case_id=previous['case_id'], event_at=score['posted_at'], event='escalated',
                               transaction_id=score['transaction_id'], rule_score=score['rule_score'], priority=score['priority']))
        if score['rule_score'] >= previous['max_score']:
            previous['max_score'] = score['rule_score']
            previous['explanation_vi'] = score['explanation_vi']
    source_cases, source_events = _source_cases(result.get('evidence_findings', []), staff)
    cases.extend(source_cases)
    events.extend(source_events)
    for case in cases:
        if case['case_type'] == 'transaction':
            hours = {'cao_nhat': 24, 'cao': 48, 'trung_binh': 168, 'thap': 720}[case['priority']]
            case['sla_due_at'] = (parse(case['opened_at']) + timedelta(hours=hours)).isoformat()
            case['sla_basis'] = 'calendar_hours_from_opened_at_simulation_policy'
            case['observation_count'] = len(case['transaction_ids'])
            case['estimated_minutes'] = min(45, 20 + 5 * max(0, case['observation_count'] - 1))
        case['transaction_ids'] = json.dumps(case['transaction_ids'], ensure_ascii=False)
        case['rule_ids'] = '|'.join(sorted(case['rule_ids']))
    cases.sort(key=lambda r: (-r['max_score'], r['opened_at'], r['case_id']))
    return cases, events
