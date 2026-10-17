"""Phase 3 business definitions; source evidence is optional, never inferred truth."""
from collections import defaultdict
import re

from .generate import parse
from .temporal_evidence import approved_evidence, bank_token, bank_identity, employee_at


def identity_matches(vendor, staff, account=None, bank_code=None):
    number = bank_token(vendor.get('bank_account') if account is None else account)
    bank = bank_identity(number, vendor.get('bank_code', '') if bank_code is None else bank_code)
    national = bank_token(vendor.get('national_id'))
    national = national if re.fullmatch(r'(?:\d{9}|\d{12})', national) else ''
    matched, ambiguous = defaultdict(list), []
    for employee_id, employee in staff.items():
        if employee['company_id'] != vendor['company_id']:
            continue
        other = bank_identity(employee.get('bank_account'), employee.get('bank_code', ''))
        if bank and other and bank == other:
            matched['bank_identity'].append(employee_id)
        elif number and number == bank_token(employee.get('bank_account')) and (not bank or not other):
            ambiguous.append(employee_id)
        if national and national == bank_token(employee.get('national_id')):
            matched['national_id'].append(employee_id)
    return dict(matched), sorted(ambiguous)


class PeriodPayments:
    """Budgeted exceptions: repeat payments cannot all claim one monthly approval."""
    def __init__(self):
        self.totals = defaultdict(int)

    @staticmethod
    def key(row):
        return (row['company_id'], row['txn_type'], row['vendor_id'] or row['employee_id'], row['posted_at'][:7])

    def exception(self, row, entitlements, recurring, staff, now):
        cumulative = self.totals[self.key(row)] + int(row['amount_vnd'])
        employee = employee_at(staff, row['employee_id'], now)
        if row['txn_type'] == 'payroll':
            for record in sorted(entitlements, key=lambda r: r['observed_at'], reverse=True):
                if (record.get('payroll_period') == row['payroll_period'] == now[:7] and
                        record.get('leave_type') in {'regular_payroll', 'paid_leave'} and
                        record.get('approver_id') != row['employee_id'] and
                        approved_evidence(record, staff, row['company_id'], now) and
                        employee and employee.get('contract_on_file') in {1, '1'} and
                        cumulative <= int(record.get('entitled_amount_vnd', 0))):
                    return record['entitlement_id']
        for record in recurring:
            if (record.get('frequency') == 'monthly' and record.get('txn_type') == row['txn_type'] and
                    record.get('effective_from', '') <= now[:10] <= record.get('effective_to', '') and
                    approved_evidence(record, staff, row['company_id'], now)):
                expected = int(record.get('expected_amount_vnd', 0))
                tolerance = int(record.get('tolerance_vnd', 0))
                if expected > 0 and tolerance >= 0 and abs(int(row['amount_vnd']) - expected) <= tolerance and cumulative <= expected + tolerance:
                    return record['pattern_id']
        return ''

    def commit(self, row):
        if int(row['is_financial_entry']) and row['payment_channel'] in {'bank', 'cash'}:
            self.totals[self.key(row)] += int(row['amount_vnd'])


def manual_close_evidence(row, audits, closings, policies, staff, now, days):
    """No adjustment/month-end/approval-limit proxy can establish this predicate."""
    cid = row['company_id']
    audits = [r for r in audits if r.get('transaction_id') == row['transaction_id'] and
              r.get('entry_origin') in {'manual', 'automatic'} and r.get('evidence_id') and
              r.get('employee_id') == row['creator_id'] and
              r.get('entered_at') and r['entered_at'] <= r['observed_at'] <= now and
              (actor := employee_at(staff, row['creator_id'], r['entered_at'])) and actor['company_id'] == cid]
    audit = max(audits, key=lambda r: (r['observed_at'], r['audit_id']), default=None)
    if not audit or audit['entry_origin'] != 'manual':
        return None
    date = row['posted_at'][:10]
    valid_closings = [r for r in closings if approved_evidence(r, staff, cid, now) and
                     r['period_start'] <= date <= r['period_end'] and r.get('closing_at')]
    # Later known revisions/replacements take precedence, not any stale approval.
    closing = max(valid_closings, key=lambda r: (r['observed_at'], r['closing_id']), default=None)
    valid_policies = [r for r in policies if approved_evidence(r, staff, cid, now) and
                      r['effective_from'] <= date <= r['effective_to'] and int(r['materiality_vnd']) > 0]
    policy = max(valid_policies, key=lambda r: (r['effective_from'], r['observed_at'], r['policy_id']), default=None)
    if not closing or not policy:
        return None
    distance = (parse(closing['closing_at']) - parse(audit['entered_at'])).total_seconds() / 86400
    if not 0 <= distance <= days or int(row['amount_vnd']) <= int(policy['materiality_vnd']):
        return None
    return dict(manual_proxy=None, evidence_status='confirmed_sources', audit_id=audit['audit_id'],
                entered_at=audit['entered_at'], closing_id=closing['closing_id'], closing_at=closing['closing_at'],
                policy_id=policy['policy_id'], materiality_vnd=int(policy['materiality_vnd']),
                days_before_close=round(distance, 4), amount_vnd=int(row['amount_vnd']),
                source_records=[dict(r) for r in (audit, closing, policy)])
