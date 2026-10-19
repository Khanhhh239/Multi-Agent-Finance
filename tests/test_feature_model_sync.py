"""Cache/model provenance and train/validation-only integration contracts."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sme_fraud.feature_contract import (cache_contract, current_contract, model_compatibility,
                                      require_model, sha, validate_cache)
from sme_fraud.features import FEATURE_DESCRIPTIONS
from sme_fraud.sync_feature_model import (callback_revisions, derive, read_rows, run_dataset,
                                         write_json, write_jsonl, np, joblib, IsolationForest)


class FeatureModelSyncTest(unittest.TestCase):
    def metadata(self):
        files = {'transactions.csv': {'sha256': 'tx'}, 'features.csv': {'sha256': 'x'}}
        return dict(version='2.1-feature-sync', feature_columns=list(FEATURE_DESCRIPTIONS),
                    files=files, feature_contract=cache_contract(files))

    def artifact(self, meta):
        return dict(model=SimpleNamespace(n_features_in_=len(FEATURE_DESCRIPTIONS)),
            feature_columns=list(FEATURE_DESCRIPTIONS), dataset_version=meta['version'],
            feature_contract_fingerprint=meta['feature_contract']['fingerprint'],
            sklearn_version='runtime', training_feature_fingerprint='train',
            score_direction='higher_is_more_anomalous')

    def test_legacy_cache_with_same_columns_is_rejected(self):
        meta = self.metadata()
        del meta['feature_contract']
        with self.assertRaisesRegex(ValueError, 'Legacy feature cache'):
            validate_cache(meta)

    def test_semantics_and_manifest_columns_are_checked(self):
        for field in ('fingerprint', 'version', 'dtype'):
            meta = self.metadata()
            meta['feature_contract'][field] = 'stale'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'semantics/schema'):
                validate_cache(meta)
        meta = self.metadata()
        meta['feature_columns'].reverse()
        with self.assertRaisesRegex(ValueError, 'ordered feature columns'):
            validate_cache(meta)

    def test_source_and_feature_content_bindings_are_checked(self):
        for name, reason in (('transactions.csv', 'input binding'), ('features.csv', 'content binding')):
            meta = self.metadata()
            meta['files'][name]['sha256'] = 'changed'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, reason):
                validate_cache(meta)

    def test_labels_and_split_statistics_do_not_define_feature_provenance(self):
        meta = self.metadata()
        meta['files']['labels.csv'] = {'sha256': 'later-labels'}
        meta['files']['splits.csv'] = {'sha256': 'later-splits'}
        self.assertEqual(validate_cache(meta)['fingerprint'], current_contract()['fingerprint'])

    def test_matching_model_is_accepted(self):
        meta = self.metadata()
        self.assertTrue(require_model(self.artifact(meta), meta, 'runtime')['compatible'])

    def test_model_provenance_runtime_width_and_order_are_required(self):
        meta = self.metadata()
        for field in ('feature_columns', 'feature_contract_fingerprint', 'sklearn_version',
                      'training_feature_fingerprint', 'dataset_version', 'score_direction'):
            artifact = self.artifact(meta)
            artifact.pop(field)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'IF model incompatible'):
                require_model(artifact, meta, 'runtime')
        artifact = self.artifact(meta)
        artifact['model'].n_features_in_ = 189
        self.assertIn('estimator_input_width_mismatch', model_compatibility(artifact, meta, 'runtime')['reasons'])

    def callback(self):
        return dict(change_id='C', company_id='SME', callback_verified='1', approver_id='SIGNER',
            observed_at='2025-06-01T10:00:00+07:00', verified_at='2025-06-02T10:00:00+07:00')

    def test_synthetic_callback_revision_preserves_causal_availability(self):
        original = self.callback()
        rows, repairs = callback_revisions([original], synthetic=True)
        self.assertEqual(original, self.callback())
        self.assertEqual([r['callback_verified'] for r in rows], ['0', '1'])
        self.assertEqual(rows[0]['approver_id'], '')
        self.assertEqual(rows[1]['observed_at'], original['verified_at'])
        self.assertEqual(len(repairs), 1)

    def test_future_callback_revision_is_excluded(self):
        row = self.callback()
        row['verified_at'] = '2025-07-02T10:00:00+07:00'
        rows, _ = callback_revisions([row], synthetic=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['callback_verified'], '0')

    def test_real_source_is_never_automatically_repaired(self):
        with self.assertRaisesRegex(ValueError, 'synthetic source provenance'):
            callback_revisions([self.callback()])

    def test_bad_flag_is_not_repaired_into_valid_data(self):
        row = self.callback()
        row['callback_verified'] = '2'
        with self.assertRaisesRegex(ValueError, 'expected boolean'):
            callback_revisions([row], synthetic=True)

    def fixture(self, root):
        from sme_fraud.generate import parse, save_dataset, write_csv
        from sme_fraud.rule_audit_cases import Case
        from sme_fraud.case_queue import review_queue
        from sme_fraud.rules import INPUT_TABLES
        case = Case()
        for name in INPUT_TABLES:
            case.tables.setdefault(name, [])
        for year, month in ((2024, 6), (2025, 6), (2025, 8)):
            for day in (12, 13):
                case.pay(at=parse(f'{year}-{month:02}-{day}T11:00:00+07:00'),
                         amount=30_000_000, invoice_number='SMOKE', invoice_gross_vnd=30_000_000)
        result = case.score()
        case.tables['labels'] = [dict(transaction_id=r['transaction_id'], is_fraud=n % 2,
            fraud_type='overpayment' if n % 2 else '', variant='smoke', case_id=f'TRUTH{n}',
            hard_negative_type='') for n, r in enumerate(case.rows)]
        case.tables['splits'] = [dict(transaction_id=r['transaction_id'],
            split='train' if r['posted_at'][:4] == '2024' else 'validation' if r['posted_at'][5:7] == '06' else 'test')
            for r in case.rows]
        source = root / 'data/sme_fraud_001'
        save_dataset(source, case.tables, 6, .003, 20261012, 1)
        baseline = root / 'reports/rules/sme_fraud_001'
        baseline.mkdir(parents=True)
        write_csv(baseline / 'rule_scores.csv', result['scores'])
        write_jsonl(baseline / 'rule_hits.jsonl', result['hits'])
        queue, events = review_queue(result, case.tables)
        write_csv(baseline / 'case_queue.csv', queue)
        write_csv(baseline / 'case_events.csv', events)
        write_json(baseline / 'rule_config.json', result['config'])
        x = np.asarray([[r[c] for c in FEATURE_DESCRIPTIONS] for r in case.features], dtype=np.float32)
        model = IsolationForest(n_estimators=3, max_samples=2, random_state=20261012).fit(x[:2])
        model_path = root / 'reports/sme_fraud_001/isolation_forest.joblib'
        model_path.parent.mkdir(parents=True)
        joblib.dump(dict(model=model, feature_columns=list(FEATURE_DESCRIPTIONS), dataset_version='2.0'), model_path)
        return source

    def test_derivation_and_end_to_end_evaluation_exclude_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.fixture(root)
            tables, partitions, _, protected = derive(source, root / 'derive_only')
            self.assertEqual(sorted(partitions.values()), ['train', 'train', 'validation', 'validation'])
            from sme_fraud.features import build_features
            rebuilt = {r['transaction_id']: r for r in build_features(tables)}
            original = {r['transaction_id']: r for r in read_rows(source / 'features.csv')}
            from sme_fraud.accounting import ACCOUNTING_FEATURE_DESCRIPTIONS
            accounting_columns = set(ACCOUNTING_FEATURE_DESCRIPTIONS) | {c for c in FEATURE_DESCRIPTIONS if c.startswith(('debit_', 'credit_'))}
            for identity, row in rebuilt.items():
                self.assertGreater(row['journal_line_count'], 0)
                for column in accounting_columns:
                    self.assertEqual(row[column], float(original[identity][column]), (identity, column))
            self.assertTrue(all(sha(source / name) == value for name, value in protected.items()))
            previous = Path.cwd()
            try:
                os.chdir(root)
                def guarded_rows(path):
                    if Path(path).name == 'labels.csv':
                        self.assertTrue(Path('reports/sync_smoke/sme_fraud_001/predictions_frozen.json').is_file())
                    return read_rows(path)
                with patch('sme_fraud.sync_feature_model.read_rows', side_effect=guarded_rows):
                    report = run_dataset(Path('reports/sync_smoke'), '001', jobs=1)
                from sme_fraud.rules import load_inputs
                _, loaded, _ = load_inputs(Path('data/sync_smoke/sme_fraud_001'))
                self.assertEqual(len(loaded), 4)
            finally:
                os.chdir(previous)
            self.assertFalse(report['test_scored'])
            self.assertEqual(report['label_rows_loaded'], 4)
            self.assertTrue(report['original_sources_unchanged'])
            self.assertTrue(report['legacy_reports_and_model_unchanged'])
            self.assertTrue(report['new_model_compatibility']['compatible'])
            self.assertFalse(report['legacy_model_compatibility']['compatible'])
            self.assertTrue(report['review_cache_loaded'])
            self.assertEqual(len(list(read_rows(root / 'data/sync_smoke/sme_fraud_001/features.csv'))), 4)


if __name__ == '__main__':
    unittest.main()
