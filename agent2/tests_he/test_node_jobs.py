"""Durable idempotency, authenticated checkpoint storage and restart recovery."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from experiments.he_inference.http_common import ServiceError
from experiments.he_inference.job_client import run as client_run
from experiments.he_inference.jobs_demo import submit, state, wait, worker_count
from experiments.he_inference.node_job_store import JobStore
from experiments.he_inference.protocol import canonical, public_hex, sign, sha
from experiments.he_inference.registry_export import export_snapshot
from experiments.he_inference.worker_server import Worker
from experiments.he_inference.services_demo import Pair, request
from experiments.he_inference.enterprise_server import EnterpriseNode
from experiments.he_inference.http_common import post


class JobStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.key = self.root / 'key.hex'; self.key.write_text(secrets.token_hex(32))
        self.scope = AccessScope('tenant', frozenset({'C001'}), 'reader', frozenset({'data.import'}))
        self.store = JobStore(self.root / 'state', self.key); self.addCleanup(self.store.close)
        self.body = dict(artifact_id='mth_' + '1' * 64, snapshot_id='snp_' + '2' * 32, as_of='2026-10-01T00:00:00+00:00')

    def create(self, key='stable-request-key'):
        return self.store.create(self.scope, key, self.body)

    def test_duplicate_create_is_persistently_one_job(self):
        first = self.create(); self.assertEqual(first, self.create())
        self.store.close(); self.store = JobStore(self.root / 'state', self.key); self.addCleanup(self.store.close)
        self.assertEqual(first, self.create())

    def test_changed_request_conflicts(self):
        self.create(); other = dict(self.body, as_of='2026-11-01T00:00:00+00:00')
        with self.assertRaises(ServiceError) as result:
            self.store.create(self.scope, 'stable-request-key', other)
        self.assertEqual(result.exception.code, 'IDEMPOTENCY_CONFLICT')

    def test_request_and_key_not_plaintext_in_database(self):
        self.create()
        raw = self.store.path.read_bytes()
        for value in (self.body['artifact_id'], self.body['snapshot_id'], 'stable-request-key'):
            self.assertNotIn(value.encode(), raw)

    def test_wrong_master_key_fails_without_rewriting_jobs(self):
        self.create(); self.store.close()
        before = self.store.path.read_bytes(); wrong = self.root / 'wrong.hex'; wrong.write_text(secrets.token_hex(32))
        with self.assertRaises(ServiceError):
            JobStore(self.root / 'state', wrong)
        self.assertEqual(before, self.store.path.read_bytes())

    def test_missing_master_key_never_generates_new_key_or_database(self):
        with self.assertRaises(ServiceError):
            JobStore(self.root / 'new', self.root / 'missing.hex')
        self.assertFalse((self.root / 'new/jobs.sqlite3').exists())

    def test_second_node_cannot_own_same_state(self):
        with self.assertRaises(ServiceError) as result:
            JobStore(self.root / 'state', self.key)
        self.assertEqual(result.exception.code, 'NODE_STATE_IN_USE')

    def test_other_actor_company_and_tenant_cannot_read_job(self):
        job = self.create()
        for scope in (AccessScope('other', self.scope.company_ids, 'reader', self.scope.permissions),
                      AccessScope('tenant', frozenset({'C002'}), 'reader', self.scope.permissions),
                      AccessScope('tenant', self.scope.company_ids, 'other', self.scope.permissions)):
            with self.assertRaises(ServiceError) as result:
                self.store.get(scope, job)
            self.assertEqual(result.exception.status, 404)

    def test_ciphertext_tamper_fails_closed(self):
        job = self.create()
        with closing(sqlite3.connect(self.store.path)) as conn:
            with conn:
                conn.execute('UPDATE jobs SET payload=? WHERE id=?', (b'corrupted', job))
        with self.assertRaises(ServiceError) as result:
            self.store.get(self.scope, job)
        self.assertEqual(result.exception.code, 'NODE_STATE_INTEGRITY')

    def test_copying_checkpoint_to_another_job_fails_aad(self):
        first, second = self.create('first-request-key'), self.create('second-request-key')
        with closing(sqlite3.connect(self.store.path)) as conn:
            nonce, blob = conn.execute('SELECT nonce,payload FROM jobs WHERE id=?', (first,)).fetchone()
            with conn:
                conn.execute('UPDATE jobs SET nonce=?,payload=? WHERE id=?', (nonce, blob, second))
        with self.assertRaises(ServiceError):
            self.store.get(self.scope, second)

    def test_phase_metadata_is_authenticated(self):
        job = self.create()
        with closing(sqlite3.connect(self.store.path)) as conn:
            with conn:
                conn.execute("UPDATE jobs SET phase='completed' WHERE id=?", (job,))
        with self.assertRaises(ServiceError):
            self.store.status(self.scope, job)

    def test_new_nonce_for_each_update(self):
        job = self.create(); row, data = self.store.get(self.scope, job)
        self.store.save(self.scope, job, data, 'preparing')
        updated, _ = self.store.get(self.scope, job)
        self.assertNotEqual(row['nonce'], updated['nonce'])

    def test_restart_pauses_pending_until_current_authorization(self):
        job = self.create(); self.store.close()
        self.store = JobStore(self.root / 'state', self.key); self.addCleanup(self.store.close)
        status = self.store.status(self.scope, job)
        self.assertEqual(status['phase'], 'waiting_authorization')
        self.assertNotIn('request', status); self.assertNotIn('payload', status)


class DurableFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='he-durable-tests-'); cls.addClassCleanup(cls.temp.cleanup)
        cls.pair = Pair(cls.temp.name); cls.addClassCleanup(cls.pair.close); cls.pair.start()
        cls.auth_bytes = cls.pair.env['policy'].read_bytes()

    def setUp(self):
        self.pair.env['policy'].write_bytes(self.auth_bytes)
        self.pair.restart_node()

    def test_submit_poll_result_and_persisted_phase_history(self):
        status, job = submit(self.pair, 'C001', 'async-standard-flow')
        self.assertIn(status, (200, 202))
        done = wait(self.pair, 'C001', job['job_id'])
        status, result = state(self.pair, 'C001', job['job_id'], True)
        self.assertEqual(status, 200); self.assertEqual(result['row_count'], 5)
        phases = {e['phase'] for e in done['events']}
        self.assertTrue({'ready', 'waiting_worker', 'received', 'decrypting', 'completed'} <= phases)

    def test_concurrent_repeated_clicks_create_one_job(self):
        before = worker_count(self.pair)
        with ThreadPoolExecutor(4) as pool:
            responses = list(pool.map(lambda _: submit(self.pair, 'C001', 'parallel-repeated-click'), range(4)))
        self.assertTrue(all(s in (200, 202) for s, _ in responses), responses)
        ids = {v['job_id'] for _, v in responses}; self.assertEqual(len(ids), 1)
        wait(self.pair, 'C001', ids.pop())
        self.assertEqual(worker_count(self.pair), before + 1)

    def test_completed_result_and_idempotency_survive_node_restart(self):
        _, job = submit(self.pair, 'C001', 'completed-restart-key'); wait(self.pair, 'C001', job['job_id'])
        original = state(self.pair, 'C001', job['job_id'], True)
        before = worker_count(self.pair)
        self.pair.restart_node()
        _, repeated = submit(self.pair, 'C001', 'completed-restart-key')
        self.assertEqual(job['job_id'], repeated['job_id'])
        self.assertEqual(original, state(self.pair, 'C001', job['job_id'], True))
        self.assertEqual(before, worker_count(self.pair))

    def test_saved_he_key_recovers_outage_after_node_restart(self):
        self.pair._stop(self.pair.worker_process)
        _, job = submit(self.pair, 'C001', 'durable-network-outage')
        wait(self.pair, 'C001', job['job_id'], ('retryable',))
        self.pair.restart_worker(); self.pair.restart_node()
        _, paused = state(self.pair, 'C001', job['job_id'])
        self.assertEqual(paused['phase'], 'waiting_authorization')
        before = worker_count(self.pair)
        _, repeated = submit(self.pair, 'C001', 'durable-network-outage')
        self.assertEqual(job['job_id'], repeated['job_id'])
        wait(self.pair, 'C001', job['job_id'])
        self.assertEqual(state(self.pair, 'C001', job['job_id'], True)[0], 200)
        self.assertEqual(worker_count(self.pair), before + 1)

    def test_get_job_and_result_require_current_company_permission(self):
        _, job = submit(self.pair, 'C001', 'private-job-result'); wait(self.pair, 'C001', job['job_id'])
        policy = json.loads(self.auth_bytes); policy['principals'][1]['status'] = 'revoked'
        self.pair.env['policy'].write_bytes(canonical(policy))
        status, _ = state(self.pair, 'C001', job['job_id'], True)
        self.assertEqual(status, 401)

    def test_job_is_not_readable_through_other_company_url(self):
        _, job = submit(self.pair, 'C001', 'cross-company-status'); wait(self.pair, 'C001', job['job_id'])
        self.assertEqual(state(self.pair, 'C002', job['job_id'])[0], 404)

    def test_client_lost_submit_reply_reuses_receipt_key(self):
        import experiments.he_inference.job_client as module
        original = module.call; first = [True]
        def lost(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[1] == 'POST' and args[2].endswith('/jobs') and first[0]:
                first[0] = False
                raise ServiceError(503, 'NODE_CONNECTION_UNAVAILABLE')
            return result
        before = worker_count(self.pair)
        folder = self.pair.enterprise
        with patch.object(module, 'call', side_effect=lost):
            result = client_run(f'http://127.0.0.1:{self.pair.node_port}', self.pair.env['header'], 'C001', self.pair.body(),
                folder / 'lost-receipt.json', folder / 'lost-result.json', wait_seconds=30)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(worker_count(self.pair), before + 1)

    def test_client_resume_same_receipt_does_not_recompute(self):
        folder = self.pair.enterprise
        args = (f'http://127.0.0.1:{self.pair.node_port}', self.pair.env['header'], 'C001', self.pair.body(),
                folder / 'repeat-receipt.json', folder / 'repeat-result.json')
        result = client_run(*args, wait_seconds=30); before = worker_count(self.pair)
        again = client_run(*args, wait_seconds=30)
        self.assertEqual(result, again); self.assertEqual(before, worker_count(self.pair))
        self.assertNotIn(self.pair.env['header'], (folder / 'repeat-receipt.json').read_text())

    def test_lost_worker_reply_and_node_restart_use_saved_key_without_exporting_again(self):
        import experiments.he_inference.node_jobs as module
        pair = self.pair; before = worker_count(pair)
        with tempfile.TemporaryDirectory(dir=pair.enterprise) as folder:
            node = EnterpriseNode(pair.env['auth'], pair.env['model_db'], pair.env['snapshot_db'],
                f'http://127.0.0.1:{pair.worker_port}', public_hex(pair.worker_key), pair.node_key)
            node.enable_jobs(folder, pair.state_key_path)
            lost = [False]
            def transport(url, path, payload):
                value = post(url, path, payload)
                if path == '/v1/evaluate' and not lost[0]:
                    lost[0] = True
                    raise ServiceError(503, 'LOST_WORKER_REPLY')
                return value
            try:
                with patch.object(module, 'post', side_effect=transport), patch.object(node.jobs, '_retry'):
                    job = node.jobs.submit('C001', pair.env['header'], 'lost-durable-worker-reply', pair.body())
                    end = time.monotonic() + 30
                    while time.monotonic() < end:
                        status = node.jobs.status('C001', pair.env['header'], job['job_id'])
                        if status['phase'] == 'retryable':
                            break
                        time.sleep(.05)
                    self.assertEqual(status['phase'], 'retryable', status)
                    scope = pair.env['auth'].authorize(pair.env['header'], 'C001')
                    _, saved = node.jobs.store.get(scope, job['job_id'])
                    self.assertIsNotNone(saved['pending'])
                    self.assertNotIn(pair.env['header'], canonical(saved).decode())
            finally:
                node.jobs.close()
            recovered = EnterpriseNode(pair.env['auth'], pair.env['model_db'], pair.env['snapshot_db'],
                f'http://127.0.0.1:{pair.worker_port}', public_hex(pair.worker_key), pair.node_key)
            recovered.enable_jobs(folder, pair.state_key_path)
            try:
                with patch.object(module, 'export_snapshot', side_effect=AssertionError('No new export/context')):
                    same = recovered.jobs.submit('C001', pair.env['header'], 'lost-durable-worker-reply', pair.body())
                    self.assertEqual(same['job_id'], job['job_id'])
                    result = recovered.jobs.wait('C001', pair.env['header'], job['job_id'], 30)
                self.assertTrue(all(r['available'] for r in result['rows']))
                self.assertEqual(worker_count(pair), before + 1)
            finally:
                recovered.jobs.close()

    def test_expired_inference_can_only_fetch_existing_ciphertext_with_fresh_node_signature(self):
        pair = self.pair; env = pair.env
        exported = export_snapshot(env['model_db'], env['snapshot_db'], env['auth'], env['header'], 'C001',
            env['artifacts']['C001'], env['queries']['C001'], '2026-10-03T00:00:00+07:00', public_hex(pair.worker_key))
        package = exported.cloud_package(); p = package['request']['payload']; now = p['created_at']
        with tempfile.TemporaryDirectory(dir=pair.root) as folder, closing(Worker(folder, pair.grants_file, pair.worker_key)) as worker:
            registration = sign(dict(version='he-session-registration/1.0.0', node_verify_key=public_hex(pair.node_key),
                expires_at=p['expires_at'], policy=package['policy']), pair.node_key)
            with patch('experiments.he_inference.worker_server.time.time', return_value=now):
                worker.register(registration); original = worker.score(package['request'])
            retrieval = dict(version='he-result-retrieval/1.0.0', node_verify_key=public_hex(pair.node_key),
                expires_at=now + 460, tenant_id='demo', company_id='C001', session_id=p['session_id'], nonce=p['nonce'],
                request_sha256=sha(canonical(package['request'])), retrieval_id='get_recover_existing')
            with patch('experiments.he_inference.worker_server.time.time', return_value=now + 400):
                with self.assertRaises(ServiceError):
                    worker.score(package['request'])
                self.assertEqual(original, worker.retrieve(sign(retrieval, pair.node_key)))
                wrong = dict(retrieval, request_sha256='0' * 64)
                with self.assertRaises(ServiceError):
                    worker.retrieve(sign(wrong, pair.node_key))
                rogue = Ed25519PrivateKey.generate()
                with self.assertRaises(ServiceError):
                    worker.retrieve(sign(dict(retrieval, node_verify_key=public_hex(rogue)), rogue))
            with closing(sqlite3.connect(worker.store.path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_received_ciphertext_checkpoint_resumes_decrypt_without_network(self):
        import experiments.he_inference.node_jobs as module
        pair = self.pair
        with tempfile.TemporaryDirectory(dir=pair.enterprise) as folder:
            node = EnterpriseNode(pair.env['auth'], pair.env['model_db'], pair.env['snapshot_db'],
                f'http://127.0.0.1:{pair.worker_port}', public_hex(pair.worker_key), pair.node_key)
            node.enable_jobs(folder, pair.state_key_path)
            original = node.jobs.store.save
            def crash_after_receive(scope, job_id, data, phase, reason=None):
                original(scope, job_id, data, phase, reason)
                if phase == 'received':
                    raise SystemExit('simulated process interruption after durable receive')
            try:
                with patch.object(node.jobs.store, 'save', side_effect=crash_after_receive):
                    job = node.jobs.submit('C001', pair.env['header'], 'received-before-decrypt', pair.body())
                    end = time.monotonic() + 30
                    while time.monotonic() < end:
                        status = node.jobs.status('C001', pair.env['header'], job['job_id'])
                        if status['phase'] == 'received':
                            break
                        time.sleep(.05)
                    self.assertEqual(status['phase'], 'received', status)
            finally:
                node.jobs.close()
            recovered = EnterpriseNode(pair.env['auth'], pair.env['model_db'], pair.env['snapshot_db'],
                f'http://127.0.0.1:{pair.worker_port}', public_hex(pair.worker_key), pair.node_key)
            recovered.enable_jobs(folder, pair.state_key_path)
            try:
                with patch.object(module, 'post', side_effect=AssertionError('No network needed after receipt')):
                    recovered.jobs.resume('C001', pair.env['header'], job['job_id'])
                    result = recovered.jobs.wait('C001', pair.env['header'], job['job_id'], 30)
                self.assertEqual(result['row_count'], 5)
                self.assertTrue(all(r['available'] for r in result['rows']))
            finally:
                recovered.jobs.close()


if __name__ == '__main__':
    unittest.main()
