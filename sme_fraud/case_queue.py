"""Review queue construction shared by rule-only and ML comparison runners."""
import hashlib
import json
from datetime import timedelta

from .generate import parse


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
                            conclusion='', reviewer_note='', transaction_ids=[], rule_ids=set(), explanation_vi='')
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
    for case in cases:
        hours = {'cao_nhat': 24, 'cao': 48, 'trung_binh': 168, 'thap': 720}[case['priority']]
        case['sla_due_at'] = (parse(case['opened_at']) + timedelta(hours=hours)).isoformat()
        case['sla_basis'] = 'calendar_hours_from_opened_at_simulation_policy'
        case['observation_count'] = len(case['transaction_ids'])
        case['transaction_ids'] = json.dumps(case['transaction_ids'], ensure_ascii=False)
        case['rule_ids'] = '|'.join(sorted(case['rule_ids']))
    cases.sort(key=lambda r: (-r['max_score'], r['opened_at'], r['case_id']))
    return cases, events
