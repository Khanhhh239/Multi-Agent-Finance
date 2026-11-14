"""Windows current-user key protection and compatibility without rotating data."""
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from experiments.he_inference.demo import worker_environment
from experiments.he_inference.http_common import ServiceError
from experiments.he_inference.key_manager import (PROVIDER, create_key, load_key, protect_key)
from experiments.he_inference.node_job_store import JobStore


class LocalKeyProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='he-local-keys-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_dpapi_roundtrip_never_stores_plain_key(self):
        path = self.root / 'state.json'; created = create_key(path)
        loaded = load_key(path, required_provider=PROVIDER)
        self.assertEqual(created.material, loaded.material)
        self.assertNotIn(created.material.hex(), path.read_text())
        self.assertNotIn(created.material.hex(), repr(loaded))

    def test_two_fresh_keys_are_distinct(self):
        first, second = create_key(self.root / 'a.json'), create_key(self.root / 'b.json')
        self.assertNotEqual(first.key_id, second.key_id)

    def test_existing_key_file_is_never_overwritten(self):
        path = self.root / 'state.json'; create_key(path); before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            create_key(path)
        self.assertEqual(before, path.read_bytes())

    def test_wrong_purpose_is_rejected(self):
        path = self.root / 'state.json'; create_key(path)
        with self.assertRaises(ServiceError):
            load_key(path, purpose='node-signing')

    def test_signing_public_key_survives_wrapping(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        material = Ed25519PrivateKey.generate().private_bytes_raw()
        path = self.root / 'signing.json'; protected = protect_key(material, path, purpose='node-signing')
        loaded = load_key(path, purpose='node-signing', required_provider=PROVIDER)
        self.assertEqual(protected.public_info()['verify_key'], loaded.public_info()['verify_key'])
        self.assertEqual(material, loaded.material)

    def test_tampered_ciphertext_is_not_accepted(self):
        path = self.root / 'state.json'; create_key(path)
        value = json.loads(path.read_bytes()); value['protected'] = value['protected'][:-8] + 'AAAAAAAA'
        path.write_text(json.dumps(value))
        with self.assertRaises(ServiceError):
            load_key(path)

    def test_tampered_key_id_is_not_accepted(self):
        path = self.root / 'state.json'; create_key(path)
        value = json.loads(path.read_bytes()); value['key_id'] = 'key_' + '0' * 64
        path.write_text(json.dumps(value))
        with self.assertRaises(ServiceError):
            load_key(path)

    def test_unknown_provider_cannot_fall_back_to_plaintext(self):
        path = self.root / 'state.json'; create_key(path)
        value = json.loads(path.read_bytes()); value['provider'] = 'unsupported-provider'
        path.write_text(json.dumps(value))
        with self.assertRaises(ServiceError):
            load_key(path)

    def test_plaintext_key_is_rejected_in_protected_mode(self):
        path = self.root / 'legacy.hex'; path.write_text(secrets.token_hex(32))
        with self.assertRaises(ServiceError) as result:
            load_key(path, required_provider=PROVIDER)
        self.assertEqual(result.exception.code, 'NODE_KEY_PROTECTION_REQUIRED')

    def test_missing_key_is_not_created(self):
        path = self.root / 'absent.json'
        with self.assertRaises(ServiceError):
            load_key(path)
        self.assertFalse(path.exists())

    def test_protected_provider_unavailable_does_not_fall_back(self):
        path = self.root / 'state.json'; create_key(path)
        with patch('experiments.he_inference.key_manager.os.name', 'posix'):
            with self.assertRaises(ServiceError) as result:
                load_key(str(path))
        self.assertEqual(result.exception.code, 'NODE_KEY_PROVIDER_UNAVAILABLE')

    def test_current_user_fresh_process_can_unprotect_with_sanitized_environment(self):
        path = self.root / 'state.json'; created = create_key(path)
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, '-X', 'utf8', '-B', '-m', 'experiments.he_inference.key_manager', 'inspect', '--input', str(path)]
        child = subprocess.run(command, cwd=root, env=worker_environment(), capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0)
        result = json.loads(child.stdout); self.assertEqual(result['key_id'], created.key_id)
        self.assertNotIn(created.material.hex(), child.stdout + child.stderr)

    def test_migration_keeps_old_jobs_and_idempotency_readable(self):
        legacy = self.root / 'legacy.hex'; legacy.write_text(secrets.token_hex(32))
        scope = AccessScope('demo', frozenset({'C001'}), 'reader', frozenset({'data.import'}))
        original = load_key(legacy)
        store = JobStore(self.root / 'state', legacy)
        body = dict(snapshot_id='snp_fixture', artifact_id='mth_fixture', as_of='2026-10-01T00:00:00+00:00')
        job = store.create(scope, 'stable-migration-key', body); store.close()
        protected = self.root / 'protected.json'; protect_key(original.material, protected)
        migrated = JobStore(self.root / 'state', protected, required_provider=PROVIDER)
        try:
            self.assertEqual(job, migrated.create(scope, 'stable-migration-key', body))
            self.assertEqual(migrated.get(scope, job)[1]['request'], body)
        finally:
            migrated.close()
        self.assertTrue(legacy.exists())  # Migration is explicit, never destructive.

    def test_wrong_protected_key_does_not_rewrite_job_database(self):
        key = self.root / 'key.json'; create_key(key)
        store = JobStore(self.root / 'state', key, required_provider=PROVIDER); store.close()
        before = store.path.read_bytes(); other = self.root / 'other.json'; create_key(other)
        with self.assertRaises(ServiceError):
            JobStore(self.root / 'state', other, required_provider=PROVIDER)
        self.assertEqual(before, store.path.read_bytes())

    def test_strict_node_config_rejects_legacy_signing_key_before_serving(self):
        key = self.root / 'signing.hex'; raw = secrets.token_hex(32); key.write_text(raw)
        config = dict(version='he-enterprise-service/1.2.0', key_protection=PROVIDER,
            auth_file=str(self.root / 'auth.json'), model_db=str(self.root / 'models.sqlite3'),
            snapshot_db=str(self.root / 'snapshots.sqlite3'), worker_url='http://127.0.0.1:8868',
            worker_verify_key='0' * 64, provisioning_key_file=str(key), state_dir=str(self.root / 'state'),
            state_key_file=str(self.root / 'state-key.json'))
        path = self.root / 'config.json'; path.write_text(json.dumps(config))
        ready = self.root / 'ready.json'; root = Path(__file__).resolve().parents[1]
        command = [sys.executable, '-X', 'utf8', '-B', '-m', 'experiments.he_inference.enterprise_server',
                   '--config', str(path), '--port', '0', '--ready-file', str(ready)]
        child = subprocess.run(command, cwd=root, env=worker_environment(), capture_output=True, text=True, timeout=15)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn('NODE_KEY_PROTECTION_REQUIRED', child.stderr)
        self.assertNotIn(raw, child.stdout + child.stderr)
        self.assertFalse(ready.exists()); self.assertFalse((self.root / 'state/jobs.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
