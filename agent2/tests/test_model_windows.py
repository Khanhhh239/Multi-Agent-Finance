"""Verify actual time membership and frozen-model bindings without retraining."""
import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_train_source_model as fixtures
from sme_fraud.audit_model_windows import audit_model_windows, partition_rows, main
from sme_fraud.feature_contract import sha, digest
from sme_fraud.train_source_model import IsolationForest, joblib


class ModelWindowsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TrainSourceModelTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.trained = self.fixture.train()
        self.model = self.root/'model/isolation_forest.joblib'

    def audit(self, name='audit', **kwargs):
        args = dict(model_sha256=self.trained['model_sha256'])
        args.update(kwargs)
        return audit_model_windows(self.fixture.dataset, self.model, self.root/name, **args)

    def test_actual_boundary_membership_and_id_disjointness_without_fit_or_score(self):
        before = {p: sha(p) for folder in (self.fixture.dataset, self.model.parent) for p in folder.iterdir()}
        with (patch.object(IsolationForest, 'fit', side_effect=AssertionError('Audit cannot fit')),
              patch.object(IsolationForest, 'score_samples', side_effect=AssertionError('Audit cannot score'))):
            report = self.audit()
        with (self.root/'audit/temporal_partitions.csv').open(encoding='utf-8', newline='') as stream:
            rows = {r['transaction_id']: r for r in csv.DictReader(stream)}
        self.assertEqual({i: rows[i]['partition'] for i in rows}, {
            'T0': 'train', 'T1': 'train', 'T2': 'calibration', 'T3': 'calibration', 'T4': 'evaluation',
            'T5': 'outside_time_windows', 'T6': 'outside_company_scope',
            'T7': 'outside_company_scope', 'T8': 'outside_company_scope'})
        self.assertEqual(rows['T2']['posted_at_utc'], '2024-12-31T17:00:00+00:00')
        self.assertEqual(report['actual_id_overlaps'], {'train__calibration': 0, 'train__evaluation': 0, 'calibration__evaluation': 0})
        self.assertTrue(report['actual_train_calibration_features_match_model'])
        self.assertTrue(report['threshold_matches_training_record'])
        self.assertEqual((report['models_fitted'], report['observations_scored']), (0, 0))
        self.assertEqual(before, {p: sha(p) for p in before})

    def test_same_instant_different_offset_and_gaps_are_assigned_correctly(self):
        plan = copy.deepcopy(self.fixture.plan)
        plan['calibration']['start_at'] = '2025-02-01T00:00:00+07:00'
        transactions = [dict(transaction_id=t, company_id='C001', posted_at=d) for t, d in (
            ('BEFORE', '2024-12-31T16:59:59+00:00'),
            ('GAP', '2025-01-01T00:00:00+07:00'),
            ('CAL', '2025-01-31T17:00:00+00:00'),
            ('EVAL', '2025-06-30T17:00:00+00:00'),
            ('END', '2025-12-31T17:00:00+00:00'))]
        assigned = {r['transaction_id']: r['partition'] for r in partition_rows(transactions, plan)}
        self.assertEqual(assigned, dict(BEFORE='train', GAP='outside_time_windows', CAL='calibration',
                                        EVAL='evaluation', END='outside_time_windows'))
        transactions[1]['transaction_id'] = 'BEFORE'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            partition_rows(transactions, plan)

    def test_labels_splits_and_oracle_are_not_audit_dependencies(self):
        original = Path.open
        def opened(path, *args, **kwargs):
            if path.name in {'labels.csv', 'splits.csv', 'control_oracle.jsonl'}:
                raise AssertionError('Forbidden audit dependency')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            report = self.audit()
        self.assertFalse(report['labels_loaded'])
        self.assertFalse(report['splits_loaded'])
        self.assertFalse(report['oracle_loaded'])

    def test_actual_feature_fingerprints_are_recomputed(self):
        artifact = joblib.load(self.model)
        proof = artifact['temporal_provenance']
        artifact['training_feature_fingerprint'] = proof['train']['feature_fingerprint'] = 'WRONG_ACTUAL_MATRIX'
        proof['fingerprint'] = digest({k: v for k, v in proof.items() if k != 'fingerprint'})
        joblib.dump(artifact, self.model)
        record_path = self.model.parent/'training_run.json'
        record = json.loads(record_path.read_text(encoding='utf-8'))
        record.update(model_sha256=sha(self.model), temporal_provenance=proof)
        record_path.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Actual train rows/features'):
            self.audit(model_sha256=sha(self.model))
        self.assertFalse((self.root/'audit').exists())

    def test_model_checksum_checked_before_deserialization(self):
        with patch('sme_fraud.audit_model_windows.joblib.load', side_effect=AssertionError('Must not deserialize')):
            with self.assertRaisesRegex(ValueError, 'Model checksum'):
                self.audit(model_sha256='wrong')

    def test_modified_threshold_training_record_or_cache_cannot_be_certified(self):
        record_path = self.model.parent/'training_run.json'
        original_record = record_path.read_bytes()
        record = json.loads(original_record)
        record['calibration']['threshold'] += .1
        record_path.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'threshold or provenance'):
            self.audit()
        record_path.write_bytes(original_record)
        self.fixture.features[0][self.fixture.columns[0]] += 1
        self.fixture.bind()
        with self.assertRaisesRegex(ValueError, 'original frozen training cache'):
            self.audit()

    def test_model_record_changed_during_audit_prevents_publication(self):
        from sme_fraud.audit_model_windows import window_summary
        def changed(*args, **kwargs):
            (self.model.parent/'training_run.json').write_text('changed', encoding='utf-8')
            return window_summary(*args, **kwargs)
        with patch('sme_fraud.audit_model_windows.window_summary', changed):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                self.audit()
        self.assertFalse((self.root/'audit').exists())

    def test_output_is_immutable_and_failed_write_cleans_stage(self):
        self.audit()
        with self.assertRaises(FileExistsError):
            self.audit()
        with self.assertRaises(ValueError):
            self.audit('model/nested')
        with patch.object(Path, 'write_text', side_effect=OSError('SIM_AUDIT_DISK_FAILURE')):
            with self.assertRaisesRegex(OSError, 'SIM_AUDIT_DISK_FAILURE'):
                self.audit('failed')
        self.assertFalse((self.root/'failed').exists())
        self.assertEqual(list(self.root.glob('.temporal-audit-*')), [])

    def test_holdout_path_rejected_before_read(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No holdout read')):
            with self.assertRaisesRegex(ValueError, '005'):
                audit_model_windows(self.root/'sme_fraud_005', self.model, self.root/'new', model_sha256='unused')

    def test_cli_publishes_partition_audit(self):
        args = ['audit_model_windows', '--dataset', str(self.fixture.dataset), '--model', str(self.model),
                '--model-sha256', self.trained['model_sha256'], '--output', str(self.root/'cli')]
        with patch('sys.argv', args), contextlib.redirect_stdout(io.StringIO()) as output:
            main()
        self.assertEqual(json.loads(output.getvalue())['status'], 'actual_source_partitions_verified')


if __name__ == '__main__':
    unittest.main()
