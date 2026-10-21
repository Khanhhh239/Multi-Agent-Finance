"""A4 trial preserves detections and strong cases while organizing review work."""
import copy
import csv
import json
from pathlib import Path
import tempfile
from datetime import timedelta
import unittest

from sme_fraud.a4_pattern_queue import A4_PATTERN_TRIAL, ENTITY_QUEUE
from sme_fraud.case_identity import equivalent, scope_hash, load_lineage
from sme_fraud.case_queue import review_queue, operational_members
from sme_fraud.generate import parse, write_csv
from sme_fraud.review_store import ReviewStore
from sme_fraud.rule_audit_cases import Case
from sme_fraud.run_rule_repairs import write_jsonl
import test_payment_evidence as payment_fixtures


class A4PatternQueueTest(unittest.TestCase):
    def case(self, count=5, same_time=False):
        c = Case()
        c.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        for index, vendor in enumerate(c.tables['vendors'][12:12+count]):
            for field in ('bank_account', 'phone', 'address', 'representative_id'):
                vendor[field] = f'PATTERN_{field}_{index}'
            vendor['bank_code'] = f'BANK_{index}'
            c.pay(c.at+timedelta(days=0 if same_time else index), 17_000_000, vendor=vendor,
                  recipient_account=vendor['bank_account'], recipient_bank_code=vendor['bank_code'],
                  invoice_number=f'INV_{index}', invoice_gross_vnd=17_000_000)
        return c

    def queue(self, c, result=None):
        return review_queue(result or c.score(), c.tables, policy=A4_PATTERN_TRIAL)

    def members(self, cases):
        return {tid for case in cases for tid in json.loads(case['transaction_ids'])}

    def test_five_unrelated_vendors_open_one_pattern_at_same_detection_time(self):
        c = self.case()
        result = c.score()
        frozen = copy.deepcopy(result)
        before, _ = review_queue(result, c.tables)
        after, events = self.queue(c, result)
        self.assertEqual(len(before), 3)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]['case_type'], 'pattern')
        self.assertEqual((after[0]['max_score'], after[0]['priority']), (3, 'trung_binh'))
        self.assertEqual(after[0]['opened_at'], before[0]['opened_at'])
        self.assertEqual(len(json.loads(after[0]['pattern_context_ids'])), 2)
        self.assertEqual(self.members(after), operational_members(result))
        self.assertEqual(sum(row['event'] == 'opened' for row in events), 1)
        self.assertEqual(result, frozen)

    def test_default_remains_entity_queue_until_independent_review(self):
        c = self.case()
        result = c.score()
        self.assertEqual(review_queue(result, c.tables), review_queue(result, c.tables, policy=ENTITY_QUEUE))
        self.assertEqual(len(review_queue(result, c.tables)[0]), 3)

    def test_hard_trigger_stays_in_its_own_unchanged_entity_case(self):
        c = self.case()
        c.rows[3]['approver_id'] = c.rows[3]['creator_id']
        result = c.score()
        before, _ = review_queue(result, c.tables)
        after, _ = self.queue(c, result)
        tid = c.rows[3]['transaction_id']
        original = next(row for row in before if tid in json.loads(row['transaction_ids']))
        preserved = next(row for row in after if tid in json.loads(row['transaction_ids']))
        for key in ('case_id', 'priority', 'max_score', 'transaction_ids', 'opened_at', 'owner_id'):
            self.assertEqual(original[key], preserved[key], key)
        self.assertEqual(preserved['priority'], 'cao_nhat')
        pattern = next(row for row in after if row['case_type'] == 'pattern')
        self.assertIn(preserved['case_id'], json.loads(pattern['linked_case_ids']))
        self.assertIn(pattern['case_id'], json.loads(preserved['linked_case_ids']))

    def test_later_strong_payment_same_vendor_cannot_append_to_pattern(self):
        c = self.case(count=3)
        vendor = c.tables['vendors'][14]
        c.pay(c.at+timedelta(days=3), 17_000_000, vendor=vendor, invoice_number='STRONG',
              invoice_gross_vnd=17_000_000, approver_id=c.maker['employee_id'])
        cases, _ = self.queue(c)
        self.assertEqual(len(cases), 2)
        strong = next(row for row in cases if c.rows[-1]['transaction_id'] in json.loads(row['transaction_ids']))
        self.assertEqual(strong['case_type'], 'transaction')
        self.assertEqual(strong['priority'], 'cao_nhat')

    def test_pure_a4_batch_opens_pattern_without_relabeling_rows(self):
        c = self.case(count=3, same_time=True)
        result = c.score()
        self.assertFalse(any(row['operational_alert'] for row in result['scores']))
        cases, _ = self.queue(c, result)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['case_type'], 'pattern')
        self.assertTrue(json.loads(cases[0]['batch_event_ids']))
        self.assertEqual(self.members(cases), operational_members(result))

    def test_batch_with_hard_member_keeps_ordinary_path_intact(self):
        c = self.case(count=3, same_time=True)
        c.rows[0]['approver_id'] = c.rows[0]['creator_id']
        result = c.score()
        before, _ = review_queue(result, c.tables)
        after, _ = self.queue(c, result)
        self.assertTrue(all(row['case_type'] != 'pattern' for row in after))
        self.assertEqual([(row['case_id'], row['priority'], row['transaction_ids']) for row in before],
                         [(row['case_id'], row['priority'], row['transaction_ids']) for row in after])

    def test_mixed_a2_a4_and_a2_only_stay_entity_cases(self):
        for amount in (9_000_000, 17_000_000):
            c = self.case(count=0)
            for index in range(3):
                c.pay(c.at+timedelta(days=7*index), amount, invoice_number=f'OTHER_{index}', invoice_gross_vnd=amount)
            cases, _ = self.queue(c)
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0]['case_type'], 'transaction')

    def test_different_banks_are_not_merged_as_a_recipient_identity(self):
        c = self.case()
        for index, row in enumerate(c.rows):
            row.update(recipient_account='0123456789', recipient_bank_code=f'BANK_{index}')
        result = c.score()
        self.assertFalse(any(hit['rule_id'] in {'A1', 'A2'} and hit['points'] for hit in result['hits']))
        cases, _ = self.queue(c, result)
        self.assertEqual(len(cases), 1)  # A4 is maker/month, not recipient equality.
        self.assertEqual(cases[0]['rule_ids'], 'A4')
        self.assertEqual(self.members(cases), operational_members(result))

    def test_bound_independent_obligations_remain_exempt(self):
        c = self.case(count=3)
        fixture = payment_fixtures.PaymentEvidenceTest()
        for index, row in enumerate(c.rows):
            previous = c.vendor
            c.vendor = next(v for v in c.tables['vendors'] if v['vendor_id'] == row['vendor_id'])
            fixture.bind_request_rows(c, [row], request_id=f'REQ_{index}', po_id=f'PO_{index}')
            c.vendor = previous
        result = c.score()
        self.assertFalse(operational_members(result))
        self.assertEqual(self.queue(c, result)[0], [])

    def test_missing_obligation_sources_do_not_suppress_admission(self):
        c = self.case()
        self.assertFalse(c.tables['payment_requests'])
        cases, _ = self.queue(c)
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(self.members(cases)), 3)

    def test_calendar_month_is_part_of_identity(self):
        c = self.case(count=3)
        c.at = parse('2025-09-01T11:00:00+07:00')
        for index, vendor in enumerate(c.tables['vendors'][16:19]):
            c.pay(c.at+timedelta(days=index), 17_000_000, vendor=vendor, invoice_number=f'SEP_{index}', invoice_gross_vnd=17_000_000)
        cases, _ = self.queue(c)
        patterns = [row for row in cases if row['case_type'] == 'pattern']
        self.assertEqual({json.loads(row['pattern_scope'])['period'] for row in patterns}, {'2025-08', '2025-09'})
        self.assertEqual(len({row['case_id'] for row in patterns}), 2)

    def test_rolling_policy_requires_a_separate_trial_design(self):
        c = self.case()
        c.config['near_period'] = 'rolling_30d'
        with self.assertRaisesRegex(ValueError, 'calendar-month'):
            self.queue(c)

    def test_full_31_day_month_does_not_split_the_pattern_after_30_days(self):
        c = self.case(count=0)
        c.at = parse('2025-08-01T08:00:00+07:00')
        for index, vendor in enumerate(c.tables['vendors'][12:15]):
            c.pay(c.at, 17_000_000, vendor=vendor, invoice_number=f'FIRST_{index}', invoice_gross_vnd=17_000_000)
        c.pay(parse('2025-08-31T18:00:00+07:00'), 17_000_000, vendor=c.tables['vendors'][19],
              invoice_number='MONTH_END', invoice_gross_vnd=17_000_000)
        cases, _ = self.queue(c)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['case_type'], 'pattern')
        self.assertEqual(len(self.members(cases)), 4)

    def test_different_makers_have_separate_pattern_ids(self):
        c = self.case(count=6)
        for row in c.rows[3:]:
            row['creator_id'] = c.tables['employees'][3]['employee_id']
        cases, _ = self.queue(c)
        self.assertEqual(len(cases), 2)
        self.assertEqual(len({json.loads(row['pattern_scope'])['maker_id'] for row in cases}), 2)

    def test_future_employee_revision_cannot_change_pattern_or_owner(self):
        c = self.case()
        before = self.queue(c)
        chief = next(row for row in c.tables['employees'] if row['company_id'] == 'C001' and row['role'] == 'chief_accountant')
        c.tables['employees'].append(dict(chief, recorded_at='2026-01-01T00:00:00+07:00', full_name='Future name'))
        self.assertEqual(before, self.queue(c))

    def test_source_and_evidence_order_do_not_change_pattern_identity(self):
        c = self.case()
        result = c.score()
        before = self.queue(c, result)
        for key in ('scores', 'hits', 'batch_events'):
            result[key].reverse()
        for key in ('transactions', 'employees', 'vendors'):
            c.tables[key].reverse()
        self.assertEqual(before, self.queue(c, result))

    def test_same_pattern_id_but_growing_scope_cannot_inherit_feedback(self):
        c = self.case(count=3)
        before = self.queue(c)[0][0]
        c.pay(c.at+timedelta(days=4), 17_000_000, vendor=c.tables['vendors'][19], invoice_number='MORE', invoice_gross_vnd=17_000_000)
        after = self.queue(c)[0][0]
        self.assertEqual(before['case_id'], after['case_id'])
        self.assertFalse(equivalent(before, after))
        self.assertNotEqual(scope_hash(before), scope_hash(after))

    def test_unknown_queue_policy_is_rejected(self):
        c = self.case()
        with self.assertRaisesRegex(ValueError, 'queue policy'):
            review_queue(c.score(), c.tables, policy='unknown')

    def persist(self, root, c, result, queue):
        data, report = root/'data/sme_fraud_003', root/'reports/sme_fraud_003'
        data.mkdir(parents=True, exist_ok=True)
        report.mkdir(parents=True, exist_ok=True)
        for name in ('companies', 'employees', 'vendors', 'customers', 'transactions', 'journal_documents', 'journal_lines'):
            fields = list(dict.fromkeys(key for row in c.tables[name] for key in row))
            write_csv(data/f'{name}.csv', c.tables[name], fields)
        cases, events = queue
        write_csv(report/'case_queue.csv', cases)
        write_csv(report/'case_events.csv', events)
        write_jsonl(report/'rule_hits.jsonl', result['hits'])
        write_jsonl(report/'batch_events.jsonl', result['batch_events'])
        (report/'rule_coverage.json').write_text(json.dumps(result['coverage']), encoding='utf-8')
        return data, report

    def test_cache_loads_all_context_and_keeps_bank_obligations_separate(self):
        c = self.case()
        result = c.score()
        queue = self.queue(c, result)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, report = self.persist(root, c, result, queue)
            store = ReviewStore(data.parent, report.parent, root/'review.sqlite3', scenarios=['003'])
            store.prepare()
            detail = store.detail('003', queue[0][0]['case_id'])
            self.assertEqual(len(detail['transactions']), 3)
            self.assertEqual(len(detail['context_transactions']), 2)
            self.assertEqual(len({row['recipient_bank_code'] for row in [*detail['transactions'], *detail['context_transactions']]}), 5)
            self.assertNotIn('is_fraud', json.dumps(detail))
            store.prepare()

    def test_cache_loads_batch_pattern(self):
        c = self.case(count=3, same_time=True)
        result = c.score()
        queue = self.queue(c, result)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, report = self.persist(root, c, result, queue)
            store = ReviewStore(data.parent, report.parent, root/'review.sqlite3', scenarios=['003'])
            store.prepare()
            self.assertTrue(store.detail('003', queue[0][0]['case_id'])['batch_events'])

    def test_pattern_merge_does_not_transfer_old_decision_or_assignment(self):
        c = self.case()
        result = c.score()
        baseline = review_queue(result, c.tables)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, report = self.persist(root, c, result, baseline)
            store = ReviewStore(data.parent, report.parent, root/'review.sqlite3', scenarios=['003'])
            store.prepare()
            old_id = baseline[0][0]['case_id']
            store.save_feedback('003', old_id, 'false_positive', 'QA', 'Old scope only', '')
            original_audit = (report/'feedback_audit.jsonl').read_bytes()
            with store.connection() as db:
                row = json.loads(db.execute('SELECT data FROM cases WHERE scenario=? AND case_id=?', ('003', old_id)).fetchone()[0])
                row['owner_id'] = 'OLD_ASSIGNED_OWNER'
                db.execute('UPDATE cases SET data=? WHERE scenario=? AND case_id=?', (json.dumps(row), '003', old_id))
            trial = self.queue(c, result)
            self.persist(root, c, result, trial)
            store.prepare()
            detail = store.detail('003', trial[0][0]['case_id'])
            self.assertEqual(detail['case']['status'], 'new')
            self.assertTrue(detail['case']['requires_rereview'])
            self.assertNotEqual(detail['case']['owner_id'], 'OLD_ASSIGNED_OWNER')
            self.assertFalse(load_lineage(report)['aliases'])
            self.assertEqual((report/'feedback_audit.jsonl').read_bytes(), original_audit)

    def test_tampered_pattern_context_is_rejected_before_cache_commit(self):
        c = self.case()
        result = c.score()
        queue = self.queue(c, result)
        queue[0][0]['pattern_context_ids'] = '[]'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, report = self.persist(root, c, result, queue)
            store = ReviewStore(data.parent, report.parent, root/'review.sqlite3', scenarios=['003'])
            with self.assertRaisesRegex(ValueError, 'pattern evidence'):
                store.prepare()


if __name__ == '__main__':
    unittest.main()
