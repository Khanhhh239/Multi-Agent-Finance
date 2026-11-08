"""Independent business controls for the declared phase 3 definitions."""
import unittest
from datetime import datetime, timedelta

from sme_fraud.generate import TZ, stamp
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import score_rules


class SpecPolicyTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3'}
        return case

    def hit(self, result, row, code):
        return next((h for h in result['hits'] if h['transaction_id'] == row['transaction_id'] and h['rule_id'] == code), None)

    def approved(self, c, **values):
        return dict(company_id='C001', status='approved', evidence_on_file=1, evidence_id='SOURCE',
                    approver_id=c.director['employee_id'], approved_at=stamp(c.at-timedelta(days=7)),
                    observed_at=stamp(c.at-timedelta(days=6)), **values)

    def test_a3_short_branch_and_exact_three_day_boundary(self):
        for days, expected in [(3, True), (4, False)]:
            c = self.case()
            row = c.sequence([8_000_000, 9_000_000], vendors=c.shared_vendors()[:2], days=days)
            hit = self.hit(c.score(), row, 'A3')
            self.assertEqual(bool(hit), expected)
            if hit:
                self.assertEqual(hit['evidence']['branch'], 'short_2_85pct')
                self.assertEqual(hit['points'], 8)

    def test_a3_below_total_limit_and_address_only_do_not_group(self):
        for amounts, field in [([7_000_000, 9_000_000], 'phone'), ([9_000_000]*3, 'address')]:
            c = self.case()
            row = c.sequence(amounts, vendors=c.shared_vendors(field)[:len(amounts)])
            self.assertIsNone(self.hit(c.score(), row, 'A3'))

    def test_a3_long_branch_remains(self):
        c = self.case()
        row = c.sequence([9_000_000]*3, days=10, vendors=c.shared_vendors())
        self.assertEqual(self.hit(c.score(), row, 'A3')['evidence']['branch'], 'long_3_100pct')

    def test_a4_calendar_month_and_explicit_rolling_option(self):
        for period, expected in [('calendar_month', False), ('rolling_30d', True)]:
            c = self.case()
            c.config['near_period'] = period
            row = c.sequence([17_000_000]*3, kind='cash_expense', start=datetime(2025, 1, 31, 11, tzinfo=TZ))
            self.assertEqual(bool(self.hit(c.score(), row, 'A4')), expected)

    def test_a4_last_day_of_31_day_month_keeps_first_day(self):
        c = self.case()
        c.pay(datetime(2025, 8, 1, 1, tzinfo=TZ), 17_000_000, kind='cash_expense')
        c.pay(datetime(2025, 8, 15, 11, tzinfo=TZ), 17_000_000, kind='cash_expense')
        row = c.pay(datetime(2025, 8, 31, 23, tzinfo=TZ), 17_000_000, kind='cash_expense')
        self.assertEqual(self.hit(c.score(), row, 'A4')['evidence']['count'], 3)

    def test_a4_known_payroll_entitlement_excludes_only_budgeted_payment(self):
        c = self.case()
        c.worker['monthly_salary_vnd'] = 17_000_000
        c.tables['payroll_entitlements'] = [self.approved(c, entitlement_id='PAYROLL',
            employee_id=c.worker['employee_id'], payroll_period='2025-08', leave_type='regular_payroll', entitled_amount_vnd=17_000_000)]
        c.pay(kind='payroll')
        c.pay(c.at+timedelta(days=1), 17_000_000, kind='cash_expense')
        row = c.pay(c.at+timedelta(days=2), 17_000_000, kind='cash_expense')
        self.assertIsNone(self.hit(c.score(), row, 'A4'))

    def test_a4_repeated_payroll_cannot_reuse_one_entitlement(self):
        c = self.case()
        c.worker['monthly_salary_vnd'] = 17_000_000
        c.tables['payroll_entitlements'] = [self.approved(c, entitlement_id='PAYROLL', employee_id=c.worker['employee_id'],
            payroll_period='2025-08', leave_type='regular_payroll', entitled_amount_vnd=17_000_000)]
        row = c.sequence([17_000_000]*4, kind='payroll')
        self.assertEqual(self.hit(c.score(), row, 'A4')['evidence']['count'], 3)

    def recurring(self, c):
        return self.approved(c, pattern_id='RENT', vendor_id=c.vendor['vendor_id'], txn_type='rent',
            frequency='monthly', expected_amount_vnd=17_000_000, tolerance_vnd=0,
            effective_from='2025-01-01', effective_to='2025-12-31')

    def test_a4_recurring_exception_is_specific_and_does_not_cover_extra_payments(self):
        c = self.case()
        c.tables['recurring_payments'] = [self.recurring(c)]
        row = c.sequence([17_000_000]*4, kind='rent')
        self.assertEqual(self.hit(c.score(), row, 'A4')['evidence']['count'], 3)

    def test_a4_simultaneous_payments_cannot_each_reuse_same_monthly_budget(self):
        c = self.case()
        c.tables['recurring_payments'] = [self.recurring(c)]
        c.pay(kind='rent', amount=17_000_000)
        c.pay(kind='rent', amount=17_000_000)
        row = c.pay(c.at+timedelta(days=1), kind='rent', amount=17_000_000)
        self.assertEqual(self.hit(c.score(), row, 'A4')['evidence']['count'], 3)

    def test_a5_lower_tail_is_out_of_scope(self):
        c = self.case()
        c.sequence([3_000_000+(i%5-2)*10_000 for i in range(25)], kind='cash_expense', start=c.at-timedelta(days=30))
        row = c.pay(amount=100_000, kind='cash_expense')
        self.assertIsNone(self.hit(c.score(), row, 'A5'))

    def test_a5_upper_tail_retained_and_two_sided_rejected(self):
        c = self.case()
        c.sequence([1_000_000+(i%5-2)*10_000 for i in range(25)], kind='cash_expense', start=c.at-timedelta(days=30))
        row = c.pay(amount=3_000_000, kind='cash_expense')
        self.assertEqual(self.hit(c.score(), row, 'A5')['evidence']['tail'], 'upper')
        with self.assertRaises(ValueError):
            score_rules(c.tables, features=c.features, config={'amount_tail': 'two_sided'})

    def test_b1_rent_and_selling_expenses_are_vendor_outflows(self):
        for kind in ('rent', 'selling_expense', 'vendor_payment'):
            c = self.case()
            row = c.pay(kind=kind, recipient_account=c.worker['bank_account'])
            hit = self.hit(c.score(), row, 'B1')
            self.assertIsNotNone(hit, kind)
            self.assertEqual(hit['hard_trigger'], 1)

    def test_b1_master_overlap_is_reported_without_cash_payment(self):
        c = self.case()
        c.vendor['bank_account'] = c.worker['bank_account']
        row = c.pay(kind='stock_purchase')
        result = c.score()
        self.assertTrue(any(h['evidence']['vendor_id'] == c.vendor['vendor_id'] for h in result['master_identity_findings']))
        self.assertIsNone(self.hit(result, row, 'B1'))

    def test_b1_existing_vendor_is_rechecked_when_employee_becomes_observed(self):
        c = self.case()
        c.vendor['bank_account'] = c.worker['bank_account']
        c.worker['recorded_at'] = stamp(c.at+timedelta(days=1))
        first = c.pay(kind='stock_purchase')
        second = c.pay(c.at+timedelta(days=2), kind='stock_purchase')
        findings = [h for h in c.score()['master_identity_findings'] if h['evidence']['vendor_id'] == c.vendor['vendor_id']]
        self.assertTrue(findings)
        self.assertTrue(all(h['observed_at'] == second['posted_at'] for h in findings))
        self.assertTrue(all(h['observed_at'] > first['posted_at'] for h in findings))

    def test_b1_bank_institution_distinguishes_identical_account_numbers(self):
        for code, expected in [('BANK_A', True), ('BANK_B', False), ('', False)]:
            c = self.case()
            c.worker.update(bank_account='001234567', bank_code='BANK_A')
            row = c.pay(recipient_account='001234567', recipient_bank_code=code)
            hit = self.hit(c.score(), row, 'B1')
            self.assertEqual(bool(hit and hit['hard_trigger']), expected)
            if not code:
                self.assertEqual(hit['evidence']['evidence_status'], 'bank_institution_missing')

    def test_b1_cccd_with_leading_zero_is_supported_only_on_outflow(self):
        for kind, expected in [('vendor_payment', True), ('stock_purchase', False)]:
            c = self.case()
            c.worker['national_id'] = '001234567890'
            c.vendor['national_id'] = '001 234 567 890'
            row = c.pay(kind=kind)
            self.assertEqual(bool(self.hit(c.score(), row, 'B1')), expected)

    def test_b3_purchase_precedes_payment_so_payment_is_not_first_economic_entry(self):
        c = self.case()
        c.new_vendor()
        c.pay(c.at-timedelta(days=1), 1_000_000, kind='stock_purchase')
        row = c.pay(amount=30_000_000)
        self.assertIsNone(self.hit(c.score(), row, 'B3'))

    def test_b3_first_large_purchase_is_candidate(self):
        c = self.case()
        c.new_vendor()
        row = c.pay(kind='stock_purchase', amount=30_000_000)
        self.assertEqual(self.hit(c.score(), row, 'B3')['evidence']['first_basis'], 'observed_economic_entry')

    def test_b3_same_time_entries_are_co_first_without_id_order_leakage(self):
        c = self.case()
        c.new_vendor()
        small = c.pay(kind='stock_purchase', amount=1_000_000)
        large = c.pay(amount=30_000_000)
        result = c.score()
        self.assertIsNone(self.hit(result, small, 'B3'))
        self.assertIsNotNone(self.hit(result, large, 'B3'))

    def manual(self, c, row, close=None):
        close = close or c.at+timedelta(days=2)
        c.tables['journal_audit_log'] = [dict(audit_id='LOG', company_id='C001', employee_id=c.maker['employee_id'],
            transaction_id=row['transaction_id'], entry_origin='manual', entered_at=row['created_at'], observed_at=row['posted_at'], evidence_id='AUDIT_TRAIL')]
        c.tables['closing_periods'] = [self.approved(c, closing_id='CLOSE', period_start='2025-08-01', period_end='2025-08-31', closing_at=stamp(close))]
        c.tables['materiality_policies'] = [self.approved(c, policy_id='MATERIAL', effective_from='2025-01-01', effective_to='2025-12-31', materiality_vnd=2_000_000)]

    def test_f1_authoritative_sources_override_creator_limit_and_calendar_proxy(self):
        c = self.case()
        row = c.pay(kind='adjustment', amount=5_000_000)
        self.manual(c, row)
        hit = self.hit(c.score(), row, 'F1')
        self.assertEqual(hit['points'], 8)
        self.assertEqual(hit['evidence']['evidence_status'], 'confirmed_sources')

    def test_f1_manual_non_adjustment_entry_is_supported(self):
        c = self.case()
        row = c.pay(kind='stock_purchase', amount=5_000_000)
        self.manual(c, row)
        self.assertEqual(self.hit(c.score(), row, 'F1')['points'], 8)

    def test_f1_unconfirmed_month_end_proxy_never_contributes(self):
        c = self.case()
        row = c.pay(c.at.replace(day=29), 50_000_000, kind='adjustment')
        hit = self.hit(c.score(), row, 'F1')
        self.assertEqual(hit['points'], 0)
        self.assertEqual(hit['evidence']['evidence_status'], 'unconfirmed_proxy')

    def test_f1_missing_unapproved_late_or_automatic_sources_do_not_confirm(self):
        for source, field, value in [('materiality_policies', 'status', 'draft'),
                                     ('closing_periods', 'observed_at', '2025-09-01T00:00:00+07:00'),
                                     ('journal_audit_log', 'entry_origin', 'automatic'),
                                     ('materiality_policies', 'company_id', 'C002')]:
            c = self.case()
            row = c.pay(kind='adjustment', amount=5_000_000)
            self.manual(c, row)
            c.tables[source][0][field] = value
            self.assertIsNone(self.hit(c.score(), row, 'F1'), (source, field))

    def test_f1_materiality_equality_and_outside_close_window(self):
        for amount, delta in [(2_000_000, 2), (5_000_000, 10), (5_000_000, -2)]:
            c = self.case()
            row = c.pay(kind='adjustment', amount=amount)
            self.manual(c, row, close=c.at+timedelta(days=delta))
            self.assertIsNone(self.hit(c.score(), row, 'F1'))

    def test_f1_revocation_revision_supersedes_prior_approval(self):
        c = self.case()
        row = c.pay(kind='adjustment', amount=5_000_000)
        self.manual(c, row)
        c.tables['materiality_policies'].append({**c.tables['materiality_policies'][0], 'status': 'revoked', 'observed_at': row['posted_at']})
        self.assertIsNone(self.hit(c.score(), row, 'F1'))

    def test_future_evidence_does_not_rewrite_past_scores(self):
        c = self.case()
        row = c.pay(kind='adjustment', amount=5_000_000)
        before = c.score()
        self.manual(c, row)
        for name in ('journal_audit_log', 'closing_periods', 'materiality_policies'):
            c.tables[name][0]['observed_at'] = stamp(c.at+timedelta(days=1))
        after = score_rules(c.tables, features=c.features, config=c.config)
        self.assertEqual(before['scores'], after['scores'])


if __name__ == '__main__':
    unittest.main()
