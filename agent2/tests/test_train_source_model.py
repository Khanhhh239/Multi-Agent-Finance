"""Source-format migration fits a new artifact, without weakening inference gates."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.train_source_model import (train_source_model, training_plan, main,
                                          IsolationForest, np, joblib, sklearn)
from sme_fraud.shadow_scoring import run_shadow
from sme_fraud.feature_contract import cache_contract, current_contract, sha, require_model, digest
from sme_fraud.generate import write_csv


class TrainSourceModelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = self.root / 'cache'
        self.dataset.mkdir()
        self.columns = current_contract()['columns']
        self.transactions = [dict(transaction_id=t, company_id=c, posted_at=d) for t, c, d in (
            ('T0', 'C001', '2024-01-01T00:00:00+07:00'),
            ('T1', 'C001', '2024-06-01T00:00:00+07:00'),
            ('T2', 'C001', '2025-01-01T00:00:00+07:00'),
            ('T3', 'C001', '2025-06-30T23:59:59+07:00'),
            ('T4', 'C001', '2025-07-01T00:00:00+07:00'),
            ('T5', 'C001', '2026-01-01T00:00:00+07:00'),
            ('T6', 'C002', '2024-06-01T00:00:00+07:00'),
            ('T7', 'C002', '2025-06-01T00:00:00+07:00'),
            ('T8', 'C002', '2025-08-01T00:00:00+07:00'))]
        self.features = [dict(transaction_id=r['transaction_id'], **{c: n+1 for c in self.columns})
                         for n, r in enumerate(self.transactions)]
        self.bind()
        self.plan = dict(company_ids=['C001'], source_ref='SIM_SOURCE_COMPATIBILITY_TEST',
                         train=dict(start_at='2024-01-01T00:00:00+07:00', end_at='2025-01-01T00:00:00+07:00'),
                         calibration=dict(start_at='2025-01-01T00:00:00+07:00', end_at='2025-07-01T00:00:00+07:00'),
                         evaluation=dict(start_at='2025-07-01T00:00:00+07:00', end_at='2026-01-01T00:00:00+07:00'))

    def tearDown(self):
        self.temp.cleanup()

    def bind(self):
        write_csv(self.dataset / 'transactions.csv', self.transactions)
        write_csv(self.dataset / 'features.csv', self.features)
        files = {n: dict(sha256=sha(self.dataset/n)) for n in ('transactions.csv', 'features.csv')}
        files.update({n: dict(sha256='DO_NOT_READ') for n in ('labels.csv', 'splits.csv')})
        self.metadata = dict(version='synthetic-source-world-v1', data_origin='synthetic_process_simulation',
                             role='reporting', feature_columns=self.columns, files=files,
                             feature_contract=cache_contract(files))
        self.save_metadata()

    def save_metadata(self):
        (self.dataset/'manifest.json').write_text(json.dumps(self.metadata), encoding='utf-8')

    def train(self, name='model', **kwargs):
        args = dict(plan=self.plan, n_estimators=8, max_samples=4, jobs=1)
        args.update(kwargs)
        return train_source_model(self.dataset, self.root/name, **args)

    def score(self, report, name='scores', scope=None):
        scope = scope or dict(company_ids=['C001'], source_ref='SIM_EVALUATION', **self.plan['evaluation'])
        return run_shadow(self.dataset, self.root/'model/isolation_forest.joblib', self.root/name,
                          model_sha256=report['model_sha256'], scope=scope)

    def test_new_format_artifact_is_fitted_and_scores_only_declared_future(self):
        original_fit = IsolationForest.fit
        fitted = []
        def fit(model, x, *args, **kwargs):
            fitted.append(x.copy())
            return original_fit(model, x, *args, **kwargs)
        before = {p: sha(p) for p in self.dataset.iterdir()}
        with patch.object(IsolationForest, 'fit', fit):
            report = self.train()
        self.assertEqual(len(fitted), 1)
        np.testing.assert_array_equal(fitted[0][:, 0], [1, 2])
        self.assertEqual(report['temporal_provenance']['train']['rows'], 2)
        self.assertEqual(report['temporal_provenance']['calibration']['rows'], 2)
        self.assertTrue(report['compatibility']['compatible'])
        artifact = joblib.load(self.root/'model/isolation_forest.joblib')
        self.assertEqual(artifact['dataset_version'], 'synthetic-source-world-v1')
        require_model(artifact, self.metadata, sklearn.__version__)
        with patch.object(IsolationForest, 'fit', side_effect=AssertionError('Inference must not fit')):
            result = self.score(report)
        self.assertEqual(result['rows_scored'], 1)
        self.assertTrue(result['model_training_window_disjointness_verified'])
        self.assertFalse(result['queue_changed'])
        self.assertEqual(before, {p: sha(p) for p in before})
        self.assertEqual(set(report['temporal_provenance']['train']['company_rows']), {'C001'})

    def test_calibration_threshold_uses_only_calibration_rows(self):
        report = self.train(alert_budget=.5)
        artifact = joblib.load(self.root/'model/isolation_forest.joblib')
        x = np.asarray([[r[c] for c in self.columns] for r in self.features[2:4]], dtype=np.float32)
        expected = float(np.quantile(-artifact['model'].score_samples(x), .5, method='higher'))
        self.assertEqual(artifact['threshold'], expected)
        self.assertEqual(report['evaluation_rows_scored'], 0)
        self.assertEqual(report['temporal_provenance']['evaluation_rows_used_for_fit_or_calibration'], 0)

    def test_training_and_scoring_never_read_labels_splits_or_oracle(self):
        original = Path.open
        def opened(path, *args, **kwargs):
            if path.name in {'labels.csv', 'splits.csv', 'control_oracle.jsonl'}:
                raise AssertionError('Forbidden label/split/oracle read')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            report = self.train()
            self.score(report)
        for field in ('labels_loaded', 'splits_loaded', 'oracle_loaded', 'queue_changed'):
            self.assertFalse(report[field])

    def test_evaluation_values_cannot_affect_fitted_model_or_threshold(self):
        self.train('first')
        for n in (4, 5, 8):
            self.features[n].update({c: 1e10 for c in self.columns})
        self.bind()
        self.train('second')
        a, b = [joblib.load(self.root/name/'isolation_forest.joblib') for name in ('first', 'second')]
        self.assertEqual(a['training_feature_fingerprint'], b['training_feature_fingerprint'])
        self.assertEqual(a['calibration_feature_fingerprint'], b['calibration_feature_fingerprint'])
        self.assertEqual(a['threshold'], b['threshold'])
        for first, second in zip(a['model'].estimators_, b['model'].estimators_):
            np.testing.assert_array_equal(first.tree_.threshold, second.tree_.threshold)

    def test_timezones_are_compared_as_instants(self):
        self.plan['train']['end_at'] = '2024-12-31T17:00:00+00:00'
        report = self.train()
        self.assertEqual(report['temporal_provenance']['train']['rows'], 2)

    def test_overlapping_reversed_naive_and_unknown_plan_fields_fail_before_fit(self):
        variants = []
        for section, field, value in (
            ('train', 'end_at', '2025-01-02T00:00:00+07:00'),
            ('evaluation', 'start_at', '2025-06-30T00:00:00+07:00'),
            ('train', 'start_at', '2025-01-01T00:00:00+07:00'),
            ('calibration', 'end_at', '2025-07-01T00:00:00')):
            plan = copy.deepcopy(self.plan)
            plan[section][field] = value
            variants.append(plan)
        variants.append(dict(self.plan, extra='unexpected'))
        variants.append(dict(self.plan, company_ids=['C001', 'C001']))
        with patch.object(IsolationForest, 'fit', side_effect=AssertionError('Must not fit')):
            for plan in variants:
                with self.subTest(plan=plan), self.assertRaises(ValueError):
                    self.train(plan=plan)

    def test_each_company_needs_train_and_calibration_observations(self):
        self.transactions[7]['posted_at'] = '2025-08-01T00:00:00+07:00'
        self.bind()
        with self.assertRaisesRegex(ValueError, 'Every requested company'):
            self.train(plan=dict(self.plan, company_ids=['C001', 'C002']))

    def test_stale_cache_and_modified_source_are_rejected_before_fit(self):
        with patch.object(IsolationForest, 'fit', side_effect=AssertionError('Must not fit')):
            self.metadata['feature_contract']['fingerprint'] = 'stale'
            self.save_metadata()
            with self.assertRaisesRegex(ValueError, 'semantics/schema'):
                self.train()
            self.bind()
            with (self.dataset/'features.csv').open('a') as stream:
                stream.write('changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.train()

    def test_legacy_model_still_cannot_score_new_format(self):
        report = self.train()
        path = self.root/'model/isolation_forest.joblib'
        artifact = joblib.load(path)
        artifact['dataset_version'] = '2.1-feature-sync'
        joblib.dump(artifact, path)
        report['model_sha256'] = sha(path)
        with self.assertRaisesRegex(ValueError, 'dataset_format_version_mismatch'):
            self.score(report)

    def test_inference_rejects_training_calibration_other_company_and_outside_window(self):
        report = self.train()
        variants = [dict(company_ids=['C001'], source_ref='SIM_INVALID', **self.plan[name])
                    for name in ('train', 'calibration')]
        variants += [dict(company_ids=['C002'], source_ref='SIM_INVALID', **self.plan['evaluation']),
                     dict(company_ids=['C001'], source_ref='SIM_INVALID',
                          start_at='2025-12-01T00:00:00+07:00', end_at='2026-02-01T00:00:00+07:00')]
        for scope in variants:
            with self.subTest(scope=scope), self.assertRaisesRegex(ValueError, 'declared evaluation window'):
                self.score(report, scope=scope)
        self.assertFalse((self.root/'scores').exists())

    def test_missing_tampered_or_overlapping_temporal_provenance_is_rejected(self):
        report = self.train()
        path = self.root/'model/isolation_forest.joblib'
        original = path.read_bytes()
        for kind in ('missing', 'tampered', 'overlap', 'wrong_fingerprint', 'row_count'):
            artifact = joblib.load(io.BytesIO(original))
            proof = artifact['temporal_provenance']
            if kind == 'missing':
                del artifact['temporal_provenance']
            elif kind == 'tampered':
                proof['plan']['train']['end_at'] = self.plan['evaluation']['end_at']
            else:
                if kind == 'overlap':
                    proof['plan']['calibration']['end_at'] = '2025-07-02T00:00:00+07:00'
                elif kind == 'wrong_fingerprint':
                    proof['train']['feature_fingerprint'] = 'wrong'
                else:
                    proof['train']['rows'] += 1
                proof['fingerprint'] = digest({k: v for k, v in proof.items() if k != 'fingerprint'})
            joblib.dump(artifact, path)
            report['model_sha256'] = sha(path)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.score(report)

    def test_invalid_parameters(self):
        for args in (dict(alert_budget=True), dict(alert_budget=float('nan')), dict(alert_budget=1),
                     dict(n_estimators=0), dict(max_samples=1), dict(jobs=0), dict(random_state=-1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.train(**args)

    def test_holdout_path_and_role_rejected(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Must not read holdout')):
            with self.assertRaisesRegex(ValueError, '005'):
                train_source_model(self.root/'sme_fraud_005', self.root/'new', plan=self.plan)
        self.metadata['role'] = 'holdout'
        self.save_metadata()
        with self.assertRaisesRegex(ValueError, 'Holdout source role'):
            self.train()

    def test_no_overwrite_or_nested_model_output(self):
        self.train()
        with self.assertRaises(FileExistsError):
            self.train()
        with self.assertRaisesRegex(ValueError, 'snapshots'):
            self.train('model/nested')
        with self.assertRaises(ValueError):
            train_source_model(self.dataset, self.dataset/'nested', plan=self.plan)

    def test_source_mutation_during_fit_prevents_publication(self):
        original_fit = IsolationForest.fit
        def fit(model, x, *args, **kwargs):
            result = original_fit(model, x, *args, **kwargs)
            (self.dataset/'transactions.csv').write_text('changed', encoding='utf-8')
            return result
        with patch.object(IsolationForest, 'fit', fit):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.train()
        self.assertFalse((self.root/'model').exists())

    def test_failed_report_write_cleans_staged_files(self):
        with patch.object(Path, 'write_text', side_effect=OSError('SIM_DISK_FAILURE')):
            with self.assertRaisesRegex(OSError, 'SIM_DISK_FAILURE'):
                self.train()
        self.assertFalse((self.root/'model').exists())
        self.assertEqual(list(self.root.glob('.train-source-*')), [])

    def test_cli_trains_a_new_model(self):
        plan_path = self.root/'plan.json'
        plan_path.write_text(json.dumps(self.plan), encoding='utf-8')
        argv = ['train_source_model', '--dataset', str(self.dataset), '--output', str(self.root/'cli'),
                '--plan', str(plan_path), '--n-estimators', '8', '--max-samples', '4', '--jobs', '1']
        with patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()) as output:
            main()
        self.assertTrue(json.loads(output.getvalue())['compatible'])


if __name__ == '__main__':
    unittest.main()
