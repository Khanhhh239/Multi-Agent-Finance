"""Shared as-of source records for rules and observable bank features."""
from collections import defaultdict
import re
import unicodedata

from .generate import parse


def bank_token(value):
    text = str(value or '').strip().upper().replace('Đ', 'D')
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^A-Z0-9]', '', text)


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
            key = (row['company_id'], row.get('vendor_id') or row.get('employee_id'))
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
        super().__init__(rows, 'change_id')

    def current(self, company, vendor, now):
        active = [row for row in self.records(company, vendor)
                  if row['effective_at'] <= now and row.get('status', 'active') not in {'cancelled', 'revoked'}]
        return max(active, key=lambda r: (r['effective_at'], r['observed_at'], r['change_id']), default=None)


def bank_change_state(change, row, staff, now, days=14):
    if not change:
        return False, False
    recent = (change['observed_at'] <= now and change['effective_at'] <= now and
              0 <= (parse(now)-parse(change['effective_at'])).total_seconds() <= days*86400 and
              bool(bank_token(change['new_account'])) and
              bank_token(row['recipient_account']) == bank_token(change['new_account']))
    verifier = staff.get(change.get('approver_id'))
    verified_at = change.get('verified_at', '')
    verified = bool(recent and int(change.get('callback_verified', 0)) and verified_at and
                    verified_at <= now and verifier and verifier['company_id'] == row['company_id'] and
                    verifier['recorded_at'] <= verified_at and change['approver_id'] != row['creator_id'])
    return bool(recent), verified


def approved_evidence(record, staff, company, now):
    approver = staff.get(record.get('approver_id'))
    approved_at = record.get('approved_at', '')
    return bool(record.get('status') == 'approved' and int(record.get('evidence_on_file', 0)) and
                record.get('evidence_id') and approved_at and
                approved_at <= record['observed_at'] <= now and approver and
                approver['company_id'] == company and approver['recorded_at'] <= approved_at)


def paid_leave_entitlement(records, row, staff, now):
    """Require explicit approval covering this period and this payment amount.

    A monthly leave count or a leave-type string alone grants no exemption.
    entitled_amount_vnd is an approved payable amount, not an inferred salary.
    """
    employee = staff.get(row['employee_id'])
    if not employee or not int(employee.get('contract_on_file', 0)):
        return None
    for record in sorted(records, key=lambda r: r['observed_at'], reverse=True):
        if (record.get('payroll_period') == row['payroll_period'] and
                record.get('leave_type') == 'paid_leave' and
                record.get('approver_id') != row['employee_id'] and
                approved_evidence(record, staff, row['company_id'], now) and
                0 < int(record.get('required_work_days', 0)) <= int(record.get('approved_paid_leave_days', 0)) <= 31 and
                0 < int(row['amount_vnd']) <= int(record.get('entitled_amount_vnd', 0))):
            return record
    return None
