"""Actionable split evidence must reach human review without changing scores."""
import copy
import json
import unittest
from datetime import timedelta
from pathlib import Path
import tempfile

import test_payment_evidence as payment_fixtures
from sme_fraud.generate import parse, write_csv
from sme_fraud.rules import score_rules
from sme_fraud.case_admission import admission

from sme_fraud.case_queue import review_queue, batch_groups, operational_members
from sme_fraud.rule_audit_cases import Case


class SplitPatternAdmissionTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        return case

    def rows(self, case, amount=9_000_000, days=7, kind='vendor_payment', count=3):
        return [case.pay(case.at+timedelta(days=i*days), amount, kind=kind,
                         invoice_number=f'SPLIT_{i}', invoice_gross_vnd=amount) for i in range(count)]

    def test_a2_alone_reaches_review_with_four_points_and_no_hard_trigger(self):
        case = self.case()
        rows = self.rows(case)
        result = case.score()
        score = result['scores'][-1]
        self.assertEqual((score['rule_score'], score['hard_trigger']), (4, 0))
        self.assertEqual(score['operational_alert'], 1)
        queue, _ = review_queue(result, case.tables)
        self.assertEqual(len(queue), 1)
        self.assertIn(rows[-1]['transaction_id'], json.loads(queue[0]['transaction_ids']))

    def test_a4_alone_reaches_review_with_three_points(self):
        case = self.case()
        self.rows(case, 17_000_000, days=5, kind='cash_expense')
        result = case.score()
        score = result['scores'][-1]
        self.assertEqual((score['rule_score'], score['hard_trigger']), (3, 0))
        self.assertEqual(score['operational_alert'], 1)
        self.assertEqual(len(review_queue(result, case.tables)[0]), 1)

    def test_batch_a2_and_a4_enter_review_without_increasing_event_points(self):
        for kind, amount, expected in (('vendor_payment', 4_000_000, 4), ('cash_expense', 17_000_000, 3)):
            with self.subTest(kind=kind):
                case = self.case()
                if kind == 'vendor_payment':
                    case.pay(case.at-timedelta(days=10), 15_000_000)
                    count = 2
                else:
                    count = 3
                for i in range(count):
                    case.pay(amount=amount, kind=kind, invoice_number=f'BATCH_{i}', invoice_gross_vnd=amount)
                result = case.score()
                groups = batch_groups(result)
                self.assertTrue(groups)
                self.assertEqual((groups[0]['rule_score'], groups[0]['priority']), (expected, 'trung_binh'))
                self.assertFalse(any(s['operational_alert'] for s in result['scores']))
                queue, _ = review_queue(result, case.tables)
                self.assertEqual(len(queue), 1)
                self.assertEqual(set(json.loads(queue[0]['transaction_ids'])), operational_members(result))

    def test_same_family_hits_are_not_added_together(self):
        case = self.case()
        self.rows(case, 17_000_000)
        result = case.score()
        row = result['scores'][-1]
        self.assertEqual((row['base_score'], row['rule_score'], row['recurrence_points']), (4, 4, 0))
        self.assertEqual(row['review_rule_ids'], 'A2|A4')
        self.assertEqual(row['admission_basis'], 'split_pattern')

    def test_disabling_admission_restores_queue_but_never_changes_numeric_scores(self):
        case = self.case()
        self.rows(case, count=5, days=5)
        # A later strong split must not gain recurrence from review-only arrivals.
        case.pay(case.at+timedelta(days=21), 9_000_000, invoice_number='LATER', invoice_gross_vnd=9_000_000)
        after = case.score()
        before = score_rules(case.tables, features=case.features,
            config={**case.config, 'split_pattern_policy': 'disabled'})
        for left, right in zip(before['scores'], after['scores']):
            for key in ('base_score', 'rule_score', 'recurrence_points', 'hard_trigger', 'known_risky_prior_ids', 'case_entity'):
                self.assertEqual(left[key], right[key], key)
        self.assertEqual(before['hits'], after['hits'])
        self.assertEqual(before['batch_events'], after['batch_events'])

    def test_policy_does_not_admit_two_payments_or_context_alone(self):
        for kind, amount in (('vendor_payment', 9_000_000), ('cash_expense', 17_000_000)):
            case = self.case()
            self.rows(case, amount, kind=kind, count=2)
            self.assertFalse(any(r['operational_alert'] for r in case.score()['scores']))

    def test_approved_installments_stay_exempt(self):
        case = self.case()
        for i in range(3):
            case.pay(case.at+timedelta(days=7*i), 9_000_000,
                invoice_number='SAME', invoice_gross_vnd=27_000_000)
        result = case.score()
        self.assertTrue(any(h['rule_id'] == 'A2' and h['suppressed_reason'] for h in result['hits']))
        self.assertFalse(any(r['operational_alert'] for r in result['scores']))

    def test_independent_bound_obligations_stay_exempt(self):
        case = self.case()
        rows = self.rows(case)
        fixture = payment_fixtures.PaymentEvidenceTest()
        for i, row in enumerate(rows):
            fixture.bind_request_rows(case, [row], request_id=f'REQ{i}', po_id=f'PO{i}', total=9_000_000)
        result = case.score()
        self.assertFalse(result['scores'][-1]['operational_alert'])
        self.assertEqual(result['scores'][-1]['review_rule_ids'], '')

    def test_future_exception_cannot_remove_existing_admission(self):
        case = self.case()
        rows = self.rows(case)
        before = case.score()
        fixture = payment_fixtures.PaymentEvidenceTest()
        fixture.bind_request_rows(case, rows, total=27_000_000)
        for name in ('payment_requests', 'procurement_links', 'transaction_documents'):
            for source in case.tables[name]:
                source['observed_at'] = '2026-01-01T00:00:00+07:00'
        after = case.score()
        self.assertEqual(before['scores'], after['scores'])

    def test_missing_or_different_banks_do_not_grant_a2_admission(self):
        for banks in (('', '', ''), ('A', 'B', 'A')):
            case = self.case()
            rows = self.rows(case)
            for row, bank in zip(rows, banks):
                row.update(recipient_account='0123456789', recipient_bank_code=bank)
            result = case.score()
            self.assertFalse(result['scores'][-1]['operational_alert'])

    def test_calendar_month_boundary_is_preserved_and_rolling_is_explicit(self):
        for period, expected in (('calendar_month', False), ('rolling_30d', True)):
            case = self.case()
            case.config['near_period'] = period
            case.at = parse('2025-01-31T11:00:00+07:00')
            self.rows(case, 17_000_000, days=1, kind='cash_expense')
            result = case.score()
            self.assertEqual(bool(result['scores'][-1]['operational_alert']), expected)
            self.assertEqual(bool(result['scores'][-1]['review_rule_ids']), expected)

    def test_31_day_calendar_month_keeps_first_day(self):
        case = self.case()
        for day in (1, 15, 31):
            case.pay(parse(f'2025-08-{day:02}T11:00:00+07:00'), 17_000_000, kind='cash_expense')
        self.assertEqual(case.score()['scores'][-1]['admission_basis'], 'split_pattern')

    def test_repeated_admissions_coalesce_and_keep_related_evidence(self):
        case = self.case()
        rows = self.rows(case, count=5, days=5)
        result = case.score()
        queue, _ = review_queue(result, case.tables)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['observation_count'], 3)
        self.assertEqual(queue[0]['admission_basis'], 'split_pattern')
        self.assertEqual(queue[0]['review_rule_ids'], 'A2')
        self.assertEqual(operational_members(result), {r['transaction_id'] for r in rows[2:]})
        for hit in result['hits']:
            if hit['rule_id'] == 'A2' and hit['points']:
                self.assertIn(rows[0]['transaction_id'], hit['related_transaction_ids'])

    def test_suppressed_gaps_false_signals_and_other_weak_rules_never_admit(self):
        config = dict(noise_policy='phase2', split_pattern_policy='split_patterns_v1', operational_score=7)
        for changes in (dict(points=0), dict(suppressed_reason='approved'), dict(status='information_gap'),
                        dict(signal=False), dict(signal=None), dict(rule_id='A5'), dict(rule_id='C1'),
                        dict(evidence=dict(evidence_status='information_gap'))):
            hit = dict(rule_id='A2', points=4, suppressed_reason='', evidence={})
            hit.update(changes)
            self.assertEqual(admission([hit], 4, False, config)['operational_alert'], 0, changes)

    def test_hard_trigger_precedes_pattern_admission(self):
        case = self.case()
        self.rows(case)
        case.rows[-1]['approver_id'] = case.maker['employee_id']
        result = case.score()
        row = result['scores'][-1]
        self.assertEqual((row['hard_trigger'], row['priority'], row['admission_basis']), (1, 'cao_nhat', 'hard_trigger'))

    def test_unsupported_policy_is_rejected(self):
        case = self.case()
        self.rows(case)
        case.config['split_pattern_policy'] = 'anything'
        with self.assertRaisesRegex(ValueError, 'split-pattern review policy'):
            case.score()

    def test_future_transaction_and_input_order_do_not_change_prior_admission(self):
        case = self.case()
        self.rows(case)
        before = copy.deepcopy(case.score())
        case.pay(case.at+timedelta(days=90), 1_000_000)
        case.tables['vendors'].reverse()
        after = case.score()
        self.assertEqual(before['scores'], after['scores'][:3])
        self.assertEqual(before['hits'], [h for h in after['hits'] if h['transaction_id'] in {r['transaction_id'] for r in before['scores']}])

    def test_review_cache_loads_low_score_case_and_related_documents(self):
        from sme_fraud.review_store import ReviewStore
        from sme_fraud.run_rule_repairs import write_jsonl
        case = self.case()
        rows = self.rows(case)
        result = case.score()
        queue, events = review_queue(result, case.tables)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, report = root/'data/sme_fraud_003', root/'reports/sme_fraud_003'
            data.mkdir(parents=True)
            report.mkdir(parents=True)
            for name in ('companies', 'employees', 'vendors', 'customers', 'transactions', 'journal_documents', 'journal_lines'):
                write_csv(data/f'{name}.csv', case.tables[name])
            for name, value in (('case_queue', queue), ('case_events', events)):
                write_csv(report/f'{name}.csv', value)
            write_jsonl(report/'rule_hits.jsonl', result['hits'])
            (report/'rule_coverage.json').write_text(json.dumps(result['coverage']), encoding='utf-8')
            store = ReviewStore(data.parent, report.parent, root/'review.sqlite3', scenarios=['003'])
            store.prepare()
            detail = store.detail('003', queue[0]['case_id'])
            self.assertEqual(detail['case']['max_score'], 4)
            self.assertEqual(detail['case']['admission_basis'], 'split_pattern')
            self.assertEqual(detail['case']['review_rule_ids'], 'A2')
            self.assertTrue(detail['hits'])
            self.assertEqual(set(detail['case']['transaction_ids']), {rows[-1]['transaction_id']})

    def test_batch_bound_obligation_cannot_be_readmitted(self):
        case = self.case()
        rows = [case.pay(amount=17_000_000, invoice_number='ONE', invoice_gross_vnd=51_000_000) for _ in range(3)]
        payment_fixtures.PaymentEvidenceTest().bind_request_rows(case, rows, total=51_000_000)
        result = case.score()
        self.assertFalse(any(r['operational_alert'] for r in result['scores']))
        self.assertFalse(batch_groups(result))

    def test_labels_cannot_change_admission(self):
        case = self.case()
        self.rows(case)
        before = case.score()
        case.tables['labels'] = [dict(transaction_id=r['transaction_id'], is_fraud=i % 2) for i, r in enumerate(case.rows)]
        self.assertEqual(before, case.score())

    def test_csv_float_counts_do_not_change_e1_or_advance_evidence_identity(self):
        for kind in ('payroll', 'advance'):
            case = self.case()
            if kind == 'payroll':
                case.attendance()
            else:
                case.pay(kind='advance_issue', amount=1_000_000)
            native = case.score()
            if kind == 'advance':
                # Exercise both integer-valued evidence fields from cached X.
                case.rows[0]['advance_id'] = 'ADV_NATIVE_CACHE'
                for feature in case.features:
                    feature.update(advance_open_fraction=1., advance_overdue_days=31, advance_extension_known=1)
                native = score_rules(case.tables, config=case.config, features=case.features)
            cached_features = [{k:v if k == 'transaction_id' else float(v) for k,v in f.items()} for f in case.features]
            cached = score_rules(case.tables, config=case.config, features=cached_features)
            self.assertEqual(native['hits'], cached['hits'])
            self.assertTrue(any(h['rule_id'] == ('E1' if kind == 'payroll' else 'T1') for h in cached['hits']))


if __name__ == '__main__':
    unittest.main()
