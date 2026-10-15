"""As-of approval authority for C2/C3; no role or amount is inferred as truth."""
from collections import defaultdict

from .temporal_evidence import approved_evidence


AUTHORITY_REQUIRED = (
    'authority_id', 'company_id', 'subject_employee_id', 'subject_role',
    'action', 'txn_type', 'department', 'project_id', 'min_amount_vnd',
    'max_amount_vnd', 'self_approval_allowed', 'authority_level',
    'authority_type', 'delegated_by_id', 'effective_from', 'effective_to',
    'status', 'evidence_on_file', 'evidence_id', 'approver_id',
    'approved_at', 'observed_at',
)
COVERAGE_REQUIRED = (
    'coverage_id', 'company_id', 'covered_actions', 'covered_from',
    'covered_through', 'status', 'evidence_on_file', 'evidence_id',
    'approver_id', 'approved_at', 'observed_at',
)


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tokens(value):
    return {part.strip() for part in str(value or '').split(',') if part.strip()}


class _Versioned:
    """Keep all revisions so an event is evaluated at its own action timestamp."""

    def __init__(self, rows, identity, required, binding):
        self.identity = identity
        self.by_company = defaultdict(lambda: defaultdict(list))
        fixed, revisions = {}, {}
        for record in rows:
            missing = set(required) - set(record)
            if missing:
                raise ValueError(f'Incomplete authority schema {identity}: {sorted(missing)}')
            if not record[identity]:
                raise ValueError(f'Empty authority source ID: {identity}')
            key = record['company_id'], record[identity]
            signature = tuple(record.get(field, '') for field in binding)
            if key in fixed and fixed[key] != signature:
                raise ValueError(f'Authority binding changed: {identity}/{key}')
            fixed[key] = signature
            version = key, record['observed_at']
            if version in revisions and revisions[version] != record:
                raise ValueError(f'Conflicting authority revision: {identity}/{version}')
            revisions[version] = record
            self.by_company[record['company_id']][record[identity]].append(record)
        for records in self.by_company.values():
            for versions in records.values():
                versions.sort(key=lambda row: row['observed_at'])

    def records_at(self, company, at):
        answer = []
        for versions in self.by_company.get(company, {}).values():
            current = None
            for record in versions:
                if record['observed_at'] > at:
                    break
                current = record
            if current:
                answer.append(current)
        return answer


class ApprovalAuthority:
    """Resolve explicit authority only when a complete matrix covers the action."""

    def __init__(self, tables):
        self.authorities = _Versioned(
            tables.get('approval_authorities', []), 'authority_id', AUTHORITY_REQUIRED,
            ('subject_employee_id', 'subject_role', 'action', 'txn_type',
             'department', 'project_id', 'min_amount_vnd', 'max_amount_vnd',
             'self_approval_allowed', 'authority_level', 'authority_type', 'delegated_by_id',
             'effective_from', 'effective_to'),
        )
        self.coverages = _Versioned(
            tables.get('approval_authority_coverage', []), 'coverage_id', COVERAGE_REQUIRED,
            ('covered_actions', 'covered_from', 'covered_through'),
        )

    @staticmethod
    def _approved(record, staff, company, at, subject=''):
        return bool(
            approved_evidence(record, staff, company, at)
            and (not subject or record['approver_id'] != subject)
        )

    def covered(self, row, action, staff, at):
        day = at[:10]
        records = [record for record in self.coverages.records_at(row['company_id'], at)
                   if action in _tokens(record['covered_actions'])
                   and record['covered_from'][:10] <= day <= record['covered_through'][:10]
                   and self._approved(record, staff, row['company_id'], at)]
        if not records:
            return None
        if len(records) != 1:
            return dict(_ambiguous=True,
                        coverage_ids=sorted(record['coverage_id'] for record in records))
        return records[0]

    def resolve(self, row, actor, action, staff, at):
        coverage = self.covered(row, action, staff, at)
        if not coverage:
            return dict(mode='legacy_fallback', status='not_covered')
        if coverage.get('_ambiguous'):
            return dict(mode='authority_matrix', status='ambiguous_coverage',
                        coverage_ids=coverage['coverage_ids'])
        employee = staff.get(actor)
        if not employee or employee['company_id'] != row['company_id']:
            return dict(mode='authority_matrix', status='unknown_actor',
                        coverage_id=coverage['coverage_id'])
        amount, candidates = _integer(row['amount_vnd']), []
        for record in self.authorities.records_at(row['company_id'], at):
            if not self._approved(record, staff, row['company_id'], at, actor):
                continue
            if record['action'] not in {action, 'all'}:
                continue
            if record['txn_type'] not in {row['txn_type'], '*'}:
                continue
            if record['subject_employee_id']:
                if record['subject_employee_id'] != actor:
                    continue
            elif record['subject_role'] != employee.get('role'):
                continue
            if record['department'] and record['department'] != row.get('department'):
                continue
            if record['project_id'] and record['project_id'] != row.get('project_id'):
                continue
            if not record['effective_from'][:10] <= at[:10] <= record['effective_to'][:10]:
                continue
            if not _integer(record['min_amount_vnd']) <= amount <= _integer(record['max_amount_vnd'], -1):
                continue
            if record['authority_type'] == 'delegation' and (
                    not record['delegated_by_id'] or record['delegated_by_id'] == actor):
                continue
            specificity = (
                int(bool(record['subject_employee_id'])),
                int(record['action'] != 'all'),
                int(record['txn_type'] != '*'),
                int(bool(record['department'])),
                int(bool(record['project_id'])),
            )
            candidates.append((specificity, record))
        if not candidates:
            return dict(mode='authority_matrix', status='no_matching_authority',
                        coverage_id=coverage['coverage_id'])
        best = max(score for score, _ in candidates)
        selected = [record for score, record in candidates if score == best]
        outcomes = {(record['self_approval_allowed'], record['authority_level'])
                    for record in selected}
        if len(outcomes) != 1:
            return dict(mode='authority_matrix', status='ambiguous_authority',
                        coverage_id=coverage['coverage_id'],
                        authority_ids=sorted(record['authority_id'] for record in selected))
        record = sorted(selected, key=lambda item: item['authority_id'])[0]
        return dict(mode='authority_matrix', status='authorized',
                    coverage_id=coverage['coverage_id'], authority_id=record['authority_id'],
                    authority_type=record['authority_type'],
                    delegated_by_id=record['delegated_by_id'],
                    self_approval_allowed=bool(_integer(record['self_approval_allowed'])),
                    authority_level=record['authority_level'],
                    authorized_min_vnd=_integer(record['min_amount_vnd']),
                    authorized_max_vnd=_integer(record['max_amount_vnd']))

    def self_approval(self, row, staff):
        decision = self.resolve(row, row['creator_id'], 'self_approve', staff, row['approved_at'])
        decision['permitted'] = bool(
            decision['status'] == 'authorized' and decision['self_approval_allowed']
        ) if decision['mode'] == 'authority_matrix' else None
        return decision

    def checker_level(self, row, staff):
        return self.resolve(row, row['approver_id'], 'approve', staff, row['approved_at'])
