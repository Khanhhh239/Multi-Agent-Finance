"""B4 must not reduce historical risk using a receipt learned after payment."""
import hashlib
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


class B4EvidenceTimingTest(unittest.TestCase):
    def case(self, *, legacy=False):
        case = Case()
        case.config = dict(noise_policy='legacy' if legacy else 'phase2',
                           spec_policy='legacy' if legacy else 'phase3')
        case.tables['vendor_status_history'] = [dict(
            company_id='C001', vendor_id=case.vendor['vendor_id'], status='ceased',
            effective_at=stamp(case.at - timedelta(days=1)),
            observed_at=stamp(case.at - timedelta(days=1)))]
        return case

    def pay(self, case, **values):
        return case.pay(invoice_issued_at=stamp(case.at - timedelta(days=10)), **values)

    def hit(self, result, row):
        hits = [hit for hit in result['hits'] if hit['rule_id'] == 'B4'
                and hit['transaction_id'] == row['transaction_id']]
        self.assertEqual(len(hits), 1)
        return hits[0]

    def test_late_receipt_keeps_three_points_in_both_policy_modes(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                case = self.case(legacy=legacy)
                row = self.pay(case, goods_receipt_verified=1,
                               support_docs_observed_at=stamp(case.at + timedelta(days=2)))
                hit = self.hit(case.score(), row)
                self.assertEqual(hit['points'], 3)
                self.assertEqual(hit['suppressed_reason'], '')

    def test_receipt_is_available_only_at_or_before_payment_cutoff(self):
        for offset, expected in ((-86400, 0), (0, 0), (1, 3)):
            with self.subTest(seconds_from_payment=offset):
                case = self.case()
                row = self.pay(case, goods_receipt_verified='1',
                               support_docs_observed_at=stamp(case.at + timedelta(seconds=offset)))
                hit = self.hit(case.score(), row)
                self.assertEqual(hit['points'], expected)
                self.assertEqual(bool(hit['suppressed_reason']), expected == 0)

    def test_future_receipt_flag_change_cannot_change_historical_b4_hit(self):
        case = self.case()
        row = self.pay(case, goods_receipt_verified=0, support_doc_count=0,
                       support_docs_observed_at=stamp(case.at + timedelta(days=2)))
        before = self.hit(case.score(), row)
        self.assertEqual(before['points'], 3)
        row.update(goods_receipt_verified=1, support_doc_count=2)
        self.assertEqual(self.hit(case.score(), row), before)

    def test_later_payment_can_use_receipt_without_rewriting_earlier_payment(self):
        case = self.case()
        observed = stamp(case.at + timedelta(days=2))
        earlier = self.pay(case, goods_receipt_verified=1, support_docs_observed_at=observed)
        before = self.hit(case.score(), earlier)
        later = case.pay(case.at + timedelta(days=2), goods_receipt_verified=1,
                         support_docs_observed_at=observed,
                         invoice_issued_at=stamp(case.at - timedelta(days=10)))
        result = case.score()
        self.assertEqual(self.hit(result, earlier), before)
        self.assertEqual(self.hit(result, earlier)['points'], 3)
        self.assertEqual(self.hit(result, later)['points'], 0)

    def test_missing_optional_timestamp_preserves_legacy_posting_assumption(self):
        for verified, expected in ((0, 3), (1, 0)):
            with self.subTest(verified=verified):
                case = self.case()
                row = self.pay(case, goods_receipt_verified=verified)
                self.assertNotIn('support_docs_observed_at', row)
                self.assertEqual(self.hit(case.score(), row)['points'], expected)

    def test_unverified_receipt_cannot_suppress_even_when_documents_are_known(self):
        case = self.case()
        row = self.pay(case, goods_receipt_verified=0,
                       support_docs_observed_at=stamp(case.at - timedelta(days=1)))
        self.assertEqual(self.hit(case.score(), row)['points'], 3)

    def test_receipt_cannot_suppress_registry_risk_already_present_at_invoice(self):
        case = self.case()
        case.tables['vendor_status_history'][0].update(
            effective_at=stamp(case.at - timedelta(days=20)),
            observed_at=stamp(case.at - timedelta(days=20)))
        row = self.pay(case, goods_receipt_verified=1, support_docs_observed_at=stamp(case.at))
        hit = self.hit(case.score(), row)
        self.assertEqual(hit['points'], 10)
        self.assertEqual(hit['evidence']['risky_at_invoice'], 1)

    def test_receipt_cannot_suppress_tax_authority_listing(self):
        case = self.case()
        case.vendor['tax_code'] = '0100000001'
        case.tables['tax_risk_history'] = [dict(
            record_id='SIM_B4_TIMING', company_id='C001', tax_code='0100000001',
            status='high_risk', risk_reason='Synthetic B4 timing regression fixture',
            effective_from='2025-01-01', effective_to='',
            published_at='2025-01-02T09:00:00+07:00', observed_at='2025-01-02T10:00:00+07:00',
            source_url='https://www.gdt.gov.vn/synthetic-contract-test', source_document_id='SIM_B4_DOC',
            source_sha256=hashlib.sha256(b'synthetic B4 timing fixture').hexdigest())]
        row = self.pay(case, goods_receipt_verified=1, support_docs_observed_at=stamp(case.at))
        hit = self.hit(case.score(), row)
        self.assertEqual(hit['points'], 10)
        self.assertEqual(hit['evidence']['evidence_status'], 'tax_authority_list_match')

    def test_explicit_invalid_timestamp_is_rejected_instead_of_assumed_known(self):
        for observed in ('', '2025-08-12', '2025-08-12T04:00:00+00:00'):
            with self.subTest(observed=observed):
                case = self.case()
                self.pay(case, goods_receipt_verified=1, support_docs_observed_at=observed)
                with self.assertRaisesRegex(ValueError, 'support_docs_observed_at'):
                    case.score()
