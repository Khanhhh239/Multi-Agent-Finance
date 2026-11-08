"""Invoice overpayment checks across payment channels and incomplete identities."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.rule_audit_cases import Case


class InvoicePaymentTest(unittest.TestCase):
    def case(self, policy='phase4'):
        case = Case()
        if policy == 'phase4':
            case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3',
                           'evidence_policy': 'phase4'}
        return case

    def pay(self, case, index, amount=9_000_000, channel='bank', **values):
        return case.pay(case.at + timedelta(days=index), amount,
                        payment_channel=channel,
                        credit_account='111' if channel == 'cash' else '112',
                        recipient_account='' if channel == 'cash' else case.vendor['bank_account'],
                        **values)

    def hits(self, result, row):
        return [hit for hit in result['hits'] if hit['rule_id'] == 'P1'
                and hit['transaction_id'] == row['transaction_id']]

    def active(self, result, row):
        return [hit for hit in self.hits(result, row) if hit['points'] > 0]

    def test_blank_invoice_numbers_are_information_gaps_not_shared_invoices(self):
        for policy in ('legacy', 'phase4'):
            for number in ('', '   ', '/ - .'):
                with self.subTest(policy=policy, number=number):
                    case = self.case(policy)
                    rows = [self.pay(case, index, invoice_number=number,
                                     invoice_gross_vnd=9_000_000) for index in range(2)]
                    result = case.score()
                    for row in rows:
                        hits = self.hits(result, row)
                        self.assertEqual(len(hits), 1)
                        self.assertEqual((hits[0]['points'], hits[0]['hard_trigger']), (0, 0))
                        self.assertEqual(hits[0]['scoring_role'], 'context')
                        self.assertEqual(hits[0]['evidence']['evidence_status'], 'information_gap')
                        self.assertIn('invoice_number', hits[0]['evidence']['missing_fields'])
                        self.assertEqual(hits[0]['related_transaction_ids'], [])

    def test_cash_overpayment_without_recipient_account_uses_all_history(self):
        for policy in ('legacy', 'phase4'):
            with self.subTest(policy=policy):
                case = self.case(policy)
                first = self.pay(case, 0, channel='cash', invoice_number='CASH_INV',
                                 invoice_gross_vnd=9_000_000)
                second = self.pay(case, 45, channel='cash', invoice_number='CASH_INV',
                                  invoice_gross_vnd=9_000_000)
                result = case.score()
                self.assertFalse(self.active(result, first))
                hit, = self.active(result, second)
                self.assertEqual((hit['points'], hit['hard_trigger']), (20, 1))
                self.assertEqual(hit['evidence']['cumulative_paid_vnd'], 18_000_000)
                self.assertEqual(hit['evidence']['excess_vnd'], 9_000_000)
                self.assertEqual(hit['related_transaction_ids'], [first['transaction_id']])

    def test_cash_and_bank_payments_consume_the_same_invoice_cap(self):
        for channels in (('cash', 'bank'), ('bank', 'cash')):
            with self.subTest(channels=channels):
                case = self.case()
                first, second = [self.pay(case, index, channel=channel,
                                         invoice_number='MIXED_INV', invoice_gross_vnd=9_000_000)
                                 for index, channel in enumerate(channels)]
                result = case.score()
                hit, = self.active(result, second)
                self.assertEqual(hit['evidence']['cumulative_paid_vnd'], 18_000_000)
                self.assertEqual(hit['related_transaction_ids'], [first['transaction_id']])

    def test_cash_installments_up_to_invoice_total_are_not_overpayments(self):
        case = self.case()
        rows = [self.pay(case, index, amount=amount, channel='cash',
                         invoice_number='INSTALLMENTS', invoice_gross_vnd=9_000_000)
                for index, amount in enumerate((4_000_000, 5_000_000))]
        result = case.score()
        self.assertTrue(all(not self.active(result, row) for row in rows))

    def test_different_vendors_do_not_share_an_invoice_cap(self):
        case = self.case()
        rows = [self.pay(case, 0, channel='cash', invoice_number='SAME_NUMBER',
                         invoice_gross_vnd=9_000_000)]
        case.vendor = case.tables['vendors'][13]
        rows.append(self.pay(case, 1, channel='cash', invoice_number='SAME_NUMBER',
                             invoice_gross_vnd=9_000_000))
        result = case.score()
        self.assertTrue(all(not self.active(result, row) for row in rows))

    def test_different_erp_ids_cannot_hide_the_same_invoice(self):
        case = self.case()
        first = self.pay(case, 0, channel='cash', invoice_id='ERP_ORIGINAL',
                         invoice_number='LEGAL-001', invoice_gross_vnd=9_000_000)
        second = self.pay(case, 1, invoice_id='ERP_COPY',
                          invoice_number='legal 001', invoice_gross_vnd=9_000_000)
        hit, = self.active(case.score(), second)
        self.assertEqual(hit['related_transaction_ids'], [first['transaction_id']])

    def test_future_cash_payment_does_not_rewrite_an_earlier_result(self):
        case = self.case()
        first = self.pay(case, 0, channel='cash', invoice_number='CAUSAL_INV',
                         invoice_gross_vnd=9_000_000)
        before = copy.deepcopy(case.score())
        second = self.pay(case, 1, channel='cash', invoice_number='CAUSAL_INV',
                          invoice_gross_vnd=9_000_000)
        after = case.score()
        self.assertEqual(before['scores'], after['scores'][:1])
        self.assertEqual(before['hits'], [hit for hit in after['hits']
                                         if hit['transaction_id'] == first['transaction_id']])
        self.assertTrue(self.active(after, second))


if __name__ == '__main__':
    unittest.main()
