"""Shared as-of source records for rules and observable bank features."""
from bisect import bisect_right
from collections import defaultdict
from functools import lru_cache
import re
import unicodedata

from .generate import parse
from .exception_validation import flag, validated_record, validated_rows


class EmployeeHistory:
    """Global employee revisions; choose the timestamp before checking company."""
    def __init__(self, rows):
        rows = validated_rows('employees', rows)
        self.versions, self.times, self.cache = defaultdict(list), {}, {}
        revisions = {}
        for row in rows:
            key = row['employee_id'], row['recorded_at']
            if key in revisions:
                if revisions[key] != row:
                    raise ValueError(f'Conflicting employee revision: {key}')
                continue
            snapshot = dict(row)
            revisions[key] = snapshot
            self.versions[row['employee_id']].append(snapshot)
        for identity, versions in self.versions.items():
            versions.sort(key=lambda row: row['recorded_at'])
            self.times[identity] = [row['recorded_at'] for row in versions]

    def employee_at(self, identity, at):
        if not at:
            return None
        index = bisect_right(self.times.get(identity, []), at) - 1
        return self.versions[identity][index] if index >= 0 else None

    def at(self, at):
        """Read-only snapshot mapping, also used by existing evidence APIs."""
        if at not in self.cache:
            if len(self.cache) >= 512:
                self.cache.pop(next(iter(self.cache)))
            self.cache[at] = {identity: employee for identity in self.versions
                              if (employee := self.employee_at(identity, at)) is not None}
        return self.cache[at]


def employee_at(staff, identity, at):
    """Accept history or an already-selected snapshot for legacy helper callers."""
    if isinstance(staff, EmployeeHistory):
        return staff.employee_at(identity, at)
    employee = staff.get(identity)
    return employee if employee and at and employee['recorded_at'] <= at else None


@lru_cache(maxsize=100000)
def bank_token(value):
    text = str(value or '').strip().upper().replace('Đ', 'D')
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^A-Z0-9]', '', text)


@lru_cache(maxsize=100000)
def bank_identity(account, code=''):
    """Institution plus account, retaining leading zeros; no master inference."""
    number, bank = bank_token(account), bank_token(code)
    if not number:
        return ''
    if bank:
        return f'B{len(bank)}C{bank}A{number}'
    # The generator guarantees globally unique accounts in this namespace.
    return number if number.startswith('BANKSYN') else ''


class ObservedVersions:
    """Retain the latest known revision per source ID, including pending events.

    Different source IDs coexist. A late observation of an older effective
    change must not replace a newer effective change for the same vendor.
    """
    def __init__(self, rows, id_field):
        self.rows = sorted(rows, key=lambda r: (r['observed_at'], r[id_field]))
        self.id_field, self.index = id_field, 0
        self.known = defaultdict(dict)

    def advance(self, now):
        while self.index < len(self.rows) and self.rows[self.index]['observed_at'] <= now:
            row = self.rows[self.index]
            key = (row['company_id'], row.get('vendor_id') or row.get('employee_id') or None)
            identity = row[self.id_field]
            if not identity:
                raise ValueError(f'Empty source ID: {self.id_field}')
            old = self.known[key].get(identity)
            if old and old['observed_at'] == row['observed_at'] and old != row:
                raise ValueError(f'Conflicting source revisions: {identity}')
            self.known[key][identity] = row
            self.index += 1

    def records(self, company, entity):
        return self.known.get((company, entity), {}).values()


class BankChangeHistory(ObservedVersions):
    def __init__(self, rows):
        rows = validated_rows('bank_account_changes', rows)
        bindings = {}
        for row in rows:
            key = row['company_id'], row['change_id']
            signature = (row['vendor_id'], bank_token(row.get('old_account')),
                         bank_token(row.get('old_bank_code')), bank_token(row.get('new_account')),
                         bank_token(row.get('new_bank_code')), row['effective_at'])
            if key in bindings and bindings[key] != signature:
                raise ValueError(f'Bank change binding changed: {key}')
            bindings[key] = signature
        super().__init__(rows, 'change_id')

    def current(self, company, vendor, now):
        active = [row for row in self.records(company, vendor)
                  if row['effective_at'] <= now and row.get('status', 'active') not in {'cancelled', 'revoked'}]
        return max(active, key=lambda r: (r['effective_at'], r['observed_at'], r['change_id']), default=None)


def bank_change_evidence(change, row, staff, now, days=14):
    """A callback belongs to one immutable change and its exact bank account."""
    result = dict(recent=False, verified=False, evidence_status='not_applicable')
    if change is not None:
        change = validated_record('bank_account_changes', change)
    if (not change or change['company_id'] != row['company_id']
            or change['vendor_id'] != row['vendor_id']):
        return result
    recent = (change['observed_at'] <= now and change['effective_at'] <= now and
              0 <= (parse(now)-parse(change['effective_at'])).total_seconds() <= days*86400)
    number = bank_token(change['new_account'])
    if not recent or not number or bank_token(row['recipient_account']) != number:
        return result
    expected = bank_identity(change['new_account'], change.get('new_bank_code', ''))
    actual = bank_identity(row['recipient_account'], row.get('recipient_bank_code', ''))
    result.update(change_bank_identity=expected, recipient_identity=actual)
    if not expected or not actual:
        result.update(evidence_status='information_gap', missing_fields=[
            field for field, identity in (('new_bank_code', expected), ('recipient_bank_code', actual))
            if not identity])
        return result
    if expected != actual:
        return result
    verified_at = change.get('verified_at', '')
    verifier = employee_at(staff, change.get('approver_id'), verified_at)
    verified = bool(flag(change.get('callback_verified', 0)) and verified_at and
                    verified_at <= change['observed_at'] <= now and verifier and verifier['company_id'] == row['company_id'] and
                    verifier['recorded_at'] <= verified_at and change['approver_id'] != row['creator_id'])
    result.update(recent=True, verified=verified, evidence_status='confirmed_bank_identity',
                  callback_binding=dict(change_id=change['change_id'], vendor_id=change['vendor_id'],
                                        bank_identity=expected) if verified else None)
    return result


def bank_change_state(change, row, staff, now, days=14):
    result = bank_change_evidence(change, row, staff, now, days)
    return result['recent'], result['verified']


def approved_evidence(record, staff, company, now):
    try:
        on_file = flag(record.get('evidence_on_file', 0))
    except ValueError as error:
        raise ValueError(f'Invalid evidence_on_file: {error}') from error
    approved_at = record.get('approved_at', '')
    approver = employee_at(staff, record.get('approver_id'), approved_at)
    return bool(record.get('company_id') == company and record.get('status') == 'approved' and on_file and
                record.get('evidence_id') and approved_at and
                approved_at <= record['observed_at'] <= now and approver and
                approver['company_id'] == company and approver['recorded_at'] <= approved_at)


def paid_leave_entitlement(records, row, staff, now):
    """Require explicit approval covering this period and this payment amount.

    A monthly leave count or a leave-type string alone grants no exemption.
    entitled_amount_vnd is an approved payable amount, not an inferred salary.
    """
    employee = employee_at(staff, row['employee_id'], now)
    if not employee or not flag(employee.get('contract_on_file', 0)):
        return None
    for record in sorted(records, key=lambda r: r['observed_at'], reverse=True):
        record = validated_record('payroll_entitlements', record)
        if (record.get('payroll_period') == row['payroll_period'] and
                record.get('leave_type') == 'paid_leave' and
                record.get('approver_id') != row['employee_id'] and
                approved_evidence(record, staff, row['company_id'], now) and
                0 < int(record.get('required_work_days', 0)) <= int(record.get('approved_paid_leave_days', 0)) <= 31 and
                0 < int(row['amount_vnd']) <= int(record.get('entitled_amount_vnd', 0))):
            return record
    return None
