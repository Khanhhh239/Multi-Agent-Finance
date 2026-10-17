"""Review queue construction shared by rule-only and ML comparison runners."""
import hashlib
import json
from collections import defaultdict
from datetime import timedelta

from .generate import parse
from .temporal_evidence import EmployeeHistory
from .case_identity import IDENTITY_VERSION, scope_hash, values
from .case_admission import admission


def owner_at(staff, company, at):
    return min((r['employee_id'] for r in staff.at(at).values()
                if r['company_id'] == company and r['role'] == 'chief_accountant'), default='')


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
            owner_id=owner_at(staff, company, last_seen), status='new', conclusion='',
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


def batch_groups(result):
    """Combine overlapping positive events at one company/cutoff, once per batch."""
    partitions = defaultdict(list)
    for event in result.get('batch_events', []):
        if event['points'] > 0:
            partitions[(event['company_id'], event['detected_at'])].append(event)
    groups = []
    for (company, at), events in sorted(partitions.items()):
        parents, owners = {}, {}

        def root(key):
            while parents[key] != key:
                parents[key] = parents[parents[key]]
                key = parents[key]
            return key

        for event in sorted(events, key=lambda e: e['event_id']):
            key = event['event_id']
            parents[key] = key
            for tid in event['transaction_ids']:
                if tid in owners:
                    left, right = sorted((root(key), root(owners[tid])))
                    parents[right] = left
                owners[tid] = key
        components = defaultdict(list)
        for event in events:
            components[root(event['event_id'])].append(event)
        for component in components.values():
            component.sort(key=lambda e: e['event_id'])
            families = {}
            for event in component:
                family = event['rule_id'][0]
                families[family] = max(families.get(family, 0), event['points'])
            score = sum(families.values())
            hard = any(e['hard_trigger'] for e in component)
            review = admission(component, score, hard, result.get('config', {}))
            if not review['operational_alert']:
                continue
            event_ids = [e['event_id'] for e in component]
            identity = hashlib.sha256(json.dumps([company, at, event_ids]).encode()).hexdigest()[:16]
            groups.append(dict(company_id=company, posted_at=at, transaction_id='', case_entity='batch:'+identity,
                rule_score=score, **review,
                rule_ids='|'.join(sorted({e['rule_id'] for e in component})),
                explanation_vi='Đối chiếu các khoản cùng thời điểm: '+'; '.join(sorted({e['rule_name'] for e in component})),
                _members=sorted({tid for e in component for tid in e['transaction_ids']}), _batch_events=event_ids))
    return sorted(groups, key=lambda g: (g['posted_at'], g['company_id'], g['case_entity']))


def operational_members(result):
    """Include batch participants without relabeling their row scores."""
    return ({r['transaction_id'] for r in result['scores'] if r['operational_alert']}
            | {tid for group in batch_groups(result) for tid in group['_members']})


def review_queue(result, tables):
    staff = EmployeeHistory(tables['employees'])
    cases, events, active = [], [], {}
    score_by_id = {r['transaction_id']: r for r in result['scores']}
    member_case = {}
    arrivals = [dict(r, _members=[r['transaction_id']], _batch_events=[])
                for r in result['scores'] if r['operational_alert']]
    arrivals.extend(batch_groups(result))
    arrivals.sort(key=lambda r: (r['posted_at'], bool(r['_batch_events']), r['transaction_id'] or r['case_entity']))
    for score in arrivals:
        is_batch = bool(score['_batch_events'])
        key = (score['company_id'], score['case_entity'])
        when = parse(score['posted_at'])
        matching = {member_case[tid]['case_id']: member_case[tid]
                    for tid in score['_members'] if tid in member_case} if is_batch else {}
        if is_batch and not matching:
            for tid in score['_members']:
                row = score_by_id[tid]
                candidate = active.get((row['company_id'], row['case_entity']))
                if candidate and (when-parse(candidate['opened_at'])).total_seconds() <= 30*86400:
                    matching[candidate['case_id']] = candidate
        previous = min(matching.values(), key=lambda c: (c['opened_at'], c['case_id'])) if matching else active.get(key)
        if previous is None or (when - parse(previous['opened_at'])).total_seconds() > 30 * 86400:
            case_id = ('BC_'+score['case_entity'].split(':', 1)[1] if is_batch else
                       'RC_' + hashlib.sha256(f"{key}|{score['transaction_id']}".encode()).hexdigest()[:16])
            previous = dict(case_id=case_id, company_id=key[0], entity=key[1], opened_at=score['posted_at'],
                            last_seen_at=score['posted_at'], priority=score['priority'], max_score=score['rule_score'],
                            owner_id=owner_at(staff, key[0], score['posted_at']), status='new',
                            conclusion='', reviewer_note='', transaction_ids=[], rule_ids=set(), explanation_vi='', batch_event_ids=set(),
                            case_type='batch' if is_batch else 'transaction', source_scope='', source_status='', estimated_minutes=20,
                            requires_rereview=0, rereview_due_at='', admission_basis=set(), review_rule_ids=set())
            previous['cluster_members'] = set()
            active[key] = previous
            cases.append(previous)
            events.append(dict(case_id=case_id, event_at=score['posted_at'], event='opened',
                               transaction_id=score['transaction_id'], rule_score=score['rule_score'], priority=score['priority']))
        for tid in score['_members']:
            if tid not in member_case:
                previous['transaction_ids'].append(tid)
                member_case[tid] = previous
            row = score_by_id[tid]
            active[(row['company_id'], row['case_entity'])] = member_case[tid]
        affected = {previous['case_id']: previous, **matching}
        for case in affected.values():
            case['admission_basis'].update(filter(None, score.get('admission_basis', '').split('|')))
            case['review_rule_ids'].update(filter(None, score.get('review_rule_ids', '').split('|')))
            for tid in score['_members']:
                case['cluster_members'].update(values(score_by_id[tid].get('case_cluster_members')))
            case['last_seen_at'] = score['posted_at']
            case['rule_ids'].update(score['rule_ids'].split('|'))
            case['batch_event_ids'].update(score['_batch_events'])
            priority_order = {'thap': 0, 'trung_binh': 1, 'cao': 2, 'cao_nhat': 3}
            if priority_order[score['priority']] > priority_order[case['priority']]:
                case['priority'] = score['priority']
                events.append(dict(case_id=case['case_id'], event_at=score['posted_at'], event='escalated',
                                   transaction_id=score['transaction_id'], rule_score=score['rule_score'], priority=score['priority']))
            if score['rule_score'] >= case['max_score']:
                case['max_score'] = score['rule_score']
                case['explanation_vi'] = score['explanation_vi']
            if is_batch:
                events.append(dict(case_id=case['case_id'], event_at=score['posted_at'], event='batch_closed',
                                   transaction_id='', rule_score=score['rule_score'], priority=score['priority']))
    source_cases, source_events = _source_cases(result.get('evidence_findings', []), staff)
    cases.extend(source_cases)
    events.extend(source_events)
    for case in cases:
        case['admission_basis'] = '|'.join(sorted(case.get('admission_basis', [])))
        case['review_rule_ids'] = '|'.join(sorted(case.get('review_rule_ids', [])))
        case['identity_version'] = IDENTITY_VERSION
        case['cluster_members'] = json.dumps(sorted(case.get('cluster_members', [])))
        if case['case_type'] != 'source':
            hours = {'cao_nhat': 24, 'cao': 48, 'trung_binh': 168, 'thap': 720}[case['priority']]
            case['sla_due_at'] = (parse(case['opened_at']) + timedelta(hours=hours)).isoformat()
            case['sla_basis'] = 'calendar_hours_from_opened_at_simulation_policy'
            case['observation_count'] = len(case['transaction_ids'])
            case['estimated_minutes'] = min(45, 20 + 5 * max(0, case['observation_count'] - 1))
        case['transaction_ids'] = json.dumps(case['transaction_ids'], ensure_ascii=False)
        case['rule_ids'] = '|'.join(sorted(case['rule_ids']))
        case['batch_event_ids'] = json.dumps(sorted(case.get('batch_event_ids', [])))
        case['scope_hash'] = scope_hash(case)
    cases.sort(key=lambda r: (-r['max_score'], r['opened_at'], r['case_id']))
    return cases, events
