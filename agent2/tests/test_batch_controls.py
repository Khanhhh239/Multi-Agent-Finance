"""Post-close evidence for simultaneous payments without rewriting row scores."""
import copy
import json
import unittest
from datetime import timedelta

import test_payment_evidence as payment_fixtures
from sme_fraud.case_queue import review_queue
from sme_fraud.rule_audit_cases import Case


class BatchControlsTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3', 'evidence_policy': 'phase4'}
        return case

    def events(self, result, rule, active=True):
        return [event for event in result.get('batch_events', []) if event['rule_id'] == rule
                and (not active or event['points'] > 0)]

    def test_p1_detects_simultaneous_bank_and_cash_overpayment(self):
        for channels in (('bank', 'bank'), ('cash', 'cash'), ('cash', 'bank')):
            with self.subTest(channels=channels):
                case = self.case()
                rows = [case.pay(invoice_number='ONE', invoice_gross_vnd=9_000_000,
                                 payment_channel=channel,
                                 recipient_account='' if channel == 'cash' else case.vendor['bank_account'],
                                 credit_account='111' if channel == 'cash' else '112') for channel in channels]
                result = case.score()
                self.assertFalse(any(h['rule_id'] == 'P1' and h['points'] for h in result['hits']))
                events = self.events(result, 'P1')
                self.assertEqual(len(events), 1)
                event = events[0]
                self.assertEqual((event['points'], event['hard_trigger']), (20, 1))
                self.assertEqual(event['phase'], 'batch_closed')
                self.assertEqual(event['evidence']['cumulative_paid_vnd'], 18_000_000)
                self.assertEqual(set(event['transaction_ids']), {r['transaction_id'] for r in rows})
                cases, _ = review_queue(result, case.tables)
                self.assertEqual(len(cases), 1)
                self.assertEqual(cases[0]['priority'], 'cao_nhat')
                self.assertEqual(set(json.loads(cases[0]['transaction_ids'])), set(event['transaction_ids']))

    def test_p1_includes_prior_payments_outside_split_windows(self):
        case = self.case()
        prior = case.pay(case.at-timedelta(days=45), 5_000_000,
                         invoice_number='ONE', invoice_gross_vnd=10_000_000)
        for _ in range(2):
            case.pay(amount=3_000_000, invoice_number='ONE', invoice_gross_vnd=10_000_000)
        event, = self.events(case.score(), 'P1')
        self.assertEqual(event['evidence']['cumulative_paid_vnd'], 11_000_000)
        self.assertEqual(event['related_transaction_ids'], [prior['transaction_id']])

    def test_missing_or_conflicting_invoice_identity_cannot_hard_trigger(self):
        for mode in ('blank', 'conflicting_gross', 'installments'):
            with self.subTest(mode=mode):
                case = self.case()
                for index in range(2):
                    gross = 9_000_000 if mode != 'installments' else 18_000_000
                    if mode == 'conflicting_gross' and index:
                        gross = 18_000_000
                    case.pay(invoice_number='' if mode == 'blank' else 'ONE', invoice_gross_vnd=gross)
                result = case.score()
                self.assertFalse(self.events(result, 'P1'))
                if mode == 'conflicting_gross':
                    event, = self.events(result, 'P1', active=False)
                    self.assertEqual((event['status'], event['hard_trigger']), ('information_gap', 0))

    def test_a1_detects_simultaneous_split_and_keeps_row_scores(self):
        case = self.case()
        first = case.pay(invoice_number='INV_1', invoice_gross_vnd=9_000_000)
        before = copy.deepcopy(case.score())
        case.pay(invoice_number='INV_2', invoice_gross_vnd=9_000_000)
        after = case.score()
        self.assertEqual(after['scores'][0], before['scores'][0])
        self.assertEqual([h for h in after['hits'] if h['transaction_id'] == first['transaction_id']], before['hits'])
        event, = self.events(after, 'A1')
        self.assertEqual(event['points'], 8)
        self.assertEqual(event['evidence']['total_vnd'], 18_000_000)
        self.assertFalse(any(h['rule_id'] == 'A1' and h['points'] for h in after['hits']))

    def test_a2_detects_count_and_total_only_reached_at_batch_close(self):
        case = self.case()
        prior = case.pay(case.at-timedelta(days=10), 4_000_000)
        for _ in range(2):
            case.pay()
        result = case.score()
        event, = self.events(result, 'A2')
        self.assertEqual(event['evidence']['count'], 3)
        self.assertEqual(event['evidence']['total_vnd'], 22_000_000)
        self.assertIn(prior['transaction_id'], event['related_transaction_ids'])
        self.assertFalse(any(h['rule_id'] == 'A2' and h['points'] for h in result['hits']))

    def test_a3_detects_linked_recipient_batch_and_respects_graph_switch(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                case = self.case()
                case.config['enable_graph'] = enabled
                vendors = case.shared_vendors()
                for vendor in vendors[:2]:
                    case.pay(vendor=vendor)
                events = self.events(case.score(), 'A3')
                self.assertEqual(bool(events), enabled)
                if enabled:
                    self.assertEqual(events[0]['points'], 8)
                    self.assertTrue(events[0]['graph_path'])

    def test_a4_counts_current_batch_with_monthly_history(self):
        case = self.case()
        for index, offset in enumerate((-1, 0, 0)):
            case.pay(case.at+timedelta(days=offset), 17_000_000,
                     vendor=case.tables['vendors'][12+index])
        result = case.score()
        event, = self.events(result, 'A4')
        self.assertEqual(event['evidence']['count'], 3)
        self.assertEqual(event['points'], 3)
        self.assertFalse(any(h['rule_id'] == 'A4' and h['points'] for h in result['hits']))

    def test_valid_installments_and_independent_requests_remain_exempt(self):
        fixture = payment_fixtures.PaymentEvidenceTest()
        for mode in ('installments', 'independent'):
            with self.subTest(mode=mode):
                case = self.case()
                rows = [case.pay(invoice_number='ONE' if mode == 'installments' else f'INV_{i}',
                                 invoice_gross_vnd=18_000_000 if mode == 'installments' else 9_000_000)
                        for i in range(2)]
                if mode == 'installments':
                    fixture.bind_request_rows(case, rows, total=18_000_000)
                else:
                    for i, row in enumerate(rows):
                        fixture.bind_request_rows(case, [row], request_id=f'R{i}', po_id=f'PO{i}')
                result = case.score()
                self.assertFalse(self.events(result, 'A1'))
                self.assertFalse(self.events(result, 'P1'))

    def test_request_cap_cannot_be_reused_by_simultaneous_installments(self):
        fixture = payment_fixtures.PaymentEvidenceTest()
        case = self.case()
        rows = [case.pay(invoice_number='ONE', invoice_gross_vnd=18_000_000) for _ in range(2)]
        fixture.bind_request_rows(case, rows, total=17_000_000)
        self.assertTrue(self.events(case.score(), 'A1'))

    def test_split_summary_excludes_a_proven_independent_obligation(self):
        fixture = payment_fixtures.PaymentEvidenceTest()
        case = self.case()
        rows = [case.pay(invoice_number=f'INV_{i}', invoice_gross_vnd=9_000_000) for i in range(3)]
        fixture.bind_request_rows(case, rows[:1], total=9_000_000)
        event, = self.events(case.score(), 'A1')
        self.assertEqual(event['transaction_ids'], [rows[1]['transaction_id'], rows[2]['transaction_id']])
        self.assertEqual(event['evidence']['total_vnd'], 18_000_000)
        self.assertEqual(event['evidence']['raw_total_vnd'], 27_000_000)

    def test_input_order_and_future_transactions_do_not_change_closed_events(self):
        case = self.case()
        for i in range(2):
            case.pay(invoice_number=f'INV_{i}', invoice_gross_vnd=9_000_000)
        before = copy.deepcopy(case.score())
        self.assertTrue(before.get('batch_events'))
        case.rows.reverse()
        self.assertEqual(case.score()['batch_events'], before['batch_events'])
        case.pay(case.at+timedelta(days=1))
        after = case.score()
        self.assertEqual([e for e in after['batch_events'] if e['detected_at'] <= before['scores'][0]['posted_at']],
                         before['batch_events'])

    def test_batch_evidence_does_not_create_duplicate_queue_members(self):
        case = self.case()
        case.pay(case.at-timedelta(days=1), invoice_number='ONE', invoice_gross_vnd=9_000_000)
        for _ in range(2):
            case.pay(invoice_number='ONE', invoice_gross_vnd=9_000_000)
        result = case.score()
        self.assertTrue(self.events(result, 'P1'))
        cases, events = review_queue(result, case.tables)
        members = [tid for case in cases for tid in json.loads(case['transaction_ids'])]
        self.assertEqual(len(members), len(set(members)))
        self.assertEqual(len(cases), 1)
        self.assertTrue(json.loads(cases[0]['batch_event_ids']))
        self.assertTrue(any(event['event'] == 'batch_closed' for event in events))

    def test_recipient_banks_are_distinct_and_unknown_bank_stays_a_gap(self):
        for known_banks in (True, False):
            with self.subTest(known_banks=known_banks):
                case = self.case()
                for index in range(2):
                    case.pay(recipient_account='0123456789', recipient_bank_code=f'BANK_{index}' if known_banks else '',
                             invoice_number=f'INV_{index}', invoice_gross_vnd=9_000_000)
                result = case.score()
                self.assertFalse(self.events(result, 'A1'))
                if not known_banks:
                    event, = self.events(result, 'A1', active=False)
                    self.assertEqual((event['status'], event['points'], event['hard_trigger']), ('information_gap', 0, 0))

    def test_a1_short_window_boundary_is_inclusive(self):
        for seconds, expected in ((0, True), (1, False)):
            with self.subTest(seconds=seconds):
                case = self.case()
                case.pay(case.at-timedelta(days=3, seconds=seconds), 5_000_000)
                for _ in range(2):
                    case.pay(amount=6_000_000)
                self.assertEqual(bool(self.events(case.score(), 'A1')), expected)

    def test_a4_calendar_month_and_rolling_policy_keep_their_boundaries(self):
        for period, expected in (('calendar_month', False), ('rolling_30d', True)):
            with self.subTest(period=period):
                case = self.case()
                case.config['near_period'] = period
                case.at = case.at.replace(month=9, day=1)
                for index, offset in enumerate((-1, 0, 0)):
                    case.pay(case.at+timedelta(days=offset), 17_000_000,
                             vendor=case.tables['vendors'][12+index])
                self.assertEqual(bool(self.events(case.score(), 'A4')), expected)

    def test_revoked_or_future_request_cannot_exempt_a_closed_batch(self):
        fixture = payment_fixtures.PaymentEvidenceTest()
        for mode in ('revoked', 'future'):
            with self.subTest(mode=mode):
                case = self.case()
                rows = [case.pay(invoice_number='ONE', invoice_gross_vnd=18_000_000) for _ in range(2)]
                fixture.bind_request_rows(case, rows, total=18_000_000)
                record = case.tables['payment_requests'][0]
                if mode == 'revoked':
                    record['status'] = 'revoked'
                else:
                    record['observed_at'] = (case.at+timedelta(days=1)).isoformat(timespec='seconds')
                self.assertTrue(self.events(case.score(), 'A1'))


if __name__ == '__main__':
    unittest.main()
