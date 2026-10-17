"""As-of approval authority for C2/C3; no role or amount is inferred as truth."""
from collections import defaultdict
from datetime import date, datetime
import json
from pathlib import Path
import re

from .temporal_evidence import approved_evidence, EmployeeHistory


SCHEMA = json.loads(Path(__file__).with_name('authority_policy.schema.json').read_text(encoding='utf-8'))
AUTHORITY_REQUIRED = tuple(SCHEMA['tables']['approval_authorities']['required'])
COVERAGE_REQUIRED = tuple(SCHEMA['tables']['approval_authority_coverage']['required'])


def _validated(record, identity, required):
    """Copy and validate every revision, including future/revoked source rows.

    Numeric CSV strings are normalized before revision/binding comparisons.
    Fixed local timestamp precision is required by the as-of string indexes.
    Missing proof remains non-authorizing; malformed values stop the run.
    """
    if not isinstance(record, dict):
        raise ValueError(f'Invalid authority source {identity}: expected a record')
    missing = set(required) - set(record)
    if missing:
        raise ValueError(f'Incomplete authority schema {identity}: {sorted(missing)}')
    row = dict(record)
    table = 'approval_authorities' if identity == 'authority_id' else 'approval_authority_coverage'
    schema = SCHEMA['tables'][table]

    def fail(field, reason):
        source_id = row[identity] if isinstance(row[identity], str) else '<invalid ID>'
        raise ValueError(f'Invalid {table}/{source_id}.{field}: {reason}')

    flags = tuple(field for field in ('evidence_on_file', 'self_approval_allowed') if field in required)
    amounts = tuple(field for field in ('min_amount_vnd', 'max_amount_vnd') if field in required)
    for field in required:
        if field in flags or field in amounts:
            continue
        value = row[field]
        if not isinstance(value, str):
            fail(field, 'expected a string')
        if field != 'covered_actions' and value != value.strip():
            fail(field, 'leading/trailing whitespace is not allowed')
    for field in (identity, 'company_id'):
        if not row[field]:
            fail(field, 'must not be empty')

    for field in flags:
        value = row[field]
        if ((type(value) in (int, bool) and value in (0, 1))
                or (isinstance(value, str) and value in ('0', '1'))):
            row[field] = int(value)
        else:
            fail(field, 'expected boolean, integer 0/1, or CSV "0"/"1"')
    for field in amounts:
        value = row[field]
        if type(value) is int and value >= 0:
            continue
        if isinstance(value, str) and re.fullmatch(r'[0-9]+', value):
            try:
                row[field] = int(value)
                continue
            except ValueError:
                pass
        fail(field, 'expected a nonnegative integer VND amount')

    enums = {'status': 'statuses'}
    if identity == 'authority_id':
        enums.update(action='actions', authority_level='authority_levels', authority_type='authority_types')
    for field, key in enums.items():
        if row[field] not in schema[key]:
            fail(field, f'expected one of {schema[key]}')

    if identity == 'authority_id':
        if not row['txn_type']:
            fail('txn_type', 'must not be empty; use * for all transaction types')
        if row['min_amount_vnd'] > row['max_amount_vnd']:
            fail('max_amount_vnd', 'must be at least min_amount_vnd')
        start, end = 'effective_from', 'effective_to'
    else:
        actions = [part.strip() for part in row['covered_actions'].split(',')]
        if (any(action not in schema['covered_actions'] for action in actions)
                or len(actions) != len(set(actions))):
            fail('covered_actions', f'expected unique actions from {schema["covered_actions"]}')
        row['covered_actions'] = ','.join(sorted(actions))
        start, end = 'covered_from', 'covered_through'

    for field in (start, end):
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', row[field]):
                raise ValueError
            date.fromisoformat(row[field])
        except ValueError:
            fail(field, 'expected a real date YYYY-MM-DD')
    if row[start] > row[end]:
        fail(end, f'must not precede {start}')
    for field in ('approved_at', 'observed_at'):
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+07:00', row[field]):
                raise ValueError
            datetime.fromisoformat(row[field])
        except ValueError:
            fail(field, 'expected a real timestamp YYYY-MM-DDTHH:MM:SS+07:00')
    if row['approved_at'] > row['observed_at']:
        fail('observed_at', 'must not precede approved_at')
    return row


def _tokens(value):
    return {part.strip() for part in str(value or '').split(',') if part.strip()}


class _Versioned:
    """Keep all revisions so an event is evaluated at its own action timestamp."""

    def __init__(self, rows, identity, required, binding):
        self.identity = identity
        self.by_company = defaultdict(lambda: defaultdict(list))
        fixed, revisions = {}, {}
        for record in rows:
            record = _validated(record, identity, required)
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
        self.employee_history = EmployeeHistory(tables.get('employees', []))
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

    def employee_at(self, company, employee_id, at):
        """Return only the employee snapshot already known at the action time."""
        employee = self.employee_history.employee_at(employee_id, at)
        # Select the revision before checking its company, so a transfer cannot
        # resurrect an older snapshot belonging to the requested company.
        return employee if employee and employee['company_id'] == company else None

    def _approved(self, record, company, at, subject=''):
        approver_id = record.get('approver_id', '')
        approver = self.employee_at(company, approver_id, record.get('approved_at', ''))
        return bool(
            approved_evidence(record, {approver_id: approver} if approver else {}, company, at)
            and (not subject or record['approver_id'] != subject)
        )

    def covered(self, row, action, at):
        day = at[:10]
        records = [record for record in self.coverages.records_at(row['company_id'], at)
                   if action in _tokens(record['covered_actions'])
                   and record['covered_from'][:10] <= day <= record['covered_through'][:10]
                   and self._approved(record, row['company_id'], at)]
        if not records:
            return None
        if len(records) != 1:
            return dict(_ambiguous=True,
                        coverage_ids=sorted(record['coverage_id'] for record in records))
        return records[0]

    def resolve(self, row, actor, action, at):
        coverage = self.covered(row, action, at)
        if not coverage:
            return dict(mode='legacy_fallback', status='not_covered')
        if coverage.get('_ambiguous'):
            return dict(mode='authority_matrix', status='ambiguous_coverage',
                        coverage_ids=coverage['coverage_ids'])
        employee = self.employee_at(row['company_id'], actor, at)
        if not employee or employee['company_id'] != row['company_id']:
            return dict(mode='authority_matrix', status='unknown_actor',
                        coverage_id=coverage['coverage_id'])
        amount, candidates = int(row['amount_vnd']), []
        for record in self.authorities.records_at(row['company_id'], at):
            if not self._approved(record, row['company_id'], at, actor):
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
            if not record['min_amount_vnd'] <= amount <= record['max_amount_vnd']:
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
                    self_approval_allowed=record['self_approval_allowed'] == 1,
                    authority_level=record['authority_level'],
                    authorized_min_vnd=record['min_amount_vnd'],
                    authorized_max_vnd=record['max_amount_vnd'])

    def self_approval(self, row):
        decision = self.resolve(row, row['creator_id'], 'self_approve', row['approved_at'])
        decision['permitted'] = bool(
            decision['status'] == 'authorized' and decision['self_approval_allowed']
        ) if decision['mode'] == 'authority_matrix' else None
        return decision

    def checker_level(self, row):
        return self.resolve(row, row['approver_id'], 'approve', row['approved_at'])
