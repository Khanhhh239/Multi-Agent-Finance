import copy
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.admission_export import explain_admissions
from sme_fraud.case_queue import review_queue
from sme_fraud.rule_audit_cases import Case
from sme_fraud.generate import write_csv
from sme_fraud.export_admissions import run
from sme_fraud.feature_contract import sha


class AdmissionExportTest(unittest.TestCase):
    def fixture(self, *, batch=False):
        case = Case()
        case.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        from datetime import timedelta
        for index in range(3):
            case.pay(case.at if batch else case.at+timedelta(days=5*index),
                17_000_000, kind='cash_expense', invoice_number=f'I{index}')
        result = case.score()
        cases, _ = review_queue(result, case.tables)
        return result, cases

    def test_row_a4_links_own_hit_and_leaves_numeric_observation_unchanged(self):
        result, cases = self.fixture()
        original = copy.deepcopy(result)
        identity = result['scores'][-1]['transaction_id']
        rows, proofs = explain_admissions(result, cases, {identity})
        row = rows[0]
        self.assertEqual(row['row_admission_basis'], 'split_pattern')
        self.assertEqual(row['effective_admission_basis'], 'split_pattern')
        self.assertEqual((row['rule_score'], row['row_hard_trigger']), (3, 0))
        self.assertEqual(row['admission_source'], 'row')
        self.assertTrue(proofs[0]['row_hits'])
        self.assertEqual(json.loads(row['batch_event_ids']), [])
        self.assertEqual(result, original)

    def test_zero_score_batch_participants_get_a4_provenance(self):
        result, cases = self.fixture(batch=True)
        ids = {row['transaction_id'] for row in result['scores']}
        rows, proofs = explain_admissions(result, cases, ids, source_directory='../frozen')
        self.assertEqual(len(rows), 3)
        for row, proof in zip(rows, proofs):
            self.assertEqual((row['rule_score'], row['row_operational_alert'], row['row_hard_trigger']), (0, 0, 0))
            self.assertEqual(row['row_admission_basis'], '')
            self.assertEqual(row['row_review_rule_ids'], '')
            self.assertEqual(row['effective_admission_basis'], 'split_pattern')
            self.assertEqual(row['effective_review_rule_ids'], 'A4')
            self.assertEqual(row['event_rule_ids'], 'A4')
            self.assertEqual(row['admission_source'], 'batch_closed')
            self.assertEqual(proof['row_hits'], [])
            self.assertTrue(proof['batch_events'][0]['direct_participant'])
            self.assertEqual(proof['batch_events'][0]['source']['path'], '../frozen/batch_events.jsonl')
            self.assertTrue(row['admission_evidence_ref'].endswith(proof['admission_evidence_id']))

    def test_context_and_unrelated_case_events_cannot_supply_admission(self):
        result, cases = self.fixture(batch=True)
        event = result['batch_events'][0]
        other = copy.deepcopy(event)
        other.update(event_id='UNRELATED', rule_id='A2', transaction_ids=[], related_transaction_ids=[result['scores'][0]['transaction_id']])
        result['batch_events'].append(other)
        cases[0]['batch_event_ids'] = json.dumps([event['event_id'], 'UNRELATED'])
        cases[0]['rule_ids'] = 'A2|A4|P1'
        rows, proofs = explain_admissions(result, cases, {result['scores'][0]['transaction_id']})
        self.assertEqual(rows[0]['event_rule_ids'], 'A4')
        self.assertNotIn('UNRELATED', json.loads(rows[0]['batch_event_ids']))

    def test_disabling_split_policy_removes_batch_eligibility(self):
        result, _ = self.fixture(batch=True)
        result['config']['split_pattern_policy'] = 'disabled'
        with self.assertRaisesRegex(ValueError, 'not operationally admitted'):
            explain_admissions(result, [], {result['scores'][0]['transaction_id']})

    def test_context_only_id_is_not_a_new_member(self):
        result, cases = self.fixture(batch=True)
        context = copy.deepcopy(result['scores'][0])
        context.update(transaction_id='CONTEXT_ONLY', posted_at='2024-01-01T00:00:00+07:00')
        result['scores'].append(context)
        result['batch_events'][0]['related_transaction_ids'].append('CONTEXT_ONLY')
        with self.assertRaisesRegex(ValueError, 'not operationally admitted'):
            explain_admissions(result, cases, {'CONTEXT_ONLY'})

    def test_suppressed_zero_point_batch_event_is_not_an_admission_reason(self):
        result, cases = self.fixture(batch=True)
        suppressed = dict(result['batch_events'][0], event_id='SUPPRESSED', rule_id='A2',
            points=0, suppressed_reason='Approved obligation', signal=False)
        result['batch_events'].append(suppressed)
        rows, _ = explain_admissions(result, cases, {result['scores'][0]['transaction_id']})
        self.assertEqual(rows[0]['event_rule_ids'], 'A4')

    def test_row_and_batch_bases_are_both_visible_without_rewriting_hard_flag(self):
        result, cases = self.fixture(batch=True)
        row = result['scores'][0]
        row.update(operational_alert=1, admission_basis='score_threshold', rule_score=8, rule_ids='A1')
        result['hits'].append(dict(transaction_id=row['transaction_id'], company_id=row['company_id'],
            detected_at=row['posted_at'], rule_id='A1', points=8, evidence_id='ROW_HIT', evidence={}))
        rows, proof = explain_admissions(result, cases, {row['transaction_id']})
        self.assertEqual(rows[0]['effective_admission_basis'], 'score_threshold|split_pattern')
        self.assertEqual(rows[0]['admission_source'], 'row|batch_closed')
        self.assertEqual(rows[0]['row_hard_trigger'], 0)
        self.assertEqual(len(proof[0]['row_hits']), 1)

    def test_transitive_batch_component_explains_other_event_participants(self):
        result, cases = self.fixture(batch=True)
        ids = [row['transaction_id'] for row in result['scores']]
        event = result['batch_events'][0]
        event.update(transaction_ids=ids[:2])
        connected = dict(event, event_id='HARD_CONNECTED', rule_id='P1', points=20, hard_trigger=1,
            transaction_ids=ids[1:])
        result['batch_events'].append(connected)
        cases[0]['batch_event_ids'] = json.dumps([event['event_id'], connected['event_id']])
        rows, proofs = explain_admissions(result, cases, {ids[0]})
        self.assertEqual(rows[0]['effective_admission_basis'], 'hard_trigger')
        self.assertEqual(rows[0]['row_hard_trigger'], 0)
        self.assertEqual(rows[0]['event_rule_ids'], 'A4|P1')
        indirect = next(item for item in proofs[0]['batch_events'] if item['rule_id'] == 'P1')
        self.assertFalse(indirect['direct_participant'])
        self.assertEqual(set(proofs[0]['batch_groups'][0]['participant_ids']), set(ids))

    def test_input_reordering_does_not_change_export_or_proof_ids(self):
        result, cases = self.fixture(batch=True)
        ids = {row['transaction_id'] for row in result['scores']}
        before = explain_admissions(result, cases, ids)
        for field in ('scores', 'hits', 'batch_events'):
            result[field].reverse()
        cases.reverse()
        self.assertEqual(before, explain_admissions(result, cases, reversed(sorted(ids))))

    def test_inconsistent_or_unlinked_snapshot_fails_instead_of_inventing_a_reason(self):
        for fault in ('case_missing', 'case_event_missing', 'cross_company', 'duplicate_event', 'suppressed_positive'):
            with self.subTest(fault=fault):
                result, cases = self.fixture(batch=True)
                ids = {row['transaction_id'] for row in result['scores']}
                if fault == 'case_missing':
                    cases = []
                elif fault == 'case_event_missing':
                    cases[0]['batch_event_ids'] = '[]'
                elif fault == 'cross_company':
                    result['batch_events'][0]['company_id'] = 'OTHER'
                elif fault == 'duplicate_event':
                    result['batch_events'].append(copy.deepcopy(result['batch_events'][0]))
                else:
                    result['batch_events'][0]['suppressed_reason'] = 'Must not authorize'
                with self.assertRaises(ValueError):
                    explain_admissions(result, cases, ids)

    def test_csv_zero_flag_is_not_treated_as_truthy(self):
        result, cases = self.fixture(batch=True)
        for row in result['scores']:
            row['operational_alert'] = '0'
            row['hard_trigger'] = '0'
        rows, _ = explain_admissions(result, cases, {result['scores'][0]['transaction_id']})
        self.assertEqual(rows[0]['admission_source'], 'batch_closed')
        self.assertEqual(rows[0]['row_operational_alert'], '0')

    def test_frozen_export_cli_preserves_inputs_and_versions_artifacts(self):
        runtime = Path('.runtime').resolve()
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temp:
            root = Path(temp)
            before, source = root/'baseline/sme_fraud_005', root/'snapshot/sme_fraud_005'
            before.mkdir(parents=True)
            source.mkdir(parents=True)
            result, cases = self.fixture(batch=True)
            write_csv(before/'case_queue.csv', [], ['case_id', 'transaction_ids'])
            write_csv(source/'case_queue.csv', cases)
            write_csv(source/'rule_scores.csv', result['scores'])
            write_csv(source/'added_admissions.csv', [dict(transaction_id=row['transaction_id'],
                rule_score=row['rule_score'], period='validation') for row in result['scores']])
            for name, value in (('rule_config.json', result['config']), ('comparison.json', {})):
                (source/name).write_text(json.dumps(value), encoding='utf-8')
            for name, records in (('rule_hits.jsonl', result['hits']), ('batch_events.jsonl', result['batch_events'])):
                (source/name).write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
            frozen = {path.name: sha(path) for path in source.iterdir()}
            (source/'predictions_frozen.json').write_text(json.dumps(dict(sha256=frozen)), encoding='utf-8')
            output = root/'export'
            summary = run(output, baseline_root=before.parent, snapshot_root=source.parent, tags=('005',))
            self.assertEqual(summary['added_members'], 3)
            self.assertTrue(all(sha(source/name) == expected for name, expected in frozen.items()))
            self.assertTrue((output/'sme_fraud_005/added_admissions_v2.csv').is_file())
            self.assertTrue((output/'sme_fraud_005/export_commitment.json').is_file())
            self.assertFalse((output/'sme_fraud_005/added_admissions.csv').exists())
            with self.assertRaises(FileExistsError):
                run(output, baseline_root=before.parent, snapshot_root=source.parent, tags=('005',))


if __name__ == '__main__':
    unittest.main()
