"""Same-budget shadow comparison must preserve chronology, safety slots and unknown outcomes."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_train_source_model as fixtures
from sme_fraud.compare_shadow import (case_score, shadow_order, select, simulation, source_work_scope,
                                      prepare_case, run_comparison, load_baseline)
from sme_fraud.shadow_scoring import instant
from sme_fraud.review_capacity import ReviewCapacity
from sme_fraud.feature_contract import cache_contract, sha
from sme_fraud.generate import write_csv
from sme_fraud.case_queue import review_queue


def case(name, score=10, if_score=.5, *, priority='trung_binh', kind='transaction', minutes=20, version='one'):
    return dict(case_id=name, company_id='C001', opened_at='2025-07-01T10:00:00+07:00',
        last_seen_at='2025-07-01T10:00:00+07:00', priority=priority, max_score=score, case_type=kind,
        source_scope='', source_status='', transaction_ids=json.dumps([name]) if kind == 'transaction' else '[]',
        rule_ids='P2', estimated_minutes=minutes, requires_rereview=0, rereview_due_at='',
        if_score=if_score if kind == 'transaction' else None,
        if_coverage='full' if if_score is not None and kind == 'transaction' else 'missing_or_partial',
        member_count=int(kind == 'transaction'), work_scope=name+version, base_work_key=name+version,
        production_scope_hash='PROD_'+name+version)


def task(row):
    return dict(case=row, key=row['base_work_key'], minutes=row['estimated_minutes'],
                ready=date(2025, 7, 1), work_type='initial_review')


def snapshots(rows_by_day):
    return [dict(day=date(2025, 7, 1)+timedelta(days=i),
                 cutoff=(date(2025, 7, 2)+timedelta(days=i)).isoformat()+'T00:00:00+07:00',
                 companies=['C001'], cases=rows) for i, rows in enumerate(rows_by_day)]


class CompareShadowTest(unittest.TestCase):
    def test_priority_is_preserved_and_missing_score_positions_are_anchored(self):
        rows = [case('A', 20, .1), case('B', 19, None), case('C', 18, .9),
                case('HIGH', 14, .01, priority='cao')]
        self.assertEqual([t['case']['case_id'] for t in shadow_order([task(c) for c in rows])],
                         ['HIGH', 'C', 'B', 'A'])

    def test_if_ties_keep_the_baseline_order(self):
        rows = [case('Z', 10, .8), case('A', 11, .8), case('B', 10, .8)]
        self.assertEqual([t['case']['case_id'] for t in shadow_order([task(c) for c in rows])], ['A', 'B', 'Z'])

    def test_case_and_minute_limits_are_independent(self):
        rows = [case(name, 20-i, .5, minutes=m) for i, (name, m) in enumerate(zip('ABCDE', (45,45,45,20,15)))]
        chosen = select([task(c) for c in rows], ReviewCapacity.ui(5))
        self.assertEqual([t['case']['case_id'] for t in chosen], ['A','B','D'])
        self.assertEqual(sum(t['minutes'] for t in chosen), 110)
        self.assertEqual(len(select([task(c) for c in rows], ReviewCapacity(1,120))), 1)

    def test_same_scope_is_not_reviewed_again_and_backlog_carries_to_next_day(self):
        rows = [case(str(i), 20-i, float(i)) for i in range(7)]
        result = simulation(snapshots([rows, rows, rows]), 5)
        for arm in ('baseline', 'if_shadow'):
            selected = [r for r in result['selections'] if r['arm'] == arm]
            self.assertEqual(len(selected), 7)
            self.assertEqual(len({r['work_key'] for r in selected}), 7)
            self.assertEqual(result['summary']['arms'][arm]['backlog_at_end'], 0)
        self.assertEqual(result['summary']['company_days_with_changed_selection'], 2)
        self.assertIsNone(result['summary']['actionable_gain'])
        self.assertEqual(result['summary']['independent_reviews'], 0)

    def test_hard_and_nontransaction_baseline_selections_are_pinned(self):
        hard = case('H', 21, .01, priority='cao_nhat')
        source = case('S', 15, None, kind='source')
        rows = [hard, source]+[case(str(i), 14-i, float(i)) for i in range(6)]
        result = simulation(snapshots([rows]), 5)
        for arm in ('baseline', 'if_shadow'):
            selected = [r for r in result['selections'] if r['arm'] == arm]
            self.assertTrue({'H','S'} <= {r['case_id'] for r in selected})
            self.assertEqual(selected[0]['case_id'], 'H')
        self.assertEqual(result['summary']['mandatory_displacements'], 0)
        self.assertEqual(result['summary']['mandatory_selected_scopes_pinned'], 2)

    def test_mandatory_overflow_is_recorded_without_breaking_capacity(self):
        rows = [case(str(i), 25-i, .5, priority='cao_nhat', minutes=45) for i in range(5)]
        result = simulation(snapshots([rows]), 5)
        self.assertEqual(result['summary']['arms']['baseline']['selected'], 2)
        self.assertEqual(result['summary']['arms']['baseline']['mandatory_overflow'], 3)
        self.assertEqual(result['summary']['budget_violations'], 0)

    def test_unselected_scope_updates_and_withdrawals_are_not_counted_as_reviews(self):
        hard = [case('H'+str(i), 25-i, .5, priority='cao_nhat', minutes=45) for i in range(2)]
        old = case('A', minutes=45)
        changed = case('A', minutes=45, version='two')
        result = simulation(snapshots([hard+[old], hard+[changed], hard]), 5)
        for arm in ('baseline', 'if_shadow'):
            self.assertEqual(result['summary']['arms'][arm]['superseded_unreviewed_scopes'], 1)
            # Changed A fits after the two hard cases were reviewed the prior day.
            self.assertEqual(result['summary']['arms'][arm]['selected'], 3)

    def test_selected_review_order_still_respects_priority_when_low_slots_are_pinned(self):
        high = task(case('HIGH', priority='cao'))
        low = task(case('LOW', kind='source', priority='thap'))
        selected = select([high, low], ReviewCapacity.ui(5), pins=[low], shadow=True)
        self.assertEqual([t['case']['case_id'] for t in selected], ['HIGH','LOW'])

    def test_changed_review_scope_requires_a_new_continued_review(self):
        a = case('A')
        changed = case('A', version='two', minutes=45)
        result = simulation(snapshots([[a], [changed], [changed]]), 5)
        for arm in ('baseline', 'if_shadow'):
            selected = [r for r in result['selections'] if r['arm'] == arm]
            self.assertEqual([r['estimated_minutes'] for r in selected], [20,23])
            self.assertEqual(selected[1]['work_type'], 'continued_review')

    def test_source_clock_only_updates_do_not_create_new_work_evidence_changes_do(self):
        row = case('S', kind='source')
        one = dict(signal=True, evidence=dict(overdue_days=61, outstanding_vnd=100))
        two = dict(signal=True, evidence=dict(overdue_days=62, outstanding_vnd=100))
        self.assertEqual(source_work_scope(row, one), source_work_scope(row, two))
        two['evidence']['outstanding_vnd'] = 50
        self.assertNotEqual(source_work_scope(row, one), source_work_scope(row, two))

    def test_information_gap_has_one_scheduled_rereview_and_no_automatic_outcome(self):
        row = case('S', kind='source')
        row.update(source_status='information_gap', requires_rereview=1, rereview_due_at='2025-07-02T09:00:00+07:00')
        result = simulation(snapshots([[row],[row],[row],[row]]), 5)
        for arm in ('baseline', 'if_shadow'):
            selected = [r for r in result['selections'] if r['arm'] == arm]
            self.assertEqual(len(selected), 2)
            self.assertTrue(all(r['awaiting_information'] for r in selected))
            self.assertEqual(selected[-1]['work_type'], 'scheduled_rereview')

    def test_unknown_or_future_case_members_are_rejected_not_filled_with_zero(self):
        row = case('A')
        txs = dict(A=dict(posted_at='2025-07-02T00:00:00+07:00'))
        with self.assertRaisesRegex(ValueError, 'future'):
            case_score(row, dict(A=.9), txs, instant('2025-07-02T00:00:00+07:00'))
        txs['A']['posted_at'] = '2025-07-01T10:00:00+07:00'
        result = case_score(row, {}, txs, instant('2025-07-02T00:00:00+07:00'))
        self.assertIsNone(result['if_score'])
        self.assertEqual(result['if_coverage'], 'missing_or_partial')

    def fixture(self):
        f = fixtures.TrainSourceModelTest(); f.setUp(); self.addCleanup(f.tearDown)
        employees = f.dataset/'employees.csv'
        write_csv(employees, [], ['employee_id','company_id','recorded_at','role'])
        f.metadata.update(is_synthetic=True)
        f.metadata['files']['employees.csv'] = dict(sha256=sha(employees))
        f.metadata['feature_contract'] = cache_contract(f.metadata['files'])
        f.save_metadata()
        trained = f.train()
        parent = f.root/'baseline'; parent.mkdir()
        baseline = parent/'sme_fraud_001'; baseline.mkdir()
        config = dict(enable_graph=True, amount_baseline='rolling_account', noise_policy='phase2',
                      split_pattern_policy='split_patterns_v1', operational_score=7)
        rows = [dict(transaction_id=r['transaction_id'], company_id=r['company_id'], posted_at=r['posted_at'],
                     rule_score=9 if r['transaction_id']=='T4' else 0, base_score=9 if r['transaction_id']=='T4' else 0,
                     recurrence_points=0, hard_trigger=0, operational_alert=int(r['transaction_id']=='T4'),
                     priority='trung_binh' if r['transaction_id']=='T4' else 'thap', admission_basis='score_threshold',
                     review_rule_ids='', case_entity='maker:'+r['transaction_id'], case_cluster_members='[]',
                     rule_ids='P2', explanation_vi='SIM_TEST') for r in f.transactions]
        result = dict(scores=rows, hits=[], batch_events=[], evidence_findings=[], config=config)
        cases, events = review_queue(result, dict(employees=[]))
        write_csv(baseline/'rule_scores.csv', rows)
        write_csv(baseline/'case_queue.csv', cases)
        write_csv(baseline/'case_events.csv', events)
        (baseline/'rule_config.json').write_text(json.dumps(config), encoding='utf-8')
        for name in ('rule_hits.jsonl','batch_events.jsonl','evidence_findings.jsonl'):
            (baseline/name).write_text('', encoding='utf-8')
        root = Path(__file__).resolve().parents[1]
        code_plan = dict(code_sha256={'sme_fraud/'+n: sha(root/'sme_fraud'/n) for n in
            ('case_queue.py','case_identity.py','case_admission.py','temporal_evidence.py','a4_pattern_queue.py')})
        (parent/'evaluation_plan.json').write_text(json.dumps(code_plan), encoding='utf-8')
        frozen = dict(files={p.name:sha(p) for p in baseline.iterdir()},
                      source_manifest_sha256=sha(f.dataset/'manifest.json'), plan_sha256=sha(parent/'evaluation_plan.json'))
        (baseline/'predictions_frozen.json').write_text(json.dumps(frozen), encoding='utf-8')
        scope = dict(company_ids=['C001'], source_ref='SIM_COMPARISON_TEST', **f.plan['evaluation'])
        return f, trained, baseline, scope

    def test_end_to_end_comparison_no_fit_no_labels_no_production_writes(self):
        f, trained, baseline, scope = self.fixture()
        before = {p: sha(p) for folder in (f.dataset, baseline, f.root/'model') for p in folder.iterdir()}
        original = Path.open
        def opened(path, *args, **kwargs):
            if path.name in {'labels.csv','splits.csv','oracle.json','control_oracle.jsonl'}:
                raise AssertionError('No labels/oracle')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened), patch('sklearn.ensemble.IsolationForest.fit', side_effect=AssertionError('No fit')):
            report = run_comparison(f.dataset, baseline, f.root/'model/isolation_forest.joblib', f.root/'comparison',
                                    model_sha256=trained['model_sha256'], scope=scope)
        self.assertEqual(report['shadow_rows'], 1)
        self.assertEqual(report['independent_reviews'], 0)
        self.assertIsNone(report['actionable_gain'])
        for row in report['summaries']:
            self.assertEqual(row['arms']['baseline']['selected'], 1)
            self.assertEqual(row['arms']['if_shadow']['selected'], 1)
            self.assertEqual(row['company_days_with_changed_selection'], 0)
        self.assertEqual(before, {p: sha(p) for p in before})
        packet = (f.root/'comparison/review_union.blind.csv').read_text(encoding='utf-8')
        self.assertNotIn('if_score', packet.splitlines()[0])
        self.assertNotIn('arm', packet.splitlines()[0])

    def test_modified_baseline_or_plan_is_rejected(self):
        f, _, baseline, _ = self.fixture()
        (baseline.parent/'evaluation_plan.json').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'plan checksum'):
            load_baseline(f.dataset, baseline)

    def test_changed_case_builder_requires_explicit_full_scope_reproduction(self):
        f, _, baseline, _ = self.fixture()
        path = baseline.parent/'evaluation_plan.json'
        plan = json.loads(path.read_text(encoding='utf-8'))
        plan['code_sha256']['sme_fraud/case_queue.py'] = 'SIM_OLD_BUILDER_HASH'
        path.write_text(json.dumps(plan), encoding='utf-8')
        commitment = json.loads((baseline/'predictions_frozen.json').read_text(encoding='utf-8'))
        commitment['plan_sha256'] = sha(path)
        (baseline/'predictions_frozen.json').write_text(json.dumps(commitment), encoding='utf-8')
        _, _, _, reconstruction = load_baseline(f.dataset, baseline)
        self.assertFalse(reconstruction['code']['case_queue.py']['unchanged'])
        self.assertTrue(reconstruction['frozen_final_scopes_reproduced'])
        saved = (baseline/'case_queue.csv').read_text(encoding='utf-8-sig')
        (baseline/'case_queue.csv').write_text(saved.replace('RC_', 'WRONG_'), encoding='utf-8')
        commitment['files']['case_queue.csv'] = sha(baseline/'case_queue.csv')
        (baseline/'predictions_frozen.json').write_text(json.dumps(commitment), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'does not reproduce'):
            load_baseline(f.dataset, baseline)

    def test_holdout_is_rejected_before_any_read(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('No holdout reads')):
            with self.assertRaisesRegex(ValueError, '005'):
                run_comparison(Path('sme_fraud_005'), Path('baseline'), Path('model'), Path('new'),
                               model_sha256='unused', scope={})


if __name__ == '__main__':
    unittest.main()
