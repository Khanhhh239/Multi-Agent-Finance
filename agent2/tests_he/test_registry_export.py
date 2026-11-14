"""Read-only registry export, feature binding, authorization and no-fit checks."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sme_fraud.auth import AuthError
from sme_fraud.import_files import ImportFailure, canonical, digest
from sme_fraud.method_adapters import LocalArtifact
from sme_fraud.method_jobs import run_fit_job as core_fit
from sme_fraud.method_store import MethodStore
from sme_fraud.unsupervised_statistics import ShrunkMahalanobis
from experiments.he_inference.demo import worker_process
from experiments.he_inference.protocol import ABS_TOLERANCE, REL_TOLERANCE, HEUnavailable, public_hex
from experiments.he_inference.registry_demo import setup_demo, source_for, commit, database_dump
from experiments.he_inference.registry_export import export_snapshot, ReadOnlySnapshots
from experiments.he_inference.registry_fit import run_fit_job


class RegistryExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='he-registry-tests-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name); cls.env = setup_demo(cls.root)
        config = deepcopy(cls.env['configs']['C001']); config['selected_columns'] = ['log_abs_amount', 'journal_line_count']
        cls.lines_artifact = run_fit_job(cls.env['snapshots'], cls.env['models'], cls.env['auth'], cls.env['fit_header'],
                                        'C001', config, 'fit-journal-line-count')['job']['artifact_id']
        config = deepcopy(cls.env['configs']['C001']); config.update(version='company-fit-config/1.0.0', method_id='ecod')
        cls.unsupported = core_fit(cls.env['snapshots'], cls.env['models'], cls.env['auth'], cls.env['fit_header'],
                                   'C001', config, 'fit-existing-core-ecod')['job']['artifact_id']
        config = deepcopy(cls.env['configs']['C001']); config['evaluation_start'] = '2026-11-01T00:00:00+07:00'
        cls.later_evaluation = run_fit_job(cls.env['snapshots'], cls.env['models'], cls.env['auth'], cls.env['fit_header'],
                                          'C001', config, 'fit-later-evaluation')['job']['artifact_id']

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(dir=self.root); self.addCleanup(self.case.cleanup)
        self.folder = Path(self.case.name)
        self.signer = Ed25519PrivateKey.generate()
        self.policy_bytes = self.env['policy'].read_bytes()
        self.addCleanup(self.env['policy'].write_bytes, self.policy_bytes)

    def export(self, company='C001', **overrides):
        params = dict(model_db=self.env['model_db'], snapshot_db=self.env['snapshot_db'],
                      authorizer=self.env['auth'], authorization=self.env['header'], company=company,
                      artifact_id=self.env['artifacts'][company], snapshot_id=self.env['queries'][company],
                      as_of='2026-10-03T00:00:00+07:00', worker_verify_key=public_hex(self.signer))
        params.update(overrides)
        return export_snapshot(**params)

    def unavailable(self, result, reason):
        self.assertFalse(result.ready)
        data = result.local_result(); self.assertEqual(data['row_count'], 5)
        self.assertTrue(all(r['raw_score'] is None and not r['available'] and r['reason'] == reason for r in data['rows']), data)
        with self.assertRaises(HEUnavailable):
            result.cloud_package()

    def alter_artifact(self, change, payload=None):
        scope = self.env['auth'].authorize(self.env['header'], 'C001')
        original = MethodStore(self.env['model_db'], read_only=True).get_artifact(scope, self.env['artifacts']['C001'])
        manifest = json.loads(original.manifest); change(manifest)
        raw = canonical(manifest); artifact = LocalArtifact('mth_' + digest(raw), raw, original.payload if payload is None else payload)
        return artifact

    def mutated_export(self, change):
        artifact = self.alter_artifact(change)
        with patch('sme_fraud.method_store.MethodStore.get_artifact', return_value=artifact), \
             patch('experiments.he_inference.registry_export.joblib.load', side_effect=AssertionError('deserialize forbidden')):
            return self.export(artifact_id=artifact.artifact_id)

    def revoke(self):
        policy = json.loads(self.policy_bytes)
        policy['principals'][1]['status'] = 'revoked'
        self.env['policy'].write_bytes(canonical(policy))

    def test_registry_model_two_companies_roundtrip_without_fit_or_db_writes(self):
        before = {name: database_dump(self.env[name]) for name in ('model_db', 'snapshot_db')}
        for company in ('C001', 'C002'):
            with self.subTest(company=company), ExitStack() as stack:
                for target in ('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',
                               'sme_fraud.method_store.MethodStore.publish', 'sme_fraud.method_store.MethodStore.begin_fit'):
                    stack.enter_context(patch(target, side_effect=AssertionError('fit/write forbidden')))
                exported = self.export(company); self.assertTrue(exported.ready)
                self.assertEqual(len(exported.receipt['selected_columns']), 2)
                packet = exported.cloud_package()
                response, code, _ = worker_process(packet['request'], packet['policy'], self.signer, self.folder / company)
                self.assertEqual(code, 0, response)
                result = exported.open(response)
                self.assertEqual(result['status'], 'available'); self.assertEqual(result['row_count'], 5)
                self.assertTrue(all(r['available'] and r['raw_score'] is not None for r in result['rows']))
        self.assertEqual(before, {name: database_dump(self.env[name]) for name in before})

    def test_read_permission_does_not_require_model_fit(self):
        scope = self.env['auth'].authorize(self.env['header'], 'C001')
        self.assertNotIn('model.fit', scope.permissions)
        self.assertTrue(self.export().ready)

    def test_authorization_precedes_both_databases(self):
        with patch('experiments.he_inference.registry_export.ReadOnlySnapshots', side_effect=AssertionError('snapshot read')), \
             patch('experiments.he_inference.registry_export.MethodStore', side_effect=AssertionError('model read')):
            with self.assertRaises(AuthError):
                self.export(authorization='Bearer invalid')

    def test_no_cross_company_artifact(self):
        with patch('experiments.he_inference.registry_export.joblib.load', side_effect=AssertionError('deserialize')):
            self.unavailable(self.export(artifact_id=self.env['artifacts']['C002']), 'artifact_missing')

    def test_no_cross_company_snapshot(self):
        with self.assertRaises(ImportFailure) as error:
            self.export(snapshot_id=self.env['queries']['C002'])
        self.assertEqual(error.exception.status, 404)

    def test_missing_model_does_not_create_database_or_fit(self):
        path = self.folder / 'missing-models.sqlite3'
        with patch.object(ShrunkMahalanobis, 'fit', side_effect=AssertionError('fit')):
            self.unavailable(self.export(model_db=path), 'artifact_missing')
        self.assertFalse(path.exists())

    def test_missing_snapshot_does_not_create_database(self):
        path = self.folder / 'missing-snapshots.sqlite3'
        with self.assertRaises(ImportFailure):
            self.export(snapshot_db=path)
        self.assertFalse(path.exists())

    def test_existing_ecod_is_unsupported_not_deserialized_or_converted(self):
        with patch('experiments.he_inference.registry_export.joblib.load', side_effect=AssertionError('deserialize')):
            self.unavailable(self.export(artifact_id=self.unsupported), 'he_adapter_unsupported')

    def test_current_33_feature_contract_is_required(self):
        self.unavailable(self.mutated_export(lambda m: m['feature_contract'].update(columns=list(reversed(m['feature_contract']['columns'])))), 'artifact_incompatible')

    def test_fingerprint_mismatch(self):
        self.unavailable(self.mutated_export(lambda m: m.update(feature_contract_fingerprint='0' * 64)), 'artifact_incompatible')

    def test_runtime_mismatch(self):
        self.unavailable(self.mutated_export(lambda m: m['versions']['runtime'].update(python='other')), 'artifact_incompatible')

    def test_preprocess_hash(self):
        self.unavailable(self.mutated_export(lambda m: m.update(preprocess_sha256='0' * 64)), 'artifact_incompatible')

    def test_selected_column_order(self):
        self.unavailable(self.mutated_export(lambda m: m.update(selected_columns=list(reversed(m['selected_columns'])))), 'artifact_incompatible')

    def test_model_payload_hash(self):
        self.unavailable(self.mutated_export(lambda m: m.update(payload_sha256='0' * 64)), 'artifact_invalid')

    def test_model_version(self):
        self.unavailable(self.mutated_export(lambda m: m.update(model_version='mdl_wrong')), 'artifact_invalid')

    def test_unknown_registry_version(self):
        self.unavailable(self.mutated_export(lambda m: m.update(he_registry_version='old')), 'artifact_incompatible')

    def test_cloud_package_contains_no_private_registry_or_snapshot_identifiers(self):
        exported = self.export(); wire = canonical(exported.cloud_package()).decode()
        self.assertNotIn(self.env['artifacts']['C001'], wire)
        self.assertNotIn(self.env['queries']['C001'], wire)
        self.assertNotIn(exported.receipt['feature_contract_fingerprint'], wire)
        self.assertNotIn(exported.receipt['origin_salt_hex'], wire)
        for field in ('selected_columns', 'preprocess', 'receipt', 'record_id', 'raw_score'):
            self.assertNotIn('"' + field + '"', wire)

    def test_mutating_package_does_not_mutate_pending_request(self):
        exported = self.export(); first = exported.cloud_package(); first['request']['payload']['model_id'] = 'bad'
        self.assertNotEqual(exported.cloud_package()['request']['payload']['model_id'], 'bad')

    def test_revoke_before_package(self):
        exported = self.export(); self.revoke()
        with self.assertRaises(AuthError):
            exported.cloud_package()

    def test_revoke_during_load(self):
        import experiments.he_inference.registry_export as module
        original = module.joblib.load
        def load(*args, **kwargs):
            model = original(*args, **kwargs); self.revoke(); return model
        with patch.object(module.joblib, 'load', side_effect=load):
            with self.assertRaises(AuthError):
                self.export()

    def test_revoke_before_result_decryption(self):
        exported = self.export(); package = exported.cloud_package()
        response, code, _ = worker_process(package['request'], package['policy'], self.signer, self.folder / 'cloud')
        self.assertEqual(code, 0); self.revoke()
        with patch('tenseal.CKKSVector.decrypt', side_effect=AssertionError('decrypt')):
            with self.assertRaises(AuthError):
                exported.open(response)

    def test_missing_features_keep_all_rows_and_only_encrypt_eligible(self):
        source = source_for('C001', 'query'); source['transactions'][2].pop('accounting_lines')
        scope = self.env['auth'].authorize(self.env['fit_header'], 'C001')
        sid = commit(self.env['snapshots'], scope, source, 'query-missing-lines')
        exported = self.export(artifact_id=self.lines_artifact, snapshot_id=sid)
        self.assertTrue(exported.ready); self.assertEqual(len(exported.cloud_package()['request']['payload']['row_handles']), 4)
        response, code, _ = worker_process(**dict(packet=exported.cloud_package()['request'], policy=exported.cloud_package()['policy'],
                                                 key=self.signer, folder=self.folder / 'partial'))
        self.assertEqual(code, 0)
        data = exported.open(response); self.assertEqual(data['row_count'], 5); self.assertEqual(data['status'], 'partial')
        row = data['rows'][2]; self.assertEqual(row['reason'], 'features_missing'); self.assertIsNone(row['raw_score'])
        self.assertEqual(row['missing_features'], ['journal_line_count'])

    def test_history_rows_are_not_re_scored_as_new(self):
        exported = self.export(snapshot_id=self.env['training']['C001'], as_of='2026-09-20T00:00:00+07:00')
        self.assertFalse(exported.ready); data = exported.local_result()
        self.assertEqual(data['row_count'], 40)
        self.assertTrue(all(r['raw_score'] is None for r in data['rows']))

    def test_read_only_snapshot_adapter_refuses_writes(self):
        store = ReadOnlySnapshots(self.env['snapshot_db'])
        conn = store._connect()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute('CREATE TABLE forbidden(x)')
        finally:
            conn.close()

    def test_offline_fit_idempotency_and_no_fit_with_reader(self):
        prior = self.env['artifacts']['C001']
        result = run_fit_job(self.env['snapshots'], self.env['models'], self.env['auth'], self.env['fit_header'],
                            'C001', self.env['configs']['C001'], 'C001-offline-fit')
        self.assertEqual(result['job']['artifact_id'], prior); self.assertTrue(result['reused'])
        with self.assertRaises(ImportFailure) as error:
            run_fit_job(self.env['snapshots'], self.env['models'], self.env['auth'], self.env['header'],
                        'C001', self.env['configs']['C001'], 'read-must-not-fit')
        self.assertEqual(error.exception.code, 'MODEL_FIT_DENIED')

    def test_fit_provenance_must_match_successful_job_before_load(self):
        self.unavailable(self.mutated_export(lambda m: m['fit_context'].update(job_id='fit_nonexistent')), 'artifact_invalid')

    def test_changed_evaluation_without_new_job_is_rejected(self):
        def change(m):
            m['fit_context']['evaluation_start'] = '2026-10-31T17:00:00+00:00'
            m['fit_context']['config']['evaluation_start'] = '2026-10-31T17:00:00+00:00'
        # Changing immutable job configuration without a new matching job is
        # rejected before loading rather than accepted as a newer artifact.
        self.unavailable(self.mutated_export(change), 'artifact_invalid')

    def test_valid_later_model_does_not_score_before_its_evaluation_period(self):
        self.unavailable(self.export(artifact_id=self.later_evaluation), 'before_evaluation_period')

    def test_seen_identity_later_date_is_excluded_but_other_rows_kept(self):
        source = source_for('C001', 'query')
        source['transactions'][0]['record_id'] = source['transactions'][0]['source']['record_id'] = 'H0'
        source['payment_allocations'][0]['transaction_ref']['record_id'] = 'H0'
        scope = self.env['auth'].authorize(self.env['fit_header'], 'C001')
        sid = commit(self.env['snapshots'], scope, source, 'query-overlap-identity')
        exported = self.export(snapshot_id=sid)
        self.assertTrue(exported.ready)
        self.assertEqual(exported.local_result()['rows'][0]['reason'], 'artifact_training_overlap')
        self.assertEqual(len(exported.cloud_package()['request']['payload']['row_handles']), 4)

    def test_batch_over_limit_is_not_truncated(self):
        source = source_for('C001', 'query')
        for i in range(5, 9):
            tx = deepcopy(source['transactions'][0]); allocation = deepcopy(source['payment_allocations'][0])
            tx['record_id'] = tx['source']['record_id'] = 'T' + str(i)
            allocation['record_id'] = allocation['source']['record_id'] = 'A_T' + str(i)
            allocation['transaction_ref']['record_id'] = tx['record_id']
            source['transactions'].append(tx); source['payment_allocations'].append(allocation)
        scope = self.env['auth'].authorize(self.env['fit_header'], 'C001')
        sid = commit(self.env['snapshots'], scope, source, 'query-nine-rows')
        result = self.export(snapshot_id=sid).local_result()
        self.assertEqual(result['row_count'], 9)
        self.assertTrue(all(r['reason'] == 'he_batch_limit' and r['raw_score'] is None for r in result['rows']))

    def cli(self, artifact, output):
        token = self.folder / 'reader.token'; token.write_text(self.env['header'].removeprefix('Bearer '))
        root = Path(__file__).resolve().parents[1]
        args = [sys.executable, '-X', 'utf8', '-B', '-m', 'experiments.he_inference.registry_cli', 'score-local',
                '--model-db', str(self.env['model_db']), '--snapshot-db', str(self.env['snapshot_db']),
                '--auth-file', str(self.env['policy']), '--token-file', str(token), '--company', 'C001',
                '--artifact-id', artifact, '--snapshot-id', self.env['queries']['C001'],
                '--as-of', '2026-10-03T00:00:00+07:00', '--output', str(output)]
        return subprocess.run(args, cwd=root, env=dict(os.environ, PYTHONPATH=str(root)),
                              capture_output=True, text=True, encoding='utf-8', timeout=45)

    def test_cli_fresh_process_reads_registry_and_writes_local_result(self):
        target = self.folder / 'result.json'
        completed = self.cli(self.env['artifacts']['C001'], target)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(target.read_bytes())
        self.assertEqual(result['row_count'], 5); self.assertEqual(result['status'], 'available')
        self.assertEqual(result['receipt']['artifact_id'], self.env['artifacts']['C001'])
        before = target.read_bytes()
        repeated = self.cli(self.env['artifacts']['C001'], target)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(target.read_bytes(), before)

    def test_cli_unsupported_model_writes_unavailable_not_scores(self):
        target = self.folder / 'unsupported.json'
        completed = self.cli(self.unsupported, target)
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        result = json.loads(target.read_bytes())
        self.assertTrue(all(r['reason'] == 'he_adapter_unsupported' and r['raw_score'] is None for r in result['rows']))


if __name__ == '__main__':
    unittest.main()
