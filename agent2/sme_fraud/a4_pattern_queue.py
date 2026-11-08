"""Opt-in review organization for A4; never changes detection or exemptions."""
import json
from collections import defaultdict

from .case_identity import digest

ENTITY_QUEUE = 'entity_v1'
A4_PATTERN_TRIAL = 'a4_pattern_trial_v1'


def active_a4(item):
    return (item['rule_id'] == 'A4' and item['points'] > 0
            and not item.get('suppressed_reason')
            and item.get('status', 'evaluated') == 'evaluated'
            and item.get('signal', True) is True
            and item.get('evidence', {}).get('evidence_status') != 'information_gap')


def prepare_arrivals(arrivals, result, tables):
    config = result['config']
    if config.get('spec_policy') != 'phase3' or config.get('near_period') != 'calendar_month':
        raise ValueError('A4 pattern trial requires the calendar-month A4 policy')
    transactions = {row['transaction_id']: row for row in tables['transactions']}
    scores = {row['transaction_id']: row for row in result['scores']}
    hits = defaultdict(list)
    for hit in result['hits']:
        if active_a4(hit):
            hits[hit['transaction_id']].append(hit)
    events = {event['event_id']: event for event in result.get('batch_events', [])}

    def weak_a4(score):
        return (score.get('admission_basis') == 'split_pattern'
                and score.get('rule_ids') == 'A4' and score.get('review_rule_ids') == 'A4'
                and not score.get('hard_trigger', False))

    def route(arrival):
        if not weak_a4(arrival):
            return None
        evidence = ([events[key] for key in arrival['_batch_events']] if arrival['_batch_events']
                    else hits[arrival['transaction_id']])
        if not evidence or not all(active_a4(item) for item in evidence):
            return None
        current = [transactions[tid] for tid in arrival['_members']]
        company, maker, month = current[0]['company_id'], current[0]['creator_id'], arrival['posted_at'][:7]
        if not maker or any(item['evidence'].get('period') != month for item in evidence):
            return None
        related = {tid for item in evidence for tid in item['related_transaction_ids']}
        if any((transactions[tid]['company_id'], transactions[tid]['creator_id'], transactions[tid]['posted_at'][:7])
               != (company, maker, month) for tid in {*arrival['_members'], *related}):
            return None
        scope = dict(policy=A4_PATTERN_TRIAL, rule_id='A4', company_id=company, maker_id=maker,
                     period=month, near_period='calendar_month', near_count=config['near_count'],
                     near_low=config['near_low'], near_high=config['near_high'],
                     operational_score=config['operational_score'])
        return dict(_pattern_scope=scope, _pattern_context_ids=related,
                    _pattern_evidence_ids={item.get('event_id') or item['evidence_id'] for item in evidence})

    routes = {id(arrival): route(arrival) for arrival in arrivals}
    blocked = set()
    for arrival in arrivals:
        if not arrival['_batch_events']:
            continue
        # A timestamp batch with any strong/mixed member keeps the ordinary
        # entity/batch path intact, including its hard-trigger case.
        if routes[id(arrival)] is None or any(
                scores[tid]['operational_alert'] and not weak_a4(scores[tid]) for tid in arrival['_members']):
            blocked.update(arrival['_members'])
            routes[id(arrival)] = None
    prepared = []
    for arrival in arrivals:
        extra = routes[id(arrival)]
        if extra is not None and not (set(arrival['_members']) & blocked):
            arrival = dict(arrival, **extra,
                           case_entity='pattern:A4:'+digest(extra['_pattern_scope'])[:24])
        prepared.append(arrival)
    return prepared


def finish_cases(cases, result):
    """Links are navigation only, never feedback aliases or shared decisions."""
    owners = {tid: case for case in cases for tid in case['transaction_ids']}
    for case in cases:
        case.setdefault('pattern_scope', '')
        case.setdefault('pattern_context_ids', set())
        case.setdefault('pattern_evidence_ids', set())
        case['linked_case_ids'] = set()
        if case['case_type'] == 'pattern':
            case['pattern_context_ids'].difference_update(case['transaction_ids'])
            case['linked_case_ids'].update(owners[tid]['case_id'] for tid in case['pattern_context_ids']
                if tid in owners and owners[tid]['case_id'] != case['case_id'])
    for hit in result['hits']:
        if not active_a4(hit) or hit['transaction_id'] not in owners:
            continue
        owner = owners[hit['transaction_id']]
        for tid in hit['related_transaction_ids']:
            related = owners.get(tid)
            if related and related['case_type'] == 'pattern' and related is not owner:
                owner['linked_case_ids'].add(related['case_id'])
    for case in cases:
        for name in ('pattern_context_ids', 'pattern_evidence_ids', 'linked_case_ids'):
            case[name] = json.dumps(sorted(case[name]))
        if isinstance(case['pattern_scope'], dict):
            case['pattern_scope'] = json.dumps(case['pattern_scope'], sort_keys=True, separators=(',', ':'))


def validate_pattern_case(case, transactions, hits, batch_events):
    if case.get('case_type') != 'pattern':
        if case.get('pattern_scope'):
            raise ValueError('Pattern scope requires a pattern case')
        return
    scope = json.loads(case.get('pattern_scope') or '{}')
    key = digest(scope)[:24]
    if (scope.get('policy') != A4_PATTERN_TRIAL or scope.get('rule_id') != 'A4'
            or scope.get('near_period') != 'calendar_month'
            or case['case_id'] != 'PC_'+key or case['entity'] != 'pattern:A4:'+key
            or case['company_id'] != scope.get('company_id') or case['rule_ids'] != ['A4']
            or case.get('admission_basis') != 'split_pattern'
            or not 0 < case['max_score'] < scope.get('operational_score', 0)):
        raise ValueError('Invalid A4 pattern scope or admission')
    evidence = [hit for hit in hits if active_a4(hit)] + [event for event in batch_events if active_a4(event)]
    identifiers = {item.get('event_id') or item['evidence_id'] for item in evidence}
    expected_context = {tid for item in evidence for tid in item['related_transaction_ids']} - set(case['transaction_ids'])
    context = json.loads(case.get('pattern_context_ids') or '[]')
    if (not evidence or identifiers != set(json.loads(case.get('pattern_evidence_ids') or '[]'))
            or set(context) != expected_context or len(context) != len(set(context))
            or min(item['detected_at'] for item in evidence) != case['opened_at']
            or max(item['detected_at'] for item in evidence) != case['last_seen_at']):
        raise ValueError('Invalid A4 pattern evidence binding')
    for tid in [*case['transaction_ids'], *context]:
        row = transactions[tid]
        if (row['company_id'] != scope['company_id'] or row['creator_id'] != scope.get('maker_id')
                or row['posted_at'][:7] != scope.get('period') or row['posted_at'] > case['last_seen_at']):
            raise ValueError('Invalid A4 pattern transaction scope or time')
