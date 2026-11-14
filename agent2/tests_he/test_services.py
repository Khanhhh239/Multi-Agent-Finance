"""Two actual HTTP processes, a worker-only distribution and scoped enterprise."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sme_fraud.import_files import canonical
from sme_fraud.method_jobs import run_fit_job as core_fit
from experiments.he_inference.enterprise_server import EnterpriseNode
from experiments.he_inference.http_common import ServiceError, post, worker_address
from experiments.he_inference.protocol import public_hex, sign
from experiments.he_inference.registry_demo import source_for, commit, database_dump
from experiments.he_inference.registry_export import export_snapshot
from experiments.he_inference.registry_fit import run_fit_job
from experiments.he_inference.services_demo import Pair, request
from experiments.he_inference.worker_bundle import FILES
from experiments.he_inference.worker_server import Worker


class SeparatedServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='he-service-tests-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.pair = Pair(cls.temp.name)
        cls.addClassCleanup(cls.pair.close)
        env = cls.pair.env
        config = deepcopy(env['configs']['C001']); config.update(version='company-fit-config/1.0.0', method_id='ecod')
        cls.ecod = core_fit(env['snapshots'], env['models'], env['auth'], env['fit_header'], 'C001', config, 'services-core-ecod')['job']['artifact_id']
        config = deepcopy(env['configs']['C001']); config['selected_columns'] = ['log_abs_amount', 'journal_line_count']
        cls.lines = run_fit_job(env['snapshots'], env['models'], env['auth'], env['fit_header'], 'C001', config, 'services-line-model')['job']['artifact_id']
        cls.pair.start()
        cls.auth_bytes = env['policy'].read_bytes(); cls.grant_bytes = cls.pair.grants_file.read_bytes()

    def setUp(self):
        self.pair.env['policy'].write_bytes(self.auth_bytes)
        self.pair.grants_file.write_bytes(self.grant_bytes)
        self.pair.restart_node()

    def count_jobs(self):
        path = self.pair.worker_root / 'state/jobs.sqlite3'
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            return conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]

    def package(self):
        pair = self.pair; env = pair.env
        exported = export_snapshot(env['model_db'], env['snapshot_db'], env['auth'], env['header'], 'C001',
                                   env['artifacts']['C001'], env['queries']['C001'], '2026-10-03T00:00:00+07:00', public_hex(pair.worker_key))
        return exported, exported.cloud_package()

    def register(self, package, key=None):
        key = key or self.pair.node_key
        value = sign(dict(version='he-session-registration/1.0.0', node_verify_key=public_hex(key),
                          expires_at=package['request']['payload']['expires_at'], policy=package['policy']), key)
        return request(self.pair.worker_port, '/v1/sessions', value)

    def test_worker_bundle_excludes_enterprise_models_data_and_decryption_code(self):
        files = {p.name for p in (self.pair.bundle / 'experiments/he_inference').glob('*.py')}
        self.assertEqual(files, set(FILES))
        for name in ('enterprise.py', 'registry_export.py', 'registry_fit.py', 'enterprise_server.py'):
            self.assertNotIn(name, files)
        status, health = request(self.pair.worker_port, '/health')
        self.assertEqual(status, 200)
        self.assertFalse(health['enterprise_module_available']); self.assertFalse(health['business_module_available'])
        self.assertFalse(health['enterprise_storage_configured'])

    def test_two_companies_receive_all_five_results_with_separate_processes(self):
        self.assertNotEqual(self.pair.worker_process.pid, self.pair.node_process.pid)
        for company in ('C001', 'C002'):
            status, value = self.pair.analyze(company, key='two-companies-' + company)
            self.assertEqual(status, 200, value); self.assertEqual(value['row_count'], 5)
            self.assertTrue(all(r['available'] and r['score'] is not None for r in value['rows']))

    def test_http_does_not_write_registry_or_snapshot(self):
        before = {k: database_dump(self.pair.env[k]) for k in ('snapshot_db', 'model_db')}
        self.assertEqual(self.pair.analyze(key='no-domain-db-write')[0], 200)
        self.assertEqual(before, {k: database_dump(self.pair.env[k]) for k in before})

    def test_duplicate_node_request_returns_same_run_without_second_worker_job(self):
        before = self.count_jobs()
        first = self.pair.analyze(key='same-node-http-key')
        second = self.pair.analyze(key='same-node-http-key')
        self.assertEqual(first, second); self.assertEqual(first[0], 200)
        self.assertEqual(self.count_jobs(), before + 1)

    def test_same_key_with_changed_source_reference_is_conflict(self):
        self.assertEqual(self.pair.analyze(key='conflicting-body')[0], 200)
        body = self.pair.body(as_of='2026-10-04T00:00:00+07:00')
        status, value = self.pair.analyze(key='conflicting-body', body=body)
        self.assertEqual(status, 409); self.assertEqual(value['reason']['code'], 'IDEMPOTENCY_CONFLICT')

    def test_missing_node_credential_is_denied(self):
        status, _ = request(self.pair.node_port, '/v1/companies/C001/he/analyze', self.pair.body())
        self.assertEqual(status, 401)

    def test_unknown_company_is_denied_before_body(self):
        status, _ = request(self.pair.node_port, '/v1/companies/C999/he/analyze', raw=b'not json',
                            headers={'Authorization': self.pair.env['header']})
        self.assertEqual(status, 403)

    def test_node_rejects_plain_feature_body(self):
        body = self.pair.body(); body['features'] = [[1, 2]]
        before = self.count_jobs()
        self.assertEqual(self.pair.analyze(key='no-raw-acceptance', body=body)[0], 400)
        self.assertEqual(before, self.count_jobs())

    def test_node_rejects_caller_selected_worker_url(self):
        body = self.pair.body(); body['worker_url'] = 'http://example.invalid/'
        self.assertEqual(self.pair.analyze(key='no-client-ssrf-url', body=body)[0], 400)

    def test_worker_url_is_loopback_only(self):
        for value in ('https://example.com', 'http://127.0.0.1:80/private', 'http://user@127.0.0.1:80', 'http://127.0.0.1:80/?x=1'):
            with self.subTest(url=value), self.assertRaises(ServiceError):
                worker_address(value)

    def test_host_and_browser_origin_denied(self):
        for port in (self.pair.node_port, self.pair.worker_port):
            self.assertEqual(request(port, '/health', headers={'Host': 'attacker.invalid'})[0], 403)
            self.assertEqual(request(port, '/health', headers={'Origin': 'http://attacker.invalid'})[0], 403)

    def test_bad_content_type_and_oversized_body(self):
        headers = {'Authorization': self.pair.env['header'], 'Content-Type': 'text/plain', 'Idempotency-Key': 'bad-content-type'}
        self.assertEqual(request(self.pair.node_port, '/v1/companies/C001/he/analyze', self.pair.body(), headers=headers)[0], 415)
        headers['Content-Type'] = 'application/json'
        self.assertEqual(request(self.pair.node_port, '/v1/companies/C001/he/analyze', raw=b' ' * 4097, headers=headers)[0], 413)

    def test_unknown_and_decryption_routes_do_not_exist_on_worker(self):
        for path in ('/decrypt', '/fit', '/v1/companies/C001/he/analyze', '/imports/upload', '/files/private'):
            self.assertEqual(request(self.pair.worker_port, path, {'features': [[1, 2]]})[0], 404)

    def test_worker_rejects_raw_input_without_session(self):
        status, value = request(self.pair.worker_port, '/v1/evaluate', {'features': [[1, 2]]})
        self.assertEqual(status, 400); self.assertNotIn('score', value)

    def test_worker_does_not_accept_policy_from_evaluation_body(self):
        _, package = self.package()
        packet = deepcopy(package['request']); packet['policy'] = package['policy']
        status, _ = request(self.pair.worker_port, '/v1/evaluate', packet)
        self.assertEqual(status, 403)  # Not registered by authorized node.

    def test_untrusted_provisioning_key_cannot_register_own_policy(self):
        _, package = self.package()
        before = self.count_jobs()
        self.assertEqual(self.register(package, Ed25519PrivateKey.generate())[0], 403)
        self.assertEqual(before, self.count_jobs())

    def test_registration_signature_tamper_is_denied(self):
        _, package = self.package()
        packet = sign(dict(version='he-session-registration/1.0.0', node_verify_key=public_hex(self.pair.node_key),
                           expires_at=package['request']['payload']['expires_at'], policy=package['policy']), self.pair.node_key)
        packet['payload']['expires_at'] -= 1
        self.assertEqual(request(self.pair.worker_port, '/v1/sessions', packet)[0], 403)

    def test_evaluation_signature_tamper_is_denied(self):
        _, package = self.package(); self.assertEqual(self.register(package)[0], 200)
        packet = deepcopy(package['request']); packet['payload']['columns'][0] = 'AAAA'
        self.assertEqual(request(self.pair.worker_port, '/v1/evaluate', packet)[0], 403)

    def test_cross_company_session_is_denied(self):
        _, package = self.package(); self.assertEqual(self.register(package)[0], 200)
        packet = deepcopy(package['request']); packet['payload']['company_id'] = 'C002'
        self.assertEqual(request(self.pair.worker_port, '/v1/evaluate', packet)[0], 403)

    def test_grant_revocation_blocks_previously_registered_session(self):
        _, package = self.package(); self.assertEqual(self.register(package)[0], 200)
        grants = deepcopy(self.pair.grants)
        grants['grants'][0]['active'] = False; self.pair.grants_file.write_bytes(canonical(grants))
        before = self.count_jobs()
        self.assertEqual(request(self.pair.worker_port, '/v1/evaluate', package['request'])[0], 403)
        self.assertEqual(before, self.count_jobs())

    def test_worker_cached_ciphertext_survives_worker_restart(self):
        exported, package = self.package(); self.assertEqual(self.register(package)[0], 200)
        before = self.count_jobs()
        status, first = request(self.pair.worker_port, '/v1/evaluate', package['request'])
        self.assertEqual(status, 200)
        self.pair.restart_worker()
        status, second = request(self.pair.worker_port, '/v1/evaluate', package['request'])
        self.assertEqual(status, 200); self.assertEqual(first, second)
        self.assertEqual(self.count_jobs(), before + 1)
        self.assertTrue(all(r['available'] for r in exported.open(second)['rows']))

    def test_retry_lost_worker_response_reuses_original_ciphertext_and_node_key(self):
        pair = self.pair
        node = EnterpriseNode(pair.env['auth'], pair.env['model_db'], pair.env['snapshot_db'],
                              f'http://127.0.0.1:{pair.worker_port}', public_hex(pair.worker_key), pair.node_key)
        before = self.count_jobs(); lost = [False]
        def transport(url, path, payload):
            result = post(url, path, payload)
            if path == '/v1/evaluate' and not lost[0]:
                lost[0] = True
                raise ServiceError(503, 'WORKER_CONNECTION_UNAVAILABLE')
            return result
        with patch('experiments.he_inference.enterprise_server.post', side_effect=transport):
            with self.assertRaises(ServiceError):
                node.analyze('C001', pair.env['header'], 'lost-response-test', pair.body())
            result = node.analyze('C001', pair.env['header'], 'lost-response-test', pair.body())
        self.assertTrue(all(r['available'] for r in result['rows']))
        self.assertEqual(self.count_jobs(), before + 1)

    def test_partial_missing_data_keeps_five_rows(self):
        source = source_for('C001', 'query'); source['transactions'][2].pop('accounting_lines')
        env = self.pair.env; scope = env['auth'].authorize(env['fit_header'], 'C001')
        sid = commit(env['snapshots'], scope, source, 'service-missing-lines')
        body = self.pair.body(artifact_id=self.lines, snapshot_id=sid)
        status, data = self.pair.analyze(body=body, key='partial-http-query')
        self.assertEqual(status, 200, data); self.assertEqual(data['row_count'], 5)
        self.assertEqual(data['status'], 'partial')
        self.assertIsNone(data['rows'][2]['score']); self.assertEqual(data['rows'][2]['reason'], 'features_missing')

    def test_missing_and_unsupported_model_never_send_worker_job(self):
        before = self.count_jobs()
        for artifact in ('mth_' + '0' * 64, self.ecod):
            status, data = self.pair.analyze(key='unavailable-' + artifact[-16:], body=self.pair.body(artifact_id=artifact))
            self.assertEqual(status, 200); self.assertEqual(data['row_count'], 5)
            self.assertTrue(all(r['score'] is None and not r['available'] for r in data['rows']))
        self.assertEqual(before, self.count_jobs())

    def test_revoke_reader_blocks_cached_plaintext_result(self):
        self.assertEqual(self.pair.analyze(key='revoke-cached-node')[0], 200)
        auth = json.loads(self.auth_bytes); auth['principals'][1]['status'] = 'revoked'
        self.pair.env['policy'].write_bytes(canonical(auth))
        self.assertEqual(self.pair.analyze(key='revoke-cached-node')[0], 401)

    def test_node_response_contains_no_technical_receipt_or_keys(self):
        status, data = self.pair.analyze(key='safe-node-business-dto')
        self.assertEqual(status, 200)
        raw = canonical(data).decode()
        for value in ('origin_salt_hex', 'feature_contract', 'preprocess', 'ciphertext', 'private_key',
                      self.pair.env['artifacts']['C001'], public_hex(self.pair.node_key)):
            self.assertNotIn(value, raw)

    def test_expired_request_cannot_read_cached_ciphertext(self):
        exported, package = self.package()
        now = int(time.time())
        packet = deepcopy(package['request']); packet['payload'].update(created_at=now, expires_at=now + 1)
        packet = sign(packet['payload'], exported._session.signer)
        with tempfile.TemporaryDirectory(dir=self.pair.root) as folder, closing(Worker(folder, self.pair.grants_file, self.pair.worker_key)) as worker:
            registration = sign(dict(version='he-session-registration/1.0.0', node_verify_key=public_hex(self.pair.node_key),
                expires_at=now + 10, policy=package['policy']), self.pair.node_key)
            with patch('experiments.he_inference.worker_server.time.time', return_value=now):
                worker.register(registration); worker.score(packet)
            with patch('experiments.he_inference.worker_server.time.time', return_value=now + 2):
                with self.assertRaises(ServiceError) as result:
                    worker.score(packet)
            self.assertEqual(result.exception.code, 'REQUEST_EXPIRED')


if __name__ == '__main__':
    unittest.main()
