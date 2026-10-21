"""Explain frozen transaction admissions without changing detector observations."""
from collections import defaultdict
import hashlib
import json

from .case_queue import batch_groups
from .case_identity import values


VERSION = 'admission-provenance-v2'
FIELDS = ('transaction_id', 'period', 'is_fraud', 'fraud_type', 'hard_negative_type',
    'company_id', 'posted_at', 'rule_score', 'row_operational_alert', 'row_hard_trigger',
    'row_rule_ids', 'row_admission_basis', 'row_review_rule_ids',
    'effective_admission_basis', 'effective_review_rule_ids', 'admission_source',
    'effective_admitted_at', 'case_ids', 'batch_event_ids', 'event_rule_ids',
    'row_hit_evidence_ids', 'admission_evidence_ref')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def flag(value):
    if value not in (0, 1, '0', '1'):
        raise ValueError('Admission flags must be 0/1')
    return int(value)


def pipe(value):
    return set(filter(None, value.split('|')))


def explain_admissions(result, cases, selected_ids, *, source_directory='.', metadata=None):
    """Return CSV rows and linked evidence for exactly the requested new members.

    Batch eligibility comes from the shared frozen queue policy. Connected batch
    events can admit each other's participants; prior/context IDs never become
    participants. Case-level rule summaries are not transaction admission proof.
    """
    metadata = metadata or {}
    scores = {}
    for row in result['scores']:
        identity = row['transaction_id']
        if identity in scores:
            raise ValueError('Duplicate transaction score')
        scores[identity] = row
    wanted = set(selected_ids)
    if wanted - set(scores):
        raise ValueError('Requested admission has no frozen row score')
    events = {}
    for event in result.get('batch_events', []):
        identity = event['event_id']
        if identity in events:
            raise ValueError('Duplicate batch event ID')
        events[identity] = event
        if int(event['points']) > 0 and (event.get('suppressed_reason') or
                event.get('status', 'evaluated') != 'evaluated' or event.get('signal', True) is not True):
            raise ValueError('Positive batch event has non-authorizing evidence')
        for tid in event['transaction_ids']:
            row = scores.get(tid)
            if row is None or row['company_id'] != event['company_id'] or row['posted_at'] != event['detected_at']:
                raise ValueError('Batch participant missing, cross-company or at a different timestamp')
    # Decode CSV flags on copies, never mutate the original frozen observations.
    decoded = dict(result, scores=[dict(row, operational_alert=flag(row['operational_alert']))
                                  for row in scores.values()])
    groups = batch_groups(decoded)
    groups_by_member = defaultdict(list)
    admitted = {tid for tid, row in scores.items() if flag(row['operational_alert'])}
    for group in groups:
        admitted.update(group['_members'])
        for tid in group['_members']:
            groups_by_member[tid].append(group)
    owners, case_ids = defaultdict(list), set()
    for case in cases:
        if case['case_id'] in case_ids:
            raise ValueError('Duplicate case ID')
        case_ids.add(case['case_id'])
        for tid in values(case.get('transaction_ids')):
            if tid not in scores or scores[tid]['company_id'] != case['company_id']:
                raise ValueError('Case member missing or cross-company')
            owners[tid].append(case)
    if set(owners) != admitted or any(len(rows) != 1 for rows in owners.values()):
        raise ValueError('Frozen queue membership differs from operational admissions')
    if wanted - admitted:
        raise ValueError('Requested transaction was not operationally admitted')
    hits_by_member = defaultdict(list)
    for hit in result.get('hits', []):
        if hit['transaction_id'] in wanted and int(hit['points']) > 0 and not hit.get('suppressed_reason'):
            if hit.get('status', 'evaluated') != 'evaluated' or hit.get('evidence', {}).get('evidence_status') == 'information_gap':
                continue
            row = scores[hit['transaction_id']]
            if hit['company_id'] != row['company_id'] or hit['detected_at'] != row['posted_at']:
                raise ValueError('Row hit does not belong to the frozen observation')
            if not hit.get('evidence_id'):
                raise ValueError('Row admission hit has no evidence ID')
            hits_by_member[hit['transaction_id']].append(hit)
    prefix = source_directory.rstrip('/\\')

    def locator(name, identity_field, identity):
        return dict(path=prefix+'/'+name, identity_field=identity_field, identity=identity)

    rows, proof = [], []
    for tid in sorted(wanted):
        row, member_groups, own_cases = scores[tid], groups_by_member[tid], owners[tid]
        by_row = bool(flag(row['operational_alert']))
        row_basis = row.get('admission_basis', '')
        if by_row and not row_basis:
            raise ValueError('Admitted row has no admission basis')
        row_hits = sorted(hits_by_member[tid], key=lambda hit: (hit['rule_id'], hit['evidence_id'])) if by_row else []
        if by_row and not row_hits:
            raise ValueError('Admitted row has no active hit evidence')
        group_event_ids = sorted({identity for group in member_groups for identity in group['_batch_events']})
        for case in own_cases:
            if set(group_event_ids) - set(values(case.get('batch_event_ids'))):
                raise ValueError('Admitting batch event is not linked to the owning case')
        selected_events = [events[identity] for identity in group_event_ids]
        bases = ({row_basis} if by_row else set()) | {group['admission_basis'] for group in member_groups}
        review_rules = (pipe(row.get('review_rule_ids', '')) if by_row else set())
        for group in member_groups:
            review_rules.update(pipe(group['review_rule_ids']))
        times = ([row['posted_at']] if by_row else []) + [group['posted_at'] for group in member_groups]
        evidence = dict(version=VERSION, transaction_id=tid, company_id=row['company_id'],
            row=locator('rule_scores.csv', 'transaction_id', tid),
            row_hits=[dict(source=locator('rule_hits.jsonl', 'evidence_id', hit['evidence_id']),
                rule_id=hit['rule_id'], evidence_id=hit['evidence_id'], detected_at=hit['detected_at'],
                record_sha256=digest(hit), evidence=hit.get('evidence', {})) for hit in row_hits],
            cases=[locator('case_queue.csv', 'case_id', case['case_id']) for case in own_cases],
            batch_groups=[dict(company_id=group['company_id'], detected_at=group['posted_at'],
                admission_basis=group['admission_basis'], rule_score=group['rule_score'],
                review_rule_ids=group['review_rule_ids'], event_ids=group['_batch_events'],
                participant_ids=group['_members']) for group in member_groups],
            batch_events=[dict(source=locator('batch_events.jsonl', 'event_id', event['event_id']),
                rule_id=event['rule_id'], detected_at=event['detected_at'],
                direct_participant=tid in event['transaction_ids'],
                transaction_ids=event['transaction_ids'], related_transaction_ids=event['related_transaction_ids'],
                record_sha256=digest(event), evidence=event.get('evidence', {})) for event in selected_events])
        evidence_id = 'AE_'+digest(evidence)[:24]
        proof.append(dict(admission_evidence_id=evidence_id, **evidence))
        meta = metadata.get(tid, {})
        rows.append(dict(transaction_id=tid,
            **{field: meta.get(field, '') for field in ('period', 'is_fraud', 'fraud_type', 'hard_negative_type')},
            company_id=row['company_id'], posted_at=row['posted_at'], rule_score=row['rule_score'],
            row_operational_alert=row['operational_alert'], row_hard_trigger=row['hard_trigger'],
            row_rule_ids=row['rule_ids'], row_admission_basis=row_basis,
            row_review_rule_ids=row.get('review_rule_ids', ''),
            effective_admission_basis='|'.join(sorted(bases)), effective_review_rule_ids='|'.join(sorted(review_rules)),
            admission_source='|'.join((['row'] if by_row else []) + (['batch_closed'] if member_groups else [])),
            effective_admitted_at=min(times), case_ids=json.dumps(sorted(case['case_id'] for case in own_cases)),
            batch_event_ids=json.dumps(group_event_ids), event_rule_ids='|'.join(sorted({event['rule_id'] for event in selected_events})),
            row_hit_evidence_ids=json.dumps([hit['evidence_id'] for hit in row_hits]),
            admission_evidence_ref='admission_evidence.jsonl#'+evidence_id))
    return rows, proof
