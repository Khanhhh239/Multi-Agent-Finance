"""Business negatives, positive controls and temporal policy at phase 2."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.noise_policy import name_similarity
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import score_rules


class NoisePolicyTest(unittest.TestCase):
    def case(self):
        c = Case()
        c.config = {'noise_policy': 'phase2'}
        return c

    def hit(self, result, row, rule):
        return next((h for h in result['hits'] if h['transaction_id'] == row['transaction_id'] and
                     (h['rule_id'] == rule or rule in h.get('aliases', []))), None)

    def proof(self, c, **values):
        return dict(company_id='C001', status='verified', evidence_id='PROOF', verifier_id=c.director['employee_id'],
                    verified_at=stamp(c.at-timedelta(days=3)), observed_at=stamp(c.at-timedelta(days=2)), **values)

    def test_generic_names_are_quality_gaps_not_fuzzy_matches(self):
        c = self.case()
        row = c.pay()
        result = c.score()
        self.assertIsNone(self.hit(result, row, 'E3'))
        self.assertTrue(result['master_name_quality'])
        self.assertIsNone(name_similarity('Công ty mô phỏng đối tác 1', 'Công ty mô phỏng đối tác 2'))

    def test_informative_alias_names_remain_master_findings_without_risk_points(self):
        c = self.case()
        c.tables['vendors'] = c.tables['vendors'][12:14]
        c.tables['vendors'][0]['name'] = 'ABC Co., Ltd'
        c.tables['vendors'][1]['name'] = 'A.B.C Co Ltd'
        row = c.pay()
        result = c.score()
        hit = self.hit(result, row, 'E3')
        self.assertEqual(hit['scoring_role'], 'master_quality')
        self.assertEqual(hit['points'], 0)
        self.assertFalse(result['scores'][-1]['operational_alert'])

    def test_b5_e4_are_one_evidence_with_address_and_disclosure_context(self):
        for field in ('address', 'phone'):
            c = self.case()
            vendors = c.shared_vendors(field)
            vendors[0]['related_party_disclosed_at'] = '2023-01-01T00:00:00+07:00'
            row = c.pay(vendor=vendors[0])
            result = c.score()
            first, alias = self.hit(result, row, 'B5'), self.hit(result, row, 'E4')
            self.assertIs(first, alias)
            self.assertEqual(first['points'], 0)
            self.assertIn(vendors[0]['vendor_id'], first['evidence']['declared_vendor_ids'])
            self.assertEqual(len([h for h in result['hits'] if h['transaction_id'] == row['transaction_id'] and h['rule_id'] in {'B5', 'E4'}]), 1)

    def test_clock_context_cannot_make_weak_rounding_patterns_operational(self):
        c = self.case()
        row = c.pay(c.at.replace(hour=23), 17_000_000)
        result = c.score()
        hit = self.hit(result, row, 'C1')
        self.assertEqual((hit['intrinsic_points'], hit['points'], hit['hard_trigger']), (1, 0, 0))
        self.assertFalse(result['scores'][-1]['operational_alert'])

    def test_clock_context_supports_independent_sod_trigger(self):
        c = self.case()
        row = c.pay(c.at.replace(hour=23), 5_000_000, approver_id=c.maker['employee_id'])
        result = c.score()
        self.assertEqual(self.hit(result, row, 'C1')['points'], 1)
        self.assertEqual(self.hit(result, row, 'C2')['points'], 20)
        self.assertTrue(result['scores'][-1]['operational_alert'])

    def schedule(self, c, action='all'):
        record = dict(schedule_id='SHIFT', company_id='C001', employee_id='', role='', action=action,
            weekdays='0,1,2,3,4,5,6', start_time='00:00', end_time='23:59', holiday_work_allowed=1,
            effective_from='2025-01-01T00:00:00+07:00', effective_to='2026-01-01T00:00:00+07:00',
            status='approved', evidence_id='APPROVED_SHIFT', evidence_on_file=1,
            approver_id=c.director['employee_id'], approved_at=stamp(c.at-timedelta(days=5)),
            observed_at=stamp(c.at-timedelta(days=4)))
        c.tables['operating_schedules'].append(record)
        return record

    def test_schedule_authorizes_weekend_operations_without_inventing_exemptions(self):
        c = self.case()
        self.schedule(c)
        row = c.pay(c.at.replace(day=17, hour=23))
        self.assertIsNone(self.hit(c.score(), row, 'C1'))

    def test_schedule_is_checked_separately_for_maker_and_checker(self):
        c = self.case()
        self.schedule(c, 'maker')
        row = c.pay(c.at.replace(hour=23))
        hit = self.hit(c.score(), row, 'C1')
        self.assertEqual((hit['evidence']['created_outside'], hit['evidence']['approved_outside']), (0, 1))

    def test_schedule_revision_between_creation_and_approval_does_not_revoke_past_work(self):
        c = self.case()
        record = self.schedule(c)
        row = c.pay(c.at.replace(hour=23))
        c.tables['operating_schedules'].append(dict(record, status='revoked', observed_at=stamp(c.at.replace(hour=22, minute=30))))
        hit = self.hit(c.score(), row, 'C1')
        self.assertEqual((hit['evidence']['created_outside'], hit['evidence']['approved_outside']), (0, 1))

    def test_future_schedule_cannot_authorize_past_events(self):
        c = self.case()
        record = self.schedule(c)
        record['observed_at'] = stamp(c.at+timedelta(days=1))
        c.pay(c.at.replace(hour=23))
        without = copy.deepcopy(c)
        without.tables['operating_schedules'] = []
        self.assertEqual(c.score(), without.score())

    def test_a1_mixed_invoices_keep_current_documented_installment_exempt(self):
        c = self.case()
        c.pay(amount=9_000_000, invoice_number='OTHER')
        row = c.sequence([9_000_000]*2, days=1, start=c.at+timedelta(hours=1),
                         invoice_number='ONE', invoice_gross_vnd=18_000_000)
        hit = self.hit(c.score(), row, 'A1')
        self.assertEqual(hit['points'], 0)
        self.assertTrue(hit['suppressed_reason'])

    def test_verified_independent_purchase_requests_are_not_a_split_packet(self):
        for code in ('A1', 'A2'):
            c = self.case()
            row = c.sequence([9_000_000]*3)
            for i, tx in enumerate(c.rows):
                c.tables['procurement_links'].append(self.proof(c, link_id=f'LINK{i}', transaction_id=tx['transaction_id'],
                    vendor_id=tx['vendor_id'], request_id=f'REQ{i}', purchase_order_id=f'PO{i}'))
            hit = self.hit(c.score(), row, code)
            self.assertEqual(hit['points'], 0)
            self.assertTrue(hit['evidence']['excluded_independent_requests'])

    def test_shared_purchase_request_or_unverified_links_cannot_hide_splitting(self):
        for same, invalid in ((True, False), (False, True)):
            c = self.case()
            row = c.sequence([9_000_000]*3)
            for i, tx in enumerate(c.rows):
                record = self.proof(c, link_id=f'LINK{i}', transaction_id=tx['transaction_id'], vendor_id=tx['vendor_id'],
                    request_id='REQ' if same else f'REQ{i}', purchase_order_id='PO' if same else f'PO{i}')
                if invalid:
                    record['status'] = 'unverified'
                c.tables['procurement_links'].append(record)
            self.assertEqual(self.hit(c.score(), row, 'A1')['points'], 8)

    def test_vendor_age_and_document_count_alone_are_not_hard_evidence(self):
        c = self.case()
        c.new_vendor()
        row = c.pay(amount=50_000_000, support_doc_count=4, goods_receipt_verified=1)
        result = c.score()
        hit = self.hit(result, row, 'B3')
        self.assertEqual(hit['points'], 0)
        self.assertFalse(hit['suppressed_reason'])
        self.assertEqual(hit['evidence']['evidence_status'], 'needs_typed_fulfilment_evidence')

    def test_verified_typed_fulfilment_exempts_new_vendor(self):
        c = self.case()
        c.new_vendor()
        row = c.pay(amount=50_000_000, support_doc_count=0, goods_receipt_verified=0)
        for i, kind in enumerate(('invoice', 'purchase_order', 'goods_receipt')):
            c.tables['transaction_documents'].append(self.proof(c, record_id=f'DOC{i}', transaction_id=row['transaction_id'],
                vendor_id=row['vendor_id'], document_type=kind))
        hit = self.hit(c.score(), row, 'B3')
        self.assertEqual(hit['points'], 0)
        self.assertTrue(hit['suppressed_reason'])
        self.assertEqual(hit['evidence']['evidence_status'], 'verified_fulfilment')

    def test_new_shell_relationship_and_payroll_fraud_are_not_suppressed_by_new_vendor_context(self):
        c = self.case()
        c.new_vendor()['bank_account'] = c.worker['bank_account']
        row = c.pay(amount=50_000_000, support_doc_count=0, goods_receipt_verified=0)
        result = c.score()
        self.assertEqual(self.hit(result, row, 'B1')['points'], 20)
        self.assertTrue(result['scores'][-1]['operational_alert'])

    def test_robust_baseline_preserves_large_control_and_does_not_pool_different_vendors(self):
        c = self.case()
        c.sequence([1_000_000+(i%5-2)*10_000 for i in range(25)], kind='cash_expense', start=c.at-timedelta(days=30))
        row = c.pay(amount=3_000_000, kind='cash_expense')
        hit = self.hit(c.score(), row, 'A5')
        self.assertEqual(hit['evidence']['method'], 'log_median_mad')
        self.assertGreater(hit['evidence']['robust_z'], 3)
        self.assertEqual(hit['points'], 0)
        c = self.case()
        c.sequence([1_000_000]*25, start=c.at-timedelta(days=30))
        row = c.pay(amount=30_000_000, vendor=c.tables['vendors'][20])
        self.assertIsNone(self.hit(c.score(), row, 'A5'))

    def test_future_transactions_do_not_change_causal_robust_baseline(self):
        c = self.case()
        c.sequence([1_000_000]*25, kind='cash_expense', start=c.at-timedelta(days=30))
        row = c.pay(amount=3_000_000, kind='cash_expense')
        short = copy.deepcopy(c)
        c.pay(c.at+timedelta(days=1), 999_000_000, kind='cash_expense')
        full = c.score()
        expected = short.score()
        self.assertEqual(self.hit(full, row, 'A5'), self.hit(expected, row, 'A5'))


if __name__ == '__main__':
    unittest.main()
