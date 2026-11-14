"""Opt-in HE acceptance tests: install requirements-he.txt first."""
from copy import deepcopy
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import tenseal as ts
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from experiments.he_inference.cloud_worker import evaluate
from experiments.he_inference.demo import fixtures, worker_process, worker_environment
from experiments.he_inference.enterprise import EnterpriseSession
from experiments.he_inference.protocol import (ABS_TOLERANCE, REL_TOLERANCE,
    MAX_CONTEXT, MAX_CIPHER, HEUnavailable, b64, canonical, public_hex, read_json, sha, sign, unb64)


class EncryptedInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='he-acceptance-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.signer = Ed25519PrivateKey.generate()
        cls.samples = {}
        for company in ('C001', 'C002'):
            history, query = fixtures(company)
            s = EnterpriseSession('demo', company, history, history_end=100, evaluation_start=200)
            p, policy = s.prepare(query, public_hex(cls.signer), event_times=[201] * 5, now=1000)
            # Positive worker test uses wall-clock-valid request in a new process.
            real, real_policy = s.prepare(query, public_hex(cls.signer), event_times=[201] * 5)
            response, code, _ = worker_process(real, real_policy, cls.signer, cls.root / company)
            assert code == 0, response
            cls.samples[company] = s, query, p, policy, real, response

    def setUp(self):
        self.session, self.query, p, policy, self.real, self.response = self.samples['C001']
        self.packet = deepcopy(p); self.policy = deepcopy(policy)
        self.pending = deepcopy(self.session.pending)
        self.addCleanup(setattr, self.session, 'pending', self.pending)
        self.case_dir = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.case_dir.cleanup)
        self.ledger = Path(self.case_dir.name) / 'replay.sqlite3'

    def resign(self):
        self.packet = sign(self.packet['payload'], self.session.signer)

    def run_worker(self):
        return evaluate(self.packet, self.policy, self.signer, self.ledger, now=1000)

    def rejects(self, code, callback=None):
        with self.assertRaises(HEUnavailable) as result:
            (callback or self.run_worker)()
        self.assertEqual(result.exception.code, code)

    def test_original_clear_circuit_and_real_encrypted_worker_match_two_companies(self):
        for company, (s, query, _, _, request, response) in self.samples.items():
            with self.subTest(company=company):
                pending = deepcopy(s.pending)
                try:
                    scores = s.open(response, request['payload']['nonce'])
                    self.assertEqual(len(scores), 5)
                    np.testing.assert_allclose(s.model.score(np.asarray(query)), s.clear_circuit(query), atol=1e-10, rtol=1e-10)
                    np.testing.assert_allclose(s.clear_circuit(query), scores, atol=ABS_TOLERANCE, rtol=REL_TOLERANCE)
                finally:
                    s.pending = pending

    def test_public_worker_context_cannot_decrypt(self):
        c = ts.context_from(unb64(self.real['payload']['context'], MAX_CONTEXT), n_threads=1)
        self.assertFalse(c.has_secret_key())
        ct = ts.ckks_vector_from(c, unb64(self.response['payload']['ciphertext'], MAX_CIPHER))
        with self.assertRaises(ValueError):
            ct.decrypt()

    def test_worker_process_does_not_import_enterprise_or_sklearn(self):
        self.assertEqual(self.response['payload']['worker'], dict(has_decryption_key=False, enterprise_imported=False, sklearn_imported=False))

    def test_worker_environment_does_not_forward_enterprise_secrets(self):
        with patch.dict(os.environ, {'AGENT2_PORTAL_SECRET': 'not-a-real-secret', 'AWS_SECRET_ACCESS_KEY': 'test-only',
                                    'PYTHONPATH': 'untrusted-import-directory'}):
            env = worker_environment()
        self.assertNotIn('AGENT2_PORTAL_SECRET', env)
        self.assertNotIn('AWS_SECRET_ACCESS_KEY', env)
        self.assertNotEqual(env['PYTHONPATH'], 'untrusted-import-directory')
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')

    def test_company_contexts_and_models_are_distinct(self):
        first, second = self.samples['C001'][0], self.samples['C002'][0]
        self.assertNotEqual(first.binding['context_sha256'], second.binding['context_sha256'])
        self.assertNotEqual(first.binding['model_id'], second.binding['model_id'])

    def test_plaintext_field_is_rejected_even_with_valid_signature(self):
        self.packet['payload']['features'] = self.query
        self.resign(); self.rejects('REQUEST_FIELDS')

    def test_packet_tamper_is_rejected_before_native_parse(self):
        self.packet['payload']['columns'][0] = b64(b'changed')
        with patch('experiments.he_inference.cloud_worker.ts.context_from', side_effect=AssertionError('native parse')):
            self.rejects('SIGNATURE_INVALID')

    def test_company_mismatch(self):
        self.packet['payload']['company_id'] = 'C002'; self.resign()
        self.rejects('BINDING_MISMATCH')

    def test_tenant_mismatch(self):
        self.packet['payload']['tenant_id'] = 'other'; self.resign()
        self.rejects('BINDING_MISMATCH')

    def test_key_epoch_mismatch(self):
        self.packet['payload']['key_epoch'] = 'other'; self.resign()
        self.rejects('BINDING_MISMATCH')

    def test_model_mismatch(self):
        self.packet['payload']['model_id'] = 'other'; self.resign()
        self.rejects('BINDING_MISMATCH')

    def test_unsupported_profile(self):
        self.packet['payload']['profile'] = 'isolation_forest'; self.resign()
        self.rejects('PROFILE_UNSUPPORTED')

    def test_disabled_policy(self):
        self.policy['enabled'] = False
        self.rejects('HE_POLICY_DISABLED')

    def test_expiry(self):
        self.packet['payload']['expires_at'] = 999; self.resign()
        self.rejects('REQUEST_EXPIRED')

    def test_lifetime_bound(self):
        self.packet['payload']['expires_at'] = 1400; self.resign()
        self.rejects('REQUEST_EXPIRED')

    def test_model_ciphertext_is_pinned(self):
        self.packet['payload']['quadratic'][0] = self.packet['payload']['quadratic'][1]
        self.resign(); self.rejects('MODEL_BINDING')

    def test_context_hash_is_pinned(self):
        self.packet['payload']['context'] = b64(b'changed')
        self.resign(); self.rejects('CONTEXT_HASH')

    def test_private_context_is_rejected_even_if_trusted_hash_is_misconfigured(self):
        raw = self.session.context.serialize(save_secret_key=True, save_galois_keys=False)
        self.packet['payload'].update(context=b64(raw), context_sha256=sha(raw))
        self.policy['context_sha256'] = sha(raw)
        self.resign(); self.rejects('PRIVATE_OR_INCOMPLETE_CONTEXT')

    def test_replay_persists_across_worker_calls(self):
        self.run_worker()
        self.rejects('REPLAY_REJECTED')

    def test_existing_other_database_is_not_migrated(self):
        with closing(sqlite3.connect(self.ledger)) as conn:
            with conn:
                conn.execute('CREATE TABLE unrelated (x TEXT)')
        before = self.ledger.read_bytes()
        self.rejects('REPLAY_STORE_INCOMPATIBLE')
        self.assertEqual(before, self.ledger.read_bytes())

    def test_bad_client_signature(self):
        self.policy['client_verify_key'] = public_hex(Ed25519PrivateKey.generate())
        self.rejects('SIGNATURE_INVALID')

    def test_duplicate_json_fields(self):
        p = Path(self.case_dir.name) / 'bad.json'; p.write_text('{"x":1,"x":2}')
        self.rejects('DUPLICATE_FIELD', lambda: read_json(p))

    def test_missing_nonfinite_bool_features_are_not_zero(self):
        for value in (None, float('nan'), float('inf'), True):
            with self.subTest(value=str(value)):
                self.rejects('HE_INPUT_UNAVAILABLE', lambda: self.session.prepare([[value, 1.0]], public_hex(self.signer), event_times=[201]))

    def test_input_domain(self):
        self.rejects('INPUT_OUT_OF_DOMAIN', lambda: self.session.prepare([[1e6, 1e6]], public_hex(self.signer), event_times=[201]))

    def test_row_budget(self):
        self.rejects('ROW_LIMIT', lambda: self.session.prepare(self.query * 2, public_hex(self.signer), event_times=[201] * 10))

    def test_evaluation_before_history_is_rejected_before_key_creation(self):
        with patch('experiments.he_inference.enterprise.ts.context', side_effect=AssertionError('key generation')):
            self.rejects('TRAIN_EVALUATION_OVERLAP', lambda: EnterpriseSession('demo', 'C001', self.query, history_end=200, evaluation_start=200))

    def test_query_before_evaluation(self):
        self.rejects('BEFORE_EVALUATION', lambda: self.session.prepare(self.query, public_hex(self.signer), event_times=[199] * 5))

    def test_result_tamper_never_reaches_decryption(self):
        response = deepcopy(self.response); response['payload']['ciphertext'] = b64(b'changed')
        with patch('experiments.he_inference.enterprise.ts.ckks_vector_from', side_effect=AssertionError('decryption')):
            self.rejects('SIGNATURE_INVALID', lambda: self.session.open(response, self.real['payload']['nonce']))

    def test_result_from_other_company_is_rejected_before_decryption(self):
        response = deepcopy(self.response); response['payload']['company_id'] = 'C002'
        response = sign(response['payload'], self.signer)
        self.rejects('RESULT_BINDING', lambda: self.session.open(response, self.real['payload']['nonce']))

    def test_result_from_other_request_is_rejected(self):
        response = deepcopy(self.response); response['payload']['request_sha256'] = '0' * 64
        response = sign(response['payload'], self.signer)
        self.rejects('RESULT_BINDING', lambda: self.session.open(response, self.real['payload']['nonce']))

    def test_result_can_only_be_opened_once(self):
        nonce = self.real['payload']['nonce']
        self.session.open(self.response, nonce)
        self.rejects('RESULT_NOT_PENDING', lambda: self.session.open(self.response, nonce))

    def test_no_fit_or_decrypt_is_called_by_evaluation(self):
        with patch('tenseal.CKKSVector.decrypt', side_effect=AssertionError('decrypt')), \
             patch('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit', side_effect=AssertionError('fit')):
            self.assertIn('ciphertext', self.run_worker()['payload'])

    def test_ciphertexts_are_randomized(self):
        packet, _ = self.session.prepare(self.query, public_hex(self.signer), event_times=[201] * 5)
        self.assertNotEqual(packet['payload']['columns'], self.real['payload']['columns'])

    def test_zero_and_domain_boundary_with_maximum_batch(self):
        z = np.asarray([[0, 0], [8, -8], [-8, 8], [8, 8], [-8, -8], [1, -1], [-1, 1], [.2, .3]], dtype=float)
        x = (z + self.session.model.cov_.location_) * self.session.model.std_ + self.session.model.mean_
        # Roundoff in reconstructing x must stay inside the declared domain.
        x[1:5] = ((z[1:5] * (1 - 1e-12)) + self.session.model.cov_.location_) * self.session.model.std_ + self.session.model.mean_
        packet, policy = self.session.prepare(x, public_hex(self.signer), event_times=[201] * 8)
        response, code, _ = worker_process(packet, policy, self.signer, Path(self.case_dir.name) / 'boundary')
        self.assertEqual(code, 0)
        scores = self.session.open(response, packet['payload']['nonce'])
        np.testing.assert_allclose(self.session.clear_circuit(x), scores, atol=ABS_TOLERANCE, rtol=REL_TOLERANCE)


if __name__ == '__main__':
    unittest.main()
