"""Stable as-of case identity and preservation of human review state."""
import copy
import json
import csv
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta

from sme_fraud.case_queue import review_queue
from sme_fraud.generate import stamp
from sme_fraud.generate import write_csv
from sme_fraud.case_identity import component_key, load_lineage, plan_lineage, scope_hash
from sme_fraud.feedback import event_hash, read_audit, record_feedback
from sme_fraud.review_store import ReviewStore
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import KnownGraph
from test_review import make_fixture


class CaseIdentityTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        return case

    def linked(self):
        case = self.case()
        vendors = case.shared_vendors()
        for vendor in vendors:
            vendor['recorded_at'] = stamp(case.at - timedelta(days=5))
        for index, vendor in enumerate(vendors[:2]):
            case.pay(case.at + timedelta(days=index), 9_000_000, vendor=vendor)
        return case

    def test_reordered_sources_preserve_scores_hits_cases_and_events(self):
        case = self.linked()
        before = case.score()
        cases, events = review_queue(before, case.tables)
        for name in ('vendors', 'employees', 'entity_links'):
            case.tables[name].reverse()
        case.rows.reverse()
        after = case.score()
        after_cases, after_events = review_queue(after, case.tables)
        self.assertEqual(after['scores'], before['scores'])
        self.assertEqual(after['hits'], before['hits'])
        self.assertEqual((after_cases, after_events), (cases, events))

    def test_owner_selection_is_independent_of_employee_source_order(self):
        case = self.linked()
        chief = next(e for e in case.tables['employees'] if e['role'] == 'chief_accountant')
        case.tables['employees'].append(dict(chief, employee_id='SECOND_CHIEF'))
        before = review_queue(case.score(), case.tables)[0]
        case.tables['employees'].reverse()
        after = review_queue(case.score(), case.tables)[0]
        self.assertEqual([c['owner_id'] for c in before], [c['owner_id'] for c in after])

    def test_future_sources_do_not_change_past_case_identity(self):
        case = self.linked()
        before = case.score()
        queue = review_queue(before, case.tables)
        case.tables['vendors'].append(dict(case.vendor, recorded_at=stamp(case.at + timedelta(days=20)), phone='FUTURE_PHONE'))
        after = case.score()
        self.assertEqual(before['scores'], after['scores'])
        self.assertEqual(queue, review_queue(after, case.tables))

    def test_duplicate_sources_and_same_time_transactions_are_order_invariant(self):
        case = self.linked()
        case.rows[1]['posted_at'] = case.rows[0]['posted_at']
        before = case.score()
        queue = review_queue(before, case.tables)
        case.tables['vendors'] += copy.deepcopy(case.tables['vendors'])
        case.tables['entity_links'] += copy.deepcopy(case.tables['entity_links'])
        case.rows.reverse()
        after = case.score()
        self.assertEqual(before['scores'], after['scores'])
        self.assertEqual(before['batch_events'], after['batch_events'])
        self.assertEqual(queue, review_queue(after, case.tables))

    def test_component_key_tracks_membership_independently_of_root_and_contact_values(self):
        graph = KnownGraph()
        graph.replace('C001', 'entity:V1', 'phone:OLD', '2025-01-01', 'phone')
        first, members = graph.identity('C001', 'entity:V1')
        graph.replace('C001', 'entity:V1', 'phone:NEW', '2025-01-02', 'phone')
        self.assertEqual((first, members), graph.identity('C001', 'entity:V1'))
        graph.replace('C001', 'entity:V2', 'phone:NEW', '2025-01-02', 'phone')
        joined, members = graph.identity('C001', 'entity:V1')
        self.assertNotEqual(joined, first)
        self.assertEqual(members, ('entity:V1', 'entity:V2'))
        graph.replace('C001', 'entity:V2', '', '2025-01-03', 'phone')
        self.assertEqual(graph.identity('C001', 'entity:V1')[0], first)
        self.assertNotEqual(graph.identity('C001', 'entity:V2')[0], first)

    def test_component_identity_is_company_scoped(self):
        self.assertNotEqual(component_key('C001', ['entity:V1']), component_key('C002', ['entity:V1']))

    def test_latest_role_at_opening_controls_default_owner(self):
        case = self.linked()
        chief = next(e for e in case.tables['employees'] if e['role'] == 'chief_accountant')
        case.tables['employees'].append(dict(chief, recorded_at=stamp(case.at - timedelta(days=1)), role='operations'))
        self.assertTrue(all(not c['owner_id'] for c in review_queue(case.score(), case.tables)[0]))
        case.tables['employees'].append(dict(chief, recorded_at=stamp(case.at + timedelta(days=20))))
        self.assertTrue(all(not c['owner_id'] for c in review_queue(case.score(), case.tables)[0]))


class CaseMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data, self.report = make_fixture(self.root)
        self.now = '2026-10-16T10:00:00+07:00'
        from datetime import datetime
        self.store = ReviewStore(self.root / 'data', self.root / 'reports', self.root / 'cache.sqlite3',
                                 clock=lambda: datetime.fromisoformat(self.now))
        self.store.prepare()

    def tearDown(self):
        self.temporary.cleanup()

    def cases(self):
        with (self.report / 'case_queue.csv').open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))

    def rename(self, old='RC_1', new='RC_CANONICAL'):
        cases = self.cases()
        for row in cases:
            if row['case_id'] == old:
                row.update(case_id=new, entity='cluster:CANONICAL', identity_version='component-members-v1',
                           cluster_members='["entity:V01"]', owner_id='NEW_DEFAULT')
        write_csv(self.report / 'case_queue.csv', cases)

    def test_equivalent_legacy_rename_preserves_feedback_owner_and_admission(self):
        event = self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Need invoice', '')
        original = (self.report / 'feedback_audit.jsonl').read_bytes()
        self.rename()
        self.store.prepare()
        detail = self.store.detail('003', 'RC_CANONICAL')
        self.assertEqual(detail['case']['status'], 'awaiting_information')
        self.assertEqual(detail['case']['owner_id'], 'E01')
        self.assertEqual(detail['case']['feedback']['event_hash'], event['event_hash'])
        self.assertEqual(self.store.detail('003', 'RC_1')['case']['case_id'], 'RC_CANONICAL')
        self.assertTrue(detail['feedback_history'][0]['applies_to_current_scope'])
        self.assertEqual((self.report / 'feedback_audit.jsonl').read_bytes(), original)
        admitted, used, _ = self.store.admissions('003')
        self.assertIn('RC_CANONICAL', admitted)
        self.assertNotIn('RC_1', admitted)
        self.assertEqual(used['C001'], 1)
        with (self.report / 'case_review_states.csv').open(encoding='utf-8-sig', newline='') as stream:
            projected = {r['case_id']: r for r in csv.DictReader(stream)}
        self.assertEqual(projected['RC_CANONICAL']['status'], 'awaiting_information')
        self.assertNotIn('RC_1', projected)

    def test_legacy_feedback_without_scope_hash_is_bound_to_cached_snapshot(self):
        event = dict(case_id='RC_1', decision='false_positive', reviewer='QA', reason='Checked',
                     reviewed_at=self.now, previous_hash='')
        event['event_hash'] = event_hash(event)
        (self.report / 'feedback_audit.jsonl').write_text(json.dumps(event) + '\n', encoding='utf-8')
        self.rename()
        self.store.prepare()
        self.assertEqual(self.store.detail('003', 'RC_CANONICAL')['case']['status'], 'closed')
        self.assertEqual(read_audit(self.report / 'feedback_audit.jsonl'), [event])

    def test_alias_feedback_stays_optimistic_and_cli_uses_canonical_id(self):
        event = self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Need invoice', '')
        self.rename()
        self.store.prepare()
        with self.assertRaises(RuntimeError):
            self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked', '')
        saved = self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked', event['event_hash'])
        self.assertEqual(saved['case_id'], 'RC_CANONICAL')
        saved = record_feedback(self.report, 'RC_1', 'information_gap', 'CLI', 'More proof', self.now)
        self.assertEqual(saved['case_id'], 'RC_CANONICAL')
        self.assertEqual(len(self.store.detail('003', 'RC_1')['feedback_history']), 3)

    def test_repeated_prepare_and_restart_do_not_duplicate_work_or_change_owner(self):
        self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Need invoice', '')
        self.rename()
        self.store.prepare()
        self.store.prepare()
        self.store.prepare()
        self.assertEqual(self.store.admissions('003')[1]['C001'], 1)
        restarted = ReviewStore(self.root / 'data', self.root / 'reports', self.root / 'cache.sqlite3', clock=self.store.clock)
        restarted.prepare()
        self.assertEqual(restarted.detail('003', 'RC_CANONICAL')['case']['owner_id'], 'E01')
        self.assertEqual(restarted.detail('003', 'RC_CANONICAL')['case']['status'], 'awaiting_information')

    def test_changed_evidence_does_not_inherit_old_closure_even_with_same_id(self):
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked old evidence', '')
        path = self.report / 'rule_hits.jsonl'
        hits = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        next(h for h in hits if h['transaction_id'] == 'T1')['evidence']['new_source'] = 'Changed evidence'
        path.write_text(''.join(json.dumps(h) + '\n' for h in hits), encoding='utf-8')
        self.store.prepare()
        detail = self.store.detail('003', 'RC_1')
        self.assertEqual(detail['case']['status'], 'new')
        self.assertIsNone(detail['case']['feedback'])
        self.assertEqual(detail['case']['requires_rereview'], 1)
        self.assertFalse(detail['feedback_history'][0]['applies_to_current_scope'])
        self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Review changed source', '')

    def test_merge_keeps_parent_histories_without_transferring_closures_or_work(self):
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked first', '')
        self.store.save_feedback('003', 'RC_2', 'information_gap', 'QA', 'Need second', '')
        cases = self.cases()
        first = next(r for r in cases if r['case_id'] == 'RC_1')
        second = next(r for r in cases if r['case_id'] == 'RC_2')
        merged = dict(first, case_id='RC_MERGED', transaction_ids='["T1","T2"]', observation_count=2,
                      last_seen_at=second['last_seen_at'], owner_id='MERGE_OWNER')
        write_csv(self.report / 'case_queue.csv', [r for r in cases if r['case_id'] not in {'RC_1', 'RC_2'}] + [merged])
        self.store.prepare()
        detail = self.store.detail('003', 'RC_MERGED')
        self.assertEqual(detail['case']['status'], 'new')
        self.assertEqual(detail['case']['owner_id'], 'MERGE_OWNER')
        self.assertEqual({r['case_id'] for r in detail['related_feedback_history']}, {'RC_1', 'RC_2'})
        self.assertEqual({r['relation'] for r in detail['case_lineage']}, {'merged'})
        self.assertNotIn('RC_MERGED', self.store.admissions('003')[0])
        self.assertTrue(self.store.detail('003', 'RC_1')['case']['archived'])
        with self.assertRaises(KeyError):
            self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Cannot edit archive', '')

    def test_split_preserves_old_summary_and_requires_independent_new_reviews(self):
        cases = self.cases()
        first = next(r for r in cases if r['case_id'] == 'RC_1')
        second = next(r for r in cases if r['case_id'] == 'RC_2')
        combined = dict(first, transaction_ids='["T1","T2"]', observation_count=2, last_seen_at=second['last_seen_at'])
        rest = [r for r in cases if r['case_id'] not in {'RC_1', 'RC_2'}]
        write_csv(self.report / 'case_queue.csv', rest + [combined])
        self.store.prepare()
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked old combined scope', '')
        write_csv(self.report / 'case_queue.csv', rest + [dict(first, case_id='RC_CHILD_A'), dict(second, case_id='RC_CHILD_B')])
        self.store.prepare()
        for identity in ('RC_CHILD_A', 'RC_CHILD_B'):
            detail = self.store.detail('003', identity)
            self.assertEqual(detail['case']['status'], 'new')
            self.assertEqual(detail['related_feedback_history'][0]['case_id'], 'RC_1')
            self.assertEqual(detail['case_lineage'][0]['relation'], 'split')
        self.assertTrue(self.store.detail('003', 'RC_1')['case']['archived'])

    def test_queue_change_cannot_silently_use_stale_mapping(self):
        self.rename()
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Stale browser', '')

    def test_failed_refresh_keeps_previous_mapping_and_cache(self):
        before = (self.report / 'case_identity.json').read_bytes()
        self.rename()
        path = self.report / 'rule_hits.jsonl'
        hit = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
        hit['related_transaction_ids'] = ['MISSING_SOURCE']
        path.write_text(json.dumps(hit) + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Missing evidence transaction'):
            self.store.prepare()
        self.assertEqual((self.report / 'case_identity.json').read_bytes(), before)
        with self.store.connection() as db:
            self.assertIsNotNone(db.execute("SELECT case_id FROM cases WHERE case_id='RC_1'").fetchone())

    def test_master_revisions_load_independently_of_row_order(self):
        path = self.data / 'employees.csv'
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows.append(dict(rows[0], recorded_at='2025-01-01T00:00:00+07:00', full_name='Later display name'))
        write_csv(path, list(reversed(rows)))
        self.store.prepare()
        self.assertEqual(self.store.detail('003', 'RC_1')['case']['owner_name'], 'Later display name')

    def test_cross_company_and_ambiguous_matches_are_not_aliased(self):
        state = load_lineage(self.report)
        old = state['current']['RC_1']
        other = dict(old, case_id='OTHER', company_id='C002')
        migrated, pairs = plan_lineage([old], [other], state, [], 'test')
        self.assertEqual(pairs, [])
        self.assertNotIn('RC_1', migrated['aliases'])
        a, b = dict(old, case_id='A'), dict(old, case_id='B')
        _, pairs = plan_lineage([old], [a, b], state, [], 'test')
        self.assertEqual(pairs, [])

    def test_context_transaction_change_invalidates_previous_review(self):
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked context', '')
        path = self.data / 'transactions.csv'
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        next(r for r in rows if r['transaction_id'] == 'T0')['amount_vnd'] = 99_000_000
        write_csv(path, rows)
        self.store.prepare()
        self.assertEqual(self.store.detail('003', 'RC_1')['case']['status'], 'new')
        item = next(r for r in self.store.list_cases('003')['items'] if r['case_id'] == 'RC_1')
        self.assertEqual(item['requires_rereview'], 1)

    def test_journal_evidence_change_invalidates_previous_review(self):
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'QA', 'Checked journal', '')
        path = self.data / 'journal_lines.csv'
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        next(r for r in rows if r['document_id'] == 'J1')['debit_vnd'] = 99_000_000
        write_csv(path, rows)
        self.store.prepare()
        self.assertEqual(self.store.detail('003', 'RC_1')['case']['status'], 'new')

    def test_missing_mapping_is_reported_instead_of_losing_alias_history(self):
        self.store.save_feedback('003', 'RC_1', 'information_gap', 'QA', 'Need invoice', '')
        self.rename()
        self.store.prepare()
        (self.report / 'case_identity.json').unlink()
        with self.assertRaisesRegex(ValueError, 'mapping missing'):
            self.store.prepare()
        with self.assertRaisesRegex(ValueError, 'mapping missing'):
            self.store.list_cases('003')

    def test_engine_reorder_and_reload_preserve_human_state(self):
        case = CaseIdentityTest().linked()

        def publish(result, cases, events):
            for name in ('companies', 'employees', 'vendors', 'transactions', 'journal_documents', 'journal_lines'):
                write_csv(self.data / f'{name}.csv', case.tables[name])
            write_csv(self.report / 'case_queue.csv', cases)
            write_csv(self.report / 'case_events.csv', events)
            (self.report / 'rule_hits.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in result['hits']), encoding='utf-8')
            (self.report / 'batch_events.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in result['batch_events']), encoding='utf-8')

        result = case.score()
        cases, events = review_queue(result, case.tables)
        self.assertEqual(len(cases), 1)
        legacy = dict(cases[0], case_id='RC_LEGACY_ENGINE', entity='entity:V0000015')
        for field in ('identity_version', 'cluster_members', 'scope_hash'):
            legacy.pop(field)
        publish(result, [legacy], [dict(r, case_id=legacy['case_id']) for r in events])
        self.store.prepare()
        event = self.store.save_feedback('003', legacy['case_id'], 'information_gap', 'QA', 'Check engine case', '')
        original = (self.report / 'feedback_audit.jsonl').read_bytes()
        for name in ('vendors', 'employees', 'entity_links'):
            case.tables[name].reverse()
        case.rows.reverse()
        after = case.score()
        canonical, events = review_queue(after, case.tables)
        publish(after, canonical, events)
        self.store.prepare()
        detail = self.store.detail('003', legacy['case_id'])
        self.assertEqual(detail['case']['case_id'], canonical[0]['case_id'])
        self.assertEqual(detail['case']['owner_id'], legacy['owner_id'])
        self.assertEqual(detail['case']['feedback']['event_hash'], event['event_hash'])
        self.assertEqual(detail['case']['status'], 'awaiting_information')
        self.assertEqual(self.store.admissions('003')[1]['C001'], 1)
        self.assertEqual((self.report / 'feedback_audit.jsonl').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
