"""Boundary, payment-scope and queue checks for independent cash purchase review."""
import copy
from datetime import datetime, timedelta
import unittest

from sme_fraud.case_queue import review_queue
from sme_fraud.cash_controls import CASH_POLICY, REVIEW_POLICY, LEGACY_REVIEW_POLICY
from sme_fraud.generate import TZ
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import score_rules


class CashControlsTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4',
                           cash_payment_policy=CASH_POLICY)
        return case

    def pay(self, case, amount, at=None, **values):
        return case.pay(at, amount, kind='cash_expense', **values)

    def hit(self, result):
        return next((r for r in result['hits'] if r['rule_id'] == 'P2'), None)

    def test_2024_and_first_half_2025_use_inclusive_twenty_million(self):
        for at in (datetime(2024, 8, 12, 11, tzinfo=TZ), datetime(2025, 6, 30, 11, tzinfo=TZ)):
            for amount, expected in ((19_999_999, False), (20_000_000, True), (20_000_001, True)):
                with self.subTest(at=at, amount=amount):
                    case = self.case()
                    self.pay(case, amount, at)
                    hit = self.hit(case.score())
                    self.assertEqual(hit is not None, expected)
                    if hit:
                        self.assertEqual(hit['evidence']['vat_non_cash_threshold_vnd'], 20_000_000)

    def test_july_2025_and_2026_use_inclusive_five_million(self):
        for at in (datetime(2025, 7, 1, 11, tzinfo=TZ), datetime(2026, 10, 17, 11, tzinfo=TZ)):
            for amount, expected in ((4_999_999, False), (5_000_000, True), (20_000_000, True)):
                with self.subTest(at=at, amount=amount):
                    case = self.case()
                    self.pay(case, amount, at)
                    hit = self.hit(case.score())
                    self.assertEqual(hit is not None, expected)
                    if hit:
                        self.assertEqual(hit['evidence']['vat_non_cash_threshold_vnd'], 5_000_000)

    def test_regime_boundary_at_vietnam_midnight(self):
        case = self.case()
        self.pay(case, 5_000_000, datetime(2025, 7, 1, 0, tzinfo=TZ))
        self.assertEqual(self.hit(case.score())['evidence']['payment_policy'], 'ND181/2025/ND-CP_D26')

    def test_cash_alone_can_open_review_without_becoming_a_hard_trigger(self):
        case = self.case()
        row = self.pay(case, 5_000_000, invoice_id='INV', invoice_number='VAT-1',
                       invoice_issued_at=case.at.isoformat(), invoice_gross_vnd=5_000_000)
        result = case.score()
        score = result['scores'][0]
        self.assertEqual((score['base_score'], score['hard_trigger'], score['operational_alert']), (8, 0, 1))
        queue, _ = review_queue(result, case.tables)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['priority'], 'trung_binh')
        self.assertIn(row['transaction_id'], queue[0]['transaction_ids'])
        self.assertTrue(self.hit(result)['evidence']['requires_tax_review'])

    def test_small_cash_installment_uses_gross_invoice_value(self):
        case = self.case()
        self.pay(case, 1_000_000, invoice_id='INV', invoice_number='VAT-1',
                 invoice_issued_at=case.at.isoformat(), invoice_gross_vnd=20_000_000)
        hit = self.hit(case.score())
        self.assertEqual(hit['points'], 8)
        self.assertIn('cash_payment_on_invoice_at_or_above_vat_threshold', hit['evidence']['reasons'])

    def test_missing_invoice_is_flagged_as_review_not_a_tax_verdict(self):
        case = self.case()
        self.pay(case, 5_000_000, invoice_id='', invoice_number='', invoice_issued_at='', invoice_gross_vnd=0)
        hit = self.hit(case.score())
        self.assertEqual(hit['evidence']['evidence_status'], 'cash_purchase_missing_invoice')
        self.assertEqual(hit['points'], 0)
        self.assertEqual(hit['evidence']['review_category'], 'information_request')
        self.assertEqual(hit['status'], 'information_gap')
        result = case.score()
        self.assertFalse(result['scores'][0]['operational_alert'])
        queue, _ = review_queue(result, case.tables)
        self.assertEqual((len(queue), queue[0]['case_type'], queue[0]['priority'], queue[0]['status']),
                         (1, 'information_request', 'thap', 'awaiting_information'))

    def test_future_invoice_cannot_hide_a_large_cash_payment(self):
        case = self.case()
        self.pay(case, 5_000_000, invoice_issued_at=(case.at+timedelta(days=1)).isoformat())
        hit = self.hit(case.score())
        self.assertEqual(hit['points'], 0)
        self.assertEqual(hit['evidence']['evidence_status'], 'cash_purchase_invalid_invoice_date')

    def test_future_invoice_is_not_used_as_gross_value_for_a_small_payment(self):
        for delay in (timedelta(hours=1), timedelta(days=1)):
            case = self.case()
            self.pay(case, 1_000_000, invoice_id='INV', invoice_gross_vnd=20_000_000,
                     invoice_issued_at=(case.at+delay).isoformat())
            hit = self.hit(case.score())
            self.assertEqual((hit['points'], hit['evidence']['evidence_status']), (0, 'information_gap'))

    def test_transition_invoice_requests_review_of_both_regimes(self):
        case = self.case()
        self.pay(case, 5_000_000, datetime(2025, 7, 2, 11, tzinfo=TZ), invoice_id='OLD',
                 invoice_gross_vnd=10_000_000, invoice_issued_at='2025-06-30T11:00:00+07:00')
        hit = self.hit(case.score())
        self.assertEqual(hit['evidence']['evidence_status'], 'transition_review_required')

    def test_internal_limit_is_company_scoped_and_strictly_exceeded(self):
        for limit, amount, expected in ((2_000_000, 2_000_000, False), (2_000_000, 2_000_001, True)):
            case = self.case()
            case.config['cash_limit_vnd_by_company'] = {'C001': limit}
            self.pay(case, amount)
            self.assertEqual(self.hit(case.score()) is not None, expected)
        case = self.case()
        case.config['cash_limit_vnd_by_company'] = {'OTHER': 1}
        self.pay(case, 2_000_000)
        self.assertIsNone(self.hit(case.score()))

    def test_bank_nonfinancial_receipts_payroll_and_advances_do_not_trigger(self):
        variations = [dict(payment_channel='bank'), dict(is_financial_entry=0)]
        for values in variations:
            case = self.case()
            self.pay(case, 50_000_000, **values)
            self.assertIsNone(self.hit(case.score()))
        for kind in ('customer_receipt', 'payroll', 'advance_issue', 'advance_review', 'tax_payment'):
            case = self.case()
            case.pay(amount=50_000_000, kind=kind, payment_channel='cash')
            self.assertIsNone(self.hit(case.score()))

    def test_foreign_currency_requires_verified_vnd_amount(self):
        case = self.case()
        self.pay(case, 5_000_000, currency='USD')
        hit = self.hit(case.score())
        self.assertEqual((hit['points'], hit['evidence']['evidence_status']), (0, 'information_gap'))

    def test_policy_can_be_pinned_for_historical_replay(self):
        case = self.case()
        self.pay(case, 30_000_000)
        enabled = case.score()
        case.config['cash_payment_policy'] = 'disabled'
        old = case.score()
        self.assertIsNotNone(self.hit(enabled))
        self.assertIsNone(self.hit(old))
        self.assertEqual(next(c for c in old['coverage'] if c['rule_id'] == 'P2')['status'], 'disabled')

    def test_engine_default_enables_cash_screening_and_never_reads_labels(self):
        case = self.case()
        self.pay(case, 5_000_000)
        case.score()
        expected = score_rules(case.tables, features=case.features)
        self.assertIsNotNone(self.hit(expected))
        changed = copy.deepcopy(case.tables)
        changed['labels'] = [dict(transaction_id=case.rows[0]['transaction_id'], is_fraud=1)]
        self.assertEqual(score_rules(changed, features=case.features), expected)

    def test_bad_config_is_rejected(self):
        for values in ({'cash_payment_policy': 'guess'}, {'cash_limit_vnd_by_company': []},
                       {'cash_review_policy': 'guess'}, {'cash_limit_evidence_by_company': []},
                       *[{'cash_limit_vnd_by_company': {'C001': v}} for v in (True, -1, '5000000', 1.5)]):
            case = self.case()
            self.pay(case, 5_000_000)
            case.config.update(values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                case.score()

    def verified_limit(self, case, **changes):
        case.config['cash_limit_vnd_by_company'] = {'C001': 2_000_000}
        record = dict(limit_vnd=2_000_000, source_ref='synthetic-policy/approved-1', verified_by='CFO_SIM',
                      verified_at='2024-01-01T09:00:00+07:00', effective_from='2024-01-01T00:00:00+07:00', effective_to='')
        record.update(changes)
        case.config['cash_limit_evidence_by_company'] = {'C001': record}

    def test_verified_internal_breach_stands_without_invoice_and_has_high_priority(self):
        case = self.case()
        case.config['cash_limit_priority_policy'] = 'legacy_high_v1'
        self.verified_limit(case)
        self.pay(case, 2_000_001)
        result = case.score()
        hit = self.hit(result)
        self.assertEqual((hit['points'], hit['hard_trigger'], hit['evidence']['review_category']),
                         (14, 0, 'verified_internal_breach'))
        queue, _ = review_queue(result, case.tables)
        self.assertEqual((len(queue), queue[0]['case_type'], queue[0]['priority']), (1, 'transaction', 'cao'))
        self.assertIn('invoice_identity', hit['evidence']['missing_fields'])

    def test_manual_limit_without_verification_is_a_zero_point_request(self):
        case = self.case()
        case.config['cash_limit_vnd_by_company'] = {'C001': 2_000_000}
        self.pay(case, 2_000_001)
        hit = self.hit(case.score())
        self.assertEqual((hit['points'], hit['evidence']['internal_limit_status']), (0, 'unverified_limit'))
        self.assertIn('internal_limit_verification', hit['evidence']['missing_fields'])

    def test_internal_verification_is_causal_and_has_exclusive_expiry(self):
        for change, expected in (({'verified_at': '2026-01-01T00:00:00+07:00'}, 'not_known_at_payment'),
                                 ({'effective_from': '2026-01-01T00:00:00+07:00'}, 'outside_effective_period'),
                                 ({'effective_to': '2025-08-12T11:00:00+07:00'}, 'outside_effective_period')):
            case = self.case()
            self.verified_limit(case, **change)
            self.pay(case, 2_000_001, at=datetime(2025, 8, 12, 11, tzinfo=TZ))
            hit = self.hit(case.score())
            self.assertEqual((hit['points'], hit['evidence']['internal_limit_status']), (0, expected))
            if expected == 'not_known_at_payment':
                self.assertIsNone(hit['evidence']['internal_limit_evidence'])

    def test_partial_or_conflicting_limit_metadata_is_rejected(self):
        for change in ({'limit_vnd': 1}, {'verified_by': ''}, {'source_ref': ''},
                       {'verified_at': '2024-01-01T00:00:00'}, {'effective_to': '2023-01-01T00:00:00+07:00'}):
            case = self.case()
            self.verified_limit(case, **change)
            self.pay(case, 2_000_001)
            with self.subTest(change=change), self.assertRaises(ValueError):
                case.score()

    def test_legacy_policy_remains_explicitly_replayable(self):
        case = self.case()
        case.config['cash_review_policy'] = LEGACY_REVIEW_POLICY
        self.pay(case, 5_000_000)
        self.assertEqual(self.hit(case.score())['points'], 8)

    def test_gap_cannot_anchor_context_but_does_not_hide_independent_violation(self):
        for extra in ({}, {'approver_id': None}):
            case = self.case()
            values = dict(created_at=case.at.replace(hour=23).isoformat())
            if extra:
                values['approver_id'] = case.maker['employee_id']
            self.pay(case, 20_000_001, **values)
            result = case.score()
            gap = self.hit(result)
            self.assertEqual(gap['points'], 0)
            c1 = [h for h in result['hits'] if h['rule_id'] == 'C1']
            if not extra:
                self.assertTrue(all(h['points'] == 0 for h in c1))
                self.assertFalse(result['scores'][0]['operational_alert'])
            else:
                self.assertTrue(result['scores'][0]['operational_alert'])
            queue, _ = review_queue(result, case.tables)
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0]['case_type'], 'transaction' if extra else 'information_request')

    def test_missing_invoice_requests_group_by_company_entity_and_30_day_window(self):
        case = self.case()
        for days in (0, 1, 31):
            self.pay(case, 5_000_000+days, case.at+timedelta(days=days))
        result = case.score()
        queue, _ = review_queue(result, case.tables)
        self.assertEqual(len(queue), 2)
        self.assertEqual(sorted(r['observation_count'] for r in queue), [1, 2])
        self.assertEqual(sum(r['observation_count'] for r in queue), 3)
        self.assertTrue(all(r['priority'] == 'thap' and r['max_score'] == 0 for r in queue))

    def test_historical_score_only_snapshots_do_not_require_new_cash_hits(self):
        case = self.case()
        self.pay(case, 2_000_001)
        result = case.score()
        result.pop('hits')
        queue, _ = review_queue(result, case.tables)
        self.assertEqual(queue, [])

    def test_unverified_currency_does_not_assert_that_an_internal_limit_was_checked(self):
        case = self.case()
        self.verified_limit(case)
        self.pay(case, 5_000_000, currency='USD')
        hit = self.hit(case.score())
        self.assertEqual((hit['points'], hit['evidence']['internal_limit_status']), (0, 'not_evaluable'))
