"""Reproduced business regressions for B7/E1/A2 on raw, causal records."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


def hits(result, row, code):
    return [r for r in result['hits'] if r['transaction_id'] == row['transaction_id'] and r['rule_id'] == code]


def active(result, row, code):
    return any(r['points'] > 0 for r in hits(result, row, code))


class RuleRepairsTest(unittest.TestCase):
    def test_b7_pending_change_activates_without_seeing_future_effective_date(self):
        c = Case()
        after = c.change(scheduled=True)
        event = c.tables['bank_account_changes'][0]
        before = c.pay(c.at-timedelta(days=6), 50_000_000, recipient_account=event['new_account'])
        result = c.score()
        features = {r['transaction_id']: r for r in c.features}
        self.assertFalse(active(result, before, 'B7'))
        self.assertEqual(features[before['transaction_id']]['bank_changed_recently'], 0)
        self.assertTrue(active(result, after, 'B7'))
        self.assertEqual(features[after['transaction_id']]['bank_changed_recently'], 1)

    def test_b7_pending_new_change_does_not_hide_active_previous_change(self):
        c = Case()
        row = c.change()
        earlier = c.tables['bank_account_changes'][0]
        c.tables['bank_account_changes'].append(dict(earlier, change_id='LATER_CHANGE',
            observed_at=stamp(c.at-timedelta(days=1)), effective_at=stamp(c.at+timedelta(days=2)),
            new_account='LATER_BANK'))
        result = c.score()
        self.assertTrue(active(result, row, 'B7'))
        self.assertEqual(hits(result, row, 'B7')[0]['evidence']['change_id'], earlier['change_id'])
        self.assertEqual(c.features[-1]['bank_changed_recently'], 1)

    def test_b7_late_observation_of_older_change_cannot_replace_newer_effective_change(self):
        c = Case()
        row = c.change()
        current = c.tables['bank_account_changes'][0]
        c.tables['bank_account_changes'].append(dict(current, change_id='OLD_CHANGE',
            observed_at=stamp(c.at-timedelta(days=1)), effective_at=stamp(c.at-timedelta(days=9)),
            new_account='OLD_BANK'))
        result = c.score()
        self.assertTrue(active(result, row, 'B7'))
        self.assertEqual(c.features[-1]['bank_changed_recently'], 1)

    def test_b7_callback_revision_is_applied_only_when_observed(self):
        c = Case()
        first = c.change()
        second = c.pay(c.at+timedelta(days=1), 50_000_000, recipient_account='AUDIT_NEW_BANK')
        original = c.tables['bank_account_changes'][0]
        c.tables['bank_account_changes'].append(dict(original, callback_verified=1,
            verified_at=stamp(c.at+timedelta(hours=1)), observed_at=stamp(c.at+timedelta(hours=2)),
            approver_id=c.director['employee_id']))
        result = c.score()
        self.assertTrue(active(result, first, 'B7'))
        self.assertFalse(active(result, second, 'B7'))
        suppressed = hits(result, second, 'B7')[0]
        self.assertEqual((suppressed['points'], suppressed['hard_trigger']), (0, 0))
        self.assertEqual([f['bank_change_verified'] for f in c.features], [0, 1])

    def test_b7_future_record_does_not_change_past_features_or_alerts(self):
        c = Case()
        c.change()
        original = copy.deepcopy(c)
        event = c.tables['bank_account_changes'][0]
        c.tables['bank_account_changes'].append(dict(event, change_id='FUTURE',
            observed_at=stamp(c.at+timedelta(days=1)), effective_at=stamp(c.at-timedelta(days=1)),
            new_account='FUTURE_BANK'))
        self.assertEqual(c.score(), original.score())
        self.assertEqual(c.features, original.features)

    def test_b7_callback_by_maker_is_not_an_exception(self):
        c = Case()
        row = c.change(verified=True)
        c.tables['bank_account_changes'][0]['approver_id'] = c.maker['employee_id']
        result = c.score()
        self.assertTrue(active(result, row, 'B7'))
        self.assertEqual(c.features[-1]['bank_change_verified'], 0)

    def test_b7_exact_14_day_boundary(self):
        for extra, expected in ((0, True), (1, False)):
            with self.subTest(extra_seconds=extra):
                c = Case()
                row = c.change()
                event = c.tables['bank_account_changes'][0]
                event.update(effective_at=stamp(c.at-timedelta(days=14, seconds=extra)),
                             observed_at=stamp(c.at-timedelta(days=15)))
                self.assertEqual(active(c.score(), row, 'B7'), expected)
                self.assertEqual(c.features[-1]['bank_changed_recently'], int(expected))

    def test_e1_documented_full_period_paid_leave_is_suppressed(self):
        c = Case()
        row = c.attendance(leave=22)
        result = c.score()
        hit = hits(result, row, 'E1')[0]
        self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0))
        self.assertEqual(hit['evidence']['paid_leave_entitlement']['evidence_id'], 'HR_APPROVED_PAYROLL_202508')

    def test_e1_monthly_leave_count_and_type_alone_do_not_grant_pay(self):
        c = Case()
        row = c.attendance(leave=22)
        c.tables['payroll_entitlements'] = []
        self.assertTrue(active(c.score(), row, 'E1'))

    def test_e1_invalid_entitlement_cannot_hide_zero_attendance_payroll(self):
        for field, value in [('status', 'revoked'), ('payroll_period', '2025-07'),
                             ('approved_paid_leave_days', 10), ('entitled_amount_vnd', 1),
                             ('evidence_id', ''), ('evidence_on_file', 0),
                             ('leave_type', 'unpaid_leave'), ('approver_id', 'UNKNOWN')]:
            with self.subTest(field=field):
                c = Case()
                row = c.attendance(leave=22)
                c.tables['payroll_entitlements'][0][field] = value
                self.assertTrue(active(c.score(), row, 'E1'))

    def test_e1_future_leave_approval_does_not_change_past_result(self):
        c = Case()
        row = c.attendance(leave=22)
        c.tables['payroll_entitlements'][0]['observed_at'] = stamp(c.at+timedelta(days=1))
        without = copy.deepcopy(c)
        without.tables['payroll_entitlements'] = []
        self.assertEqual(c.score(), without.score())
        self.assertTrue(active(c.score(), row, 'E1'))

    def test_e1_revocation_revision_does_not_revoke_past_valid_exception(self):
        c = Case()
        first = c.attendance(leave=22)
        second = c.pay(c.at+timedelta(days=1), kind='payroll')
        second['amount_vnd'] = first['amount_vnd']
        entitlement = c.tables['payroll_entitlements'][0]
        c.tables['payroll_entitlements'].append(dict(entitlement, status='revoked',
            observed_at=stamp(c.at+timedelta(hours=1))))
        result = c.score()
        self.assertFalse(active(result, first, 'E1'))
        self.assertTrue(active(result, second, 'E1'))

    def test_e1_missing_or_future_attendance_is_unknown_not_zero_days(self):
        for future in (False, True):
            with self.subTest(future=future):
                c = Case()
                row = c.attendance()
                records = [r for r in c.tables['attendance'] if r['employee_id'] == c.worker['employee_id']
                           and r['payroll_period'] == row['payroll_period']]
                if future:
                    records[0]['observed_at'] = stamp(c.at+timedelta(days=1))
                else:
                    c.tables['attendance'].remove(records[0])
                self.assertFalse(active(c.score(), row, 'E1'))
                self.assertEqual(c.features[-1]['attendance_known'], 0)

    def test_e1_remote_exception_and_ghost_signal_remain_distinct(self):
        for alternative, expected in ((1, False), (0, True)):
            c = Case()
            row = c.attendance(alternative=alternative)
            self.assertEqual(active(c.score(), row, 'E1'), expected)

    def test_a2_seven_day_installments_are_exempt(self):
        c = Case()
        row = c.sequence([9_000_000]*3, days=7, invoice_number='ONE', invoice_gross_vnd=27_000_000)
        result = c.score()
        self.assertFalse(active(result, row, 'A2'))
        self.assertFalse(active(result, row, 'P1'))
        self.assertEqual(hits(result, row, 'A2')[0]['evidence']['installment_check']['cumulative_paid_vnd'], 27_000_000)

    def test_a2_independent_invoices_or_contract_id_alone_do_not_grant_exception(self):
        for contract in ('', 'UNVERIFIED_CONTRACT'):
            c = Case()
            row = c.sequence([9_000_000]*3, days=7, invoice_gross_vnd=27_000_000, contract_id=contract)
            self.assertTrue(active(c.score(), row, 'A2'))

    def test_a2_interleaved_independent_invoice_does_not_break_valid_installments(self):
        c = Case()
        unrelated = c.pay(c.at-timedelta(days=2), 9_000_000, invoice_number='UNRELATED')
        row = c.sequence([9_000_000]*3, days=7, invoice_number='ONE', invoice_gross_vnd=27_000_000)
        result = c.score()
        self.assertFalse(active(result, row, 'A2'))
        evidence = hits(result, row, 'A2')[0]['evidence']['installment_check']
        self.assertIn(unrelated['transaction_id'], evidence['other_window_ids'])
        self.assertNotIn(unrelated['transaction_id'], evidence['installment_window_ids'])

    def test_a2_interleaved_other_invoice_is_not_itself_called_an_installment(self):
        c = Case()
        c.sequence([9_000_000]*2, days=7, invoice_number='ONE', invoice_gross_vnd=27_000_000)
        row = c.pay(c.at+timedelta(days=14), 9_000_000, invoice_number='INDEPENDENT', invoice_gross_vnd=27_000_000)
        self.assertTrue(active(c.score(), row, 'A2'))

    def test_a2_all_time_payments_outside_window_still_constrain_gross(self):
        c = Case()
        c.pay(c.at-timedelta(days=60), 9_000_000, invoice_number='ONE', invoice_gross_vnd=27_000_000)
        row = c.sequence([9_000_000]*3, days=7, invoice_number='ONE', invoice_gross_vnd=27_000_000)
        result = c.score()
        self.assertTrue(active(result, row, 'A2'))
        self.assertTrue(active(result, row, 'P1'))

    def test_a2_duplicate_full_invoice_payment_still_triggers_p1(self):
        c = Case()
        row = c.sequence([9_000_000]*3, days=7, invoice_number='ONE', invoice_gross_vnd=9_000_000)
        result = c.score()
        self.assertTrue(active(result, row, 'A2'))
        self.assertTrue(active(result, row, 'P1'))

    def test_a2_missing_documents_blank_invoice_and_inflated_gross_not_exempt(self):
        for change in ('documents', 'number', 'gross', 'future_document'):
            with self.subTest(change=change):
                c = Case()
                row = c.sequence([9_000_000]*3, days=7, invoice_number='ONE', invoice_gross_vnd=27_000_000)
                if change == 'documents':
                    c.rows[0]['support_doc_count'] = 0
                elif change == 'number':
                    for payment in c.rows:
                        payment['invoice_number'] = ''
                elif change == 'gross':
                    c.rows[0]['invoice_gross_vnd'] = 9_000_000
                else:
                    c.rows[0]['support_docs_observed_at'] = stamp(c.at+timedelta(days=20))
                self.assertTrue(active(c.score(), row, 'A2'))

    def agreement(self, c, total=27_000_000):
        c.tables['supplier_payment_agreements'].append(dict(agreement_id='AGREEMENT',
            company_id='C001', vendor_id=c.vendor['vendor_id'], contract_id='CONTRACT',
            total_vnd=total, status='approved', evidence_on_file=1, evidence_id='APPROVED_SCHEDULE',
            approver_id=c.director['employee_id'], approved_at=stamp(c.at-timedelta(days=2)),
            observed_at=stamp(c.at-timedelta(days=1))))

    def test_a2_documented_contract_covers_distinct_invoices(self):
        c = Case()
        self.agreement(c)
        row = c.sequence([9_000_000]*3, days=7, contract_id='CONTRACT')
        result = c.score()
        self.assertFalse(active(result, row, 'A2'))
        self.assertEqual(hits(result, row, 'A2')[0]['evidence']['installment_check']['basis'], 'contract')

    def test_a2_contract_cannot_override_invoice_overpayment(self):
        c = Case()
        self.agreement(c)
        row = c.sequence([9_000_000]*3, days=7, contract_id='CONTRACT', invoice_number='ONE')
        result = c.score()
        self.assertTrue(active(result, row, 'A2'))
        self.assertTrue(active(result, row, 'P1'))

    def test_a2_unobserved_agreement_or_all_time_contract_excess_is_not_exempt(self):
        for mode in ('future', 'excess'):
            with self.subTest(mode=mode):
                c = Case()
                self.agreement(c)
                if mode == 'future':
                    c.tables['supplier_payment_agreements'][0]['observed_at'] = stamp(c.at+timedelta(days=20))
                else:
                    c.pay(c.at-timedelta(days=60), 9_000_000, contract_id='CONTRACT')
                row = c.sequence([9_000_000]*3, days=7, contract_id='CONTRACT')
                self.assertTrue(active(c.score(), row, 'A2'))


if __name__ == '__main__':
    unittest.main()
