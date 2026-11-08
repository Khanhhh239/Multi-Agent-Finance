"""Strict scalar contracts for sources used to authorize rule exceptions.

Validate every revision before as-of filtering. Copy rows so CSV normalization
cannot mutate the caller's source snapshot. Missing proof remains non-authorizing;
malformed proof raises ValueError rather than silently changing a rule's score.
"""
from datetime import date, datetime
from functools import lru_cache
import json
from pathlib import Path
import re

from .generate import PAIRS


APPROVED = ('approved', 'revoked', 'draft', 'pending', 'rejected')
VERIFIED = ('verified', 'revoked', 'unverified', 'pending', 'rejected')
APPROVAL = ('status', 'evidence_on_file', 'evidence_id', 'approver_id', 'approved_at')
PROFILES = {}


def _profile(name, identity, required=(), *, approved=False, **fields):
    fields = {'observed_at': 'timestamp', **fields}
    if approved:
        fields.update(status=APPROVED, evidence_on_file='flag', approved_at='timestamp?')
        required = (*APPROVAL, *required)
    PROFILES[name] = dict(identity=identity, required=(identity, 'company_id', 'observed_at', *required), fields=fields)


_profile('bank_account_changes', 'change_id',
         ('vendor_id', 'old_account', 'new_account', 'effective_at', 'callback_verified', 'verified_at', 'approver_id'),
         effective_at='timestamp', verified_at='timestamp?', callback_verified='flag',
         status=('active', 'cancelled', 'revoked', 'pending'))
_profile('payroll_entitlements', 'entitlement_id',
         ('employee_id', 'payroll_period', 'leave_type', 'entitled_amount_vnd'), approved=True,
         payroll_period='month', leave_type=('paid_leave', 'unpaid_leave', 'regular_payroll'),
         required_work_days='workdays', approved_paid_leave_days='days', entitled_amount_vnd='integer')
_profile('operating_schedules', 'schedule_id',
         ('action', 'weekdays', 'start_time', 'end_time', 'effective_from', 'effective_to'), approved=True,
         action=('all', 'maker', 'checker'), weekdays='weekdays', start_time='clock', end_time='clock',
         holiday_work_allowed='flag', effective_from='timestamp', effective_to='timestamp')
_profile('journal_audit_log', 'audit_id',
         ('employee_id', 'transaction_id', 'entry_origin', 'entered_at', 'evidence_id'),
         entry_origin=('manual', 'automatic'), entered_at='timestamp')
_profile('closing_periods', 'closing_id', ('period_start', 'period_end', 'closing_at'), approved=True,
         period_start='date', period_end='date', closing_at='timestamp')
_profile('materiality_policies', 'policy_id', ('effective_from', 'effective_to', 'materiality_vnd'), approved=True,
         effective_from='date', effective_to='date', materiality_vnd='integer')

_payment = json.loads(Path(__file__).with_name('payment_evidence.schema.json').read_text(encoding='utf-8'))
for _name, _spec in _payment['tables'].items():
    _profile(_name, _spec['required'][0], _spec['required'][1:],
             status=APPROVED if 'evidence_on_file' in _spec['required'] else VERIFIED,
             evidence_on_file='flag', allow_partial='flag', approved_at='timestamp?', verified_at='timestamp?',
             total_vnd='integer', expected_amount_vnd='integer', tolerance_vnd='integer',
             invoice_gross_vnd='integer?', effective_from='date_or_timestamp', effective_to='date_or_timestamp',
             frequency=('weekly', 'monthly', 'quarterly', 'yearly'), schedule_type=('annual', 'seasonal'),
             window_start_mmdd='mmdd', window_end_mmdd='mmdd',
             document_type=('invoice', 'goods_receipt', 'service_acceptance', 'purchase_order', 'contract', 'delivery_receipt'))

PROFILES['transaction_documents']['fields'].update(
    invoice_issued_at='timestamp?', invoice_net_vnd='integer?', invoice_vat_vnd='integer?',
    linked_input_vat_vnd='integer?')

_evidence = json.loads(Path(__file__).with_name('evidence_sources.schema.json').read_text(encoding='utf-8'))
for _name, _spec in _evidence['tables'].items():
    _profile(_name, _spec['fields'][0], _spec['fields'][1:], approved=_spec.get('approved', False))


def _fields(name, **fields):
    PROFILES[name]['fields'].update(fields)


_fields('leave_periods', starts_at='timestamp', ends_at='timestamp')
_fields('system_actions', action=('maker', 'checker'), action_at='timestamp')
_fields('leave_activity_authorizations', action=('all', 'maker', 'checker'), starts_at='timestamp', ends_at='timestamp')
_fields('employment_events', event_type=('termination', 'rehire', 'hire'), effective_date='date')
_fields('payroll_settlements', payroll_period='month',
        payment_kind=('regular_salary', 'backpay', 'final_settlement', 'severance', 'bonus'),
        service_period_start='date', service_period_end='date', authorized_amount_vnd='integer')
_fields('workflow_policies', required='flag', allow_override='flag', override_max_vnd='integer',
        effective_from='timestamp', effective_to='timestamp')
_fields('override_events', operation_at='timestamp', status=('executed', 'cancelled', 'pending', 'rejected'),
        normal_workflow_completed='flag')
_fields('document_series', fiscal_year='year', start_number='positive', closed_through_number='positive',
        closed_at='timestamp', cancellation_log_complete='flag')
_fields('document_register', document_number='positive', issued_at='timestamp', state=('issued', 'cancelled', 'draft', 'void'))
_fields('document_cancellations', document_number='positive')
_fields('receivable_invoices', gross_vnd='integer', issued_at='timestamp', due_at='timestamp',
        status=('issued', 'cancelled', 'draft', 'void'))
_fields('receipt_allocations', amount_vnd='integer', verified_at='timestamp?', status=VERIFIED)
_fields('receipt_coverage', covered_from='timestamp', covered_through='timestamp')
_fields('receivable_explanations', reason=('payment_plan', 'dispute', 'credit_note_pending'),
        effective_from='timestamp', expires_at='timestamp')

# Master attributes can also grant an exception (contract, work schedule, limits).
PROFILES['employees'] = dict(identity='employee_id', required=('employee_id', 'company_id', 'recorded_at'), fields={
    'recorded_at': 'timestamp', 'contract_on_file': 'flag', 'leave_request_required': 'flag',
    'self_approval_allowed': 'flag', 'approval_limit_vnd': 'integer', 'self_approval_limit_vnd': 'integer',
    'monthly_salary_vnd': 'integer', 'hired_at': 'timestamp',
    'hire_date': 'date', 'termination_date': 'date?'})
PROFILES['companies'] = dict(identity='company_id', required=('company_id',), fields={
    'saturday_operations': 'flag', 'approval_limit_vnd': 'integer'})
PROFILES['vendors'] = dict(identity='vendor_id', required=('vendor_id', 'company_id', 'recorded_at'), fields={
    'recorded_at': 'timestamp', 'registered_at': 'timestamp', 'onboarded_at': 'timestamp',
    'related_party_disclosed_at': 'timestamp?'})
PROFILES['advances'] = dict(identity='advance_id', required=('advance_id', 'company_id', 'recorded_at'), fields={
    'recorded_at': 'timestamp', 'issued_at': 'timestamp', 'original_due_at': 'timestamp', 'original_amount_vnd': 'integer'})
_profile('attendance', 'employee_id', ('payroll_period', 'days_worked_observed', 'approved_leave_days',
         'alternative_work_evidence'), payroll_period='month', days_worked_observed='days',
         approved_leave_days='days', alternative_work_evidence='flag')
_profile('advance_events', 'event_id', ('advance_id', 'event_type', 'amount_vnd', 'evidence_on_file'),
         event_type=('extension', 'settlement', 'writeoff', 'reclassification'), amount_vnd='integer',
         evidence_on_file='flag', new_due_at='timestamp?')
PROFILES['transactions'] = dict(identity='transaction_id', required=('transaction_id', 'company_id'), fields={
    'evidence_on_file': 'flag', 'goods_receipt_verified': 'flag', 'is_financial_entry': 'flag',
    'support_doc_count': 'integer', 'invoice_gross_vnd': 'integer', 'amount_vnd': 'integer',
    'approval_limit_vnd': 'positive', 'support_docs_observed_at': 'timestamp',
    'invoice_observed_at': 'timestamp?', 'goods_receipt_verified_at': 'timestamp?',
    'invoice_net_vnd': 'integer', 'invoice_vat_vnd': 'integer', 'linked_input_vat_vnd': 'integer',
    'created_at': 'timestamp', 'approved_at': 'timestamp', 'posted_at': 'timestamp',
    'invoice_issued_at': 'timestamp?'})


def flag(value):
    """Accept native booleans/0/1 and exact CSV 0/1; never int(2) as permission."""
    if (type(value) in (int, bool) and value in (0, 1)
            or isinstance(value, str) and value in ('0', '1')):
        return int(value)
    raise ValueError('expected boolean, integer 0/1, or CSV "0"/"1"')


@lru_cache(maxsize=32768)
def _temporal(value, kind):
    formats = {'timestamp': r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+07:00',
               'date': r'[0-9]{4}-[0-9]{2}-[0-9]{2}', 'month': r'[0-9]{4}-[0-9]{2}',
               'clock': r'[0-9]{2}:[0-9]{2}', 'mmdd': r'[0-9]{2}-[0-9]{2}'}
    if kind == 'date_or_timestamp':
        kind = 'date' if len(value) == 10 else 'timestamp'
    if not re.fullmatch(formats[kind], value):
        raise ValueError(f'expected canonical {kind}; timestamps use seconds and +07:00')
    if kind == 'timestamp':
        datetime.fromisoformat(value)
    elif kind == 'date':
        date.fromisoformat(value)
    elif kind == 'month':
        date.fromisoformat(value + '-01')
    elif kind == 'mmdd':
        date.fromisoformat('2000-' + value)  # annual windows may include leap day
    else:
        datetime.strptime(value, '%H:%M')


def _value(value, kind):
    if isinstance(kind, tuple):
        if not isinstance(value, str) or value not in kind:
            raise ValueError(f'expected one of {kind}')
        return value
    if kind.endswith('?'):
        if value == '':
            return value
        kind = kind[:-1]
    if kind == 'flag':
        return flag(value)
    if kind in {'integer', 'positive', 'days', 'workdays', 'year'}:
        if isinstance(value, str) and re.fullmatch('[0-9]+', value):
            value = int(value)
        if type(value) is not int or value < (1 if kind in {'positive', 'workdays', 'year'} else 0):
            raise ValueError('expected an integer in the permitted range; no floats or boolean amounts')
        if value > {'days': 31, 'workdays': 31, 'year': 9999}.get(kind, value):
            raise ValueError(f'outside {kind} range')
        return value
    if not isinstance(value, str):
        raise ValueError(f'expected {kind} string')
    if kind == 'weekdays':
        parts = value.split(',')
        if any(p not in ('0', '1', '2', '3', '4', '5', '6') for p in parts) or len(set(parts)) != len(parts):
            raise ValueError('expected unique comma-separated weekdays 0..6')
        return ','.join(sorted(parts))
    _temporal(value, kind)
    return value


def validated_record(name, record):
    spec = PROFILES[name]
    if not isinstance(record, dict):
        raise ValueError(f'Invalid {name}: expected a record')
    row = dict(record)
    identity = spec['identity']

    def fail(field, reason):
        raise ValueError(f'Invalid {name}/{row.get(identity, "<missing ID>")}.{field}: {reason}')

    missing = set(spec['required']) - row.keys()
    if missing:
        fail('schema', f'missing columns {sorted(missing)}')
    for field in (identity, 'company_id'):
        if not isinstance(row[field], str) or not row[field] or row[field] != row[field].strip():
            fail(field, 'expected a nonempty string without surrounding whitespace')
    for field, kind in spec['fields'].items():
        if field not in row:
            continue
        try:
            row[field] = _value(row[field], kind)
        except (ValueError, TypeError, OverflowError) as error:
            fail(field, str(error))
    # IDs and untyped required labels remain strings (including leading zeros).
    # Empty proof/bindings are missing evidence; whitespace is not a proof ID.
    for field, value in row.items():
        if field not in spec['fields'] and (field in spec['required'] or field.endswith('_id')
                or field in {'role', 'authorized_override_roles', 'invoice_number'} or 'account' in field or field.endswith('bank_code')):
            if not isinstance(value, str):
                fail(field, 'expected a string')
            if field.endswith('_id') and value != value.strip():
                fail(field, 'surrounding whitespace is not allowed in IDs')
    if 'txn_type' in row and row['txn_type'] not in (*PAIRS, '*', 'all'):
        fail('txn_type', 'unknown transaction type')
    if name == 'payroll_entitlements' and row['leave_type'] == 'paid_leave':
        for field in ('required_work_days', 'approved_paid_leave_days'):
            if field not in row:
                fail(field, 'required for paid leave')
    for start, end in (('approved_at', 'observed_at'), ('verified_at', 'observed_at'),
                       ('action_at', 'observed_at'), ('operation_at', 'observed_at'), ('entered_at', 'observed_at'),
                       ('issued_at', 'observed_at'), ('issued_at', 'due_at'), ('effective_from', 'effective_to'),
                       ('effective_from', 'expires_at'), ('starts_at', 'ends_at'), ('period_start', 'period_end'),
                       ('service_period_start', 'service_period_end'), ('covered_from', 'covered_through'),
                       ('start_number', 'closed_through_number')):
        if row.get(start, '') == '' or row.get(end, '') == '':
            continue
        if start == 'effective_from' and end == 'effective_to' and len(row[start]) != len(row[end]):
            fail(end, f'must use the same date/timestamp format as {start}')
        if row[start] > row[end]:
            fail(end, f'must not precede {start}')
    if name == 'document_series' and row['closed_through_number'] - row['start_number'] > 100000:
        fail('closed_through_number', 'declared range exceeds 100000')
    return row


def validated_rows(name, rows):
    return [validated_record(name, row) for row in rows]


def validated_tables(tables, names=None):
    result = tables.copy()  # preserve defaultdict behavior for absent optional sources
    for name in (PROFILES if names is None else names):
        if name in tables:
            result[name] = validated_rows(name, tables[name])
    return result
