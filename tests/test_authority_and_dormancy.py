"""Explicit authority controls for C2/C3 and seasonal/annual evidence for B6."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


class AuthorityAndDormancyTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3'}
        return case

    @staticmethod
    def hit(result, row, rule):
        return next((hit for hit in result['hits']
                     if hit['transaction_id'] == row['transaction_id'] and hit['rule_id'] == rule), None)

    def coverage(self, case, actions='self_approve,approve', *, offset=0, status='approved'):
        case.tables['approval_authority_coverage'].append(dict(
            coverage_id='COVERAGE', company_id='C001', covered_actions=actions,
            covered_from='2025-01-01', covered_through='2025-12-31', status=status,
            evidence_on_file=1, evidence_id='AUTH_MATRIX',
            approver_id=case.director['employee_id'],
            approved_at=stamp(case.at + timedelta(days=offset-5)),
            observed_at=stamp(case.at + timedelta(days=offset-4))))

    def authority(self, case, subject, action, *, maximum=100_000_000,
                  self_allowed=0, level='standard', authority_type='policy',
                  delegated_by='', status='approved', offset=0, txn_type='*'):
        approving_employee = next(row for row in case.tables['employees']
                                  if row['employee_id'] not in {subject, case.maker['employee_id']})
        if subject != case.maker['employee_id']:
            approving_employee = case.maker
        case.tables['approval_authorities'].append(dict(
            authority_id=f'AUTH_{len(case.tables["approval_authorities"])}',
            company_id='C001', subject_employee_id=subject, subject_role='', action=action,
            txn_type=txn_type, department='', project_id='', min_amount_vnd=0,
            max_amount_vnd=maximum, self_approval_allowed=self_allowed,
            authority_level=level, authority_type=authority_type,
            delegated_by_id=delegated_by, effective_from='2025-01-01', effective_to='2025-12-31',
            status=status, evidence_on_file=1, evidence_id='AUTH_DOCUMENT',
            approver_id=approving_employee['employee_id'],
            approved_at=stamp(case.at + timedelta(days=offset-5)),
            observed_at=stamp(case.at + timedelta(days=offset-4))))

    def fast_payment(self, case, amount):
        row = case.pay(amount=amount)
        row['created_at'] = stamp(case.at - timedelta(minutes=5))
        row['approved_at'] = stamp(case.at - timedelta(minutes=4, seconds=30))
        return row

    def dormant_payment(self, case, amount=5_000_000, **values):
        start = case.at - timedelta(days=240)
        for index in range(20):
            case.pay(start + timedelta(days=index), 1_000_000)
        return case.pay(case.at, amount, **values)

    def schedule(self, case, *, kind='seasonal', start='08-01', end='08-31',
                 expected=5_000_000, partial=0, status='approved', observed_offset=-4,
                 recipient='', contract=''):
        case.tables['vendor_payment_schedules'].append(dict(
            schedule_id='SCHEDULE', company_id='C001', vendor_id=case.vendor['vendor_id'],
            txn_type='vendor_payment', schedule_type=kind, window_start_mmdd=start,
            window_end_mmdd=end, expected_amount_vnd=expected, tolerance_vnd=0,
            allow_partial=partial, effective_from='2025-01-01', effective_to='2026-12-31',
            status=status, evidence_on_file=1, evidence_id='APPROVED_SCHEDULE',
            approver_id=case.director['employee_id'], approved_at=stamp(case.at-timedelta(days=5)),
            observed_at=stamp(case.at+timedelta(days=observed_offset)), contract_id=contract,
            invoice_number='', recipient_account=recipient, recipient_bank_code=''))

    def test_c2_explicit_self_authority_overrides_lower_master_limit(self):
        case = self.case()
        row = case.pay(amount=9_000_000, approver_id=case.maker['employee_id'])
        self.coverage(case, 'self_approve')
        self.authority(case, case.maker['employee_id'], 'self_approve', maximum=10_000_000,
                       self_allowed=1)
        hit = self.hit(case.score(), row, 'C2')
        self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0))
        self.assertEqual(hit['evidence']['authority_check']['authority_id'], 'AUTH_0')

    def test_c2_complete_matrix_denies_missing_or_disallowed_authority(self):
        for authority_present in (False, True):
            with self.subTest(authority_present=authority_present):
                case = self.case()
                row = case.pay(amount=1_000_000, approver_id=case.maker['employee_id'])
                self.coverage(case, 'self_approve')
                if authority_present:
                    self.authority(case, case.maker['employee_id'], 'self_approve', self_allowed=0)
                hit = self.hit(case.score(), row, 'C2')
                self.assertEqual((hit['points'], hit['hard_trigger']), (20, 1))
                self.assertFalse(hit['suppressed_reason'])

    def test_c2_overlapping_complete_coverage_cannot_grant_an_exception(self):
        case = self.case()
        row = case.pay(amount=1_000_000, approver_id=case.maker['employee_id'])
        self.coverage(case, 'self_approve')
        case.tables['approval_authority_coverage'].append(dict(
            case.tables['approval_authority_coverage'][0], coverage_id='COVERAGE_2',
            evidence_id='AUTH_MATRIX_2'))
        self.authority(case, case.maker['employee_id'], 'self_approve', self_allowed=1)
        hit = self.hit(case.score(), row, 'C2')
        self.assertEqual((hit['points'], hit['hard_trigger']), (20, 1))
        self.assertEqual(hit['evidence']['authority_check']['status'], 'ambiguous_coverage')

    def test_c2_approved_delegation_is_scoped_and_independent(self):
        case = self.case()
        row = case.pay(amount=5_000_000, approver_id=case.maker['employee_id'])
        self.coverage(case, 'self_approve')
        self.authority(case, case.maker['employee_id'], 'self_approve', maximum=5_000_000,
                       self_allowed=1, authority_type='delegation',
                       delegated_by=case.director['employee_id'], txn_type='vendor_payment')
        hit = self.hit(case.score(), row, 'C2')
        self.assertEqual(hit['points'], 0)
        self.assertEqual(hit['evidence']['authority_check']['authority_type'], 'delegation')

    def test_c2_future_matrix_does_not_rewrite_legacy_exception(self):
        case = self.case()
        row = case.pay(amount=1_000_000, approver_id=case.maker['employee_id'])
        before = copy.deepcopy(case.score())
        self.coverage(case, 'self_approve', offset=30)
        self.authority(case, case.maker['employee_id'], 'self_approve', self_allowed=0, offset=30)
        self.assertEqual(case.score(), before)
        self.assertEqual(self.hit(before, row, 'C2')['points'], 0)

    def test_c3_uses_explicit_high_authority_even_below_amount_proxy(self):
        case = self.case()
        row = self.fast_payment(case, 1_000_000)
        self.coverage(case, 'approve')
        self.authority(case, case.director['employee_id'], 'approve', level='high')
        hit = self.hit(case.score(), row, 'C3')
        self.assertEqual(hit['points'], 8)
        self.assertEqual(hit['evidence']['authority_basis'], 'explicit_matrix')

    def test_c3_standard_authority_is_not_promoted_by_large_amount(self):
        case = self.case()
        row = self.fast_payment(case, 60_000_000)
        self.coverage(case, 'approve')
        self.authority(case, case.director['employee_id'], 'approve', level='standard')
        self.assertIsNone(self.hit(case.score(), row, 'C3'))

    def test_c3_missing_matrix_keeps_amount_proxy(self):
        case = self.case()
        row = self.fast_payment(case, 60_000_000)
        hit = self.hit(case.score(), row, 'C3')
        self.assertEqual(hit['points'], 8)
        self.assertEqual(hit['evidence']['authority_basis'], 'amount_proxy')

    def test_b6_approved_seasonal_or_annual_schedule_suppresses(self):
        for kind in ('seasonal', 'annual'):
            with self.subTest(kind=kind):
                case = self.case()
                row = self.dormant_payment(case)
                self.schedule(case, kind=kind)
                hit = self.hit(case.score(), row, 'B6')
                self.assertEqual(hit['points'], 0)
                self.assertEqual(hit['evidence']['payment_schedule']['schedule_type'], kind)

    def test_b6_wrong_window_future_or_excess_schedule_does_not_suppress(self):
        for mode in ('window', 'future', 'excess', 'contract', 'recipient'):
            with self.subTest(mode=mode):
                case = self.case()
                row = self.dormant_payment(case)
                values = dict(start='02-01', end='02-28') if mode == 'window' else {}
                if mode == 'future':
                    values['observed_offset'] = 20
                if mode == 'excess':
                    values.update(expected=4_000_000, partial=1)
                if mode == 'contract':
                    values['contract'] = 'OTHER_CONTRACT'
                if mode == 'recipient':
                    values['recipient'] = 'BANK_SYN_WRONG'
                self.schedule(case, **values)
                self.assertEqual(self.hit(case.score(), row, 'B6')['points'], 8)

    def test_b6_existing_yearly_recurring_authority_is_supported(self):
        case = self.case()
        row = self.dormant_payment(case, contract_id='ANNUAL_CONTRACT')
        case.tables['recurring_payments'].append(dict(
            pattern_id='YEARLY', company_id='C001', vendor_id=case.vendor['vendor_id'],
            employee_id='', txn_type='vendor_payment', contract_id='ANNUAL_CONTRACT',
            invoice_number='', frequency='yearly', expected_amount_vnd=5_000_000,
            tolerance_vnd=0, allow_partial=0, effective_from='2025-01-01',
            effective_to='2025-12-31', status='approved', evidence_on_file=1,
            evidence_id='YEARLY_CONTRACT', approver_id=case.director['employee_id'],
            approved_at=stamp(case.at-timedelta(days=5)),
            observed_at=stamp(case.at-timedelta(days=4))))
        hit = self.hit(case.score(), row, 'B6')
        self.assertEqual(hit['points'], 0)
        self.assertEqual(hit['evidence']['payment_schedule']['frequency'], 'yearly')

    def test_b6_equal_time_payments_share_the_season_cap(self):
        case = self.case()
        self.dormant_payment(case, 3_000_000)
        row = case.pay(case.at, 3_000_000)
        self.schedule(case, expected=5_000_000, partial=1)
        hit = self.hit(case.score(), row, 'B6')
        self.assertEqual(hit['points'], 8)
        self.assertIsNone(hit['evidence']['payment_schedule'])


if __name__ == '__main__':
    unittest.main()
