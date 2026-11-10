"""Tests for WebAuthn biometric (FaceID) registration and verification."""
import base64
import hashlib
import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from portal import server


class BiometricAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.sec_file = self.work / 'intake_security.json'
        self.audit_file = self.work / 'audit.jsonl'
        self.patchers = [
            patch.object(server, 'SECURITY_FILE', self.sec_file),
            patch.object(server, 'AUDIT_FILE', self.audit_file),
            patch.object(server, 'BIOMETRIC_CHALLENGES', {}),
            patch.object(server, 'FAILS', {'n': 0, 'until': 0.0}),
            patch.object(server, 'SESSIONS', {}),
        ]
        for p in self.patchers:
            p.start()
        # Setup initial password
        server.set_password('SecretP@ss123', 'SecretP@ss123')

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_challenge_generation_and_expiry(self):
        chal = server.create_biometric_challenge()
        self.assertTrue(bool(chal))
        self.assertIn(chal, server.BIOMETRIC_CHALLENGES)
        # Test expired challenge cleanup
        with patch('time.time', return_value=server.BIOMETRIC_CHALLENGES[chal] + 10):
            server.create_biometric_challenge()
            self.assertNotIn(chal, server.BIOMETRIC_CHALLENGES)

    def test_full_biometric_register_verify_and_remove(self):
        self.assertFalse(server.has_biometric())

        # 1. Generate ECDSA P-256 key pair simulating authenticator
        private_key = ec.generate_private_key(ec.SECP256R1())
        pub_der = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
        pub_b64 = server.b64_encode(pub_der)
        cred_id = secrets.token_urlsafe(32)

        # 2. Register biometric
        server.register_biometric(cred_id, pub_b64)
        self.assertTrue(server.has_biometric())

        # 3. Request challenge
        challenge = server.create_biometric_challenge()

        # 4. Construct clientDataJSON and authenticatorData
        client_data_obj = {
            'type': 'webauthn.get',
            'challenge': challenge,
            'origin': 'http://127.0.0.1:8800'
        }
        client_data_raw = json.dumps(client_data_obj).encode('utf-8')
        client_data_b64 = server.b64_encode(client_data_raw)

        rp_hash = hashlib.sha256(b'127.0.0.1').digest()
        flags = bytes([0x01 | 0x04]) # UP and UV
        counter = bytes([0, 0, 0, 1])
        auth_data = rp_hash + flags + counter
        auth_data_b64 = server.b64_encode(auth_data)

        # 5. Sign authenticatorData + sha256(clientDataJSON)
        signed_payload = auth_data + hashlib.sha256(client_data_raw).digest()
        sig = private_key.sign(signed_payload, ec.ECDSA(hashes.SHA256()))
        sig_b64 = server.b64_encode(sig)

        # 6. Verify and get session token
        token = server.verify_biometric(cred_id, client_data_b64, auth_data_b64, sig_b64)
        self.assertTrue(bool(token))
        self.assertGreater(server.session_left(token), 0)

        # 7. Test Anti-replay: repeating with same challenge must fail
        with self.assertRaisesRegex(ValueError, 'hết hạn hoặc bị phát lại'):
            server.verify_biometric(cred_id, client_data_b64, auth_data_b64, sig_b64)

        # 8. Remove biometric
        server.remove_biometric()
        self.assertFalse(server.has_biometric())

    def test_tampered_signature_is_rejected(self):
        private_key = ec.generate_private_key(ec.SECP256R1())
        pub_der = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
        cred_id = secrets.token_urlsafe(32)
        server.register_biometric(cred_id, server.b64_encode(pub_der))

        challenge = server.create_biometric_challenge()
        client_data_raw = json.dumps({'type': 'webauthn.get', 'challenge': challenge, 'origin': 'http://127.0.0.1:8800'}).encode()
        auth_data = hashlib.sha256(b'127.0.0.1').digest() + bytes([0x05, 0, 0, 0, 1])

        # Wrong key signature
        attacker_key = ec.generate_private_key(ec.SECP256R1())
        fake_sig = attacker_key.sign(auth_data + hashlib.sha256(client_data_raw).digest(), ec.ECDSA(hashes.SHA256()))

        with self.assertRaisesRegex(ValueError, 'từ chối'):
            server.verify_biometric(cred_id, server.b64_encode(client_data_raw), server.b64_encode(auth_data), server.b64_encode(fake_sig))

    def test_ai_face_descriptor_enroll_verify_and_mismatch(self):
        self.assertFalse(server.has_biometric())
        enrolled_face = [0.05 * (i % 10) for i in range(128)]
        server.save_face_descriptor(enrolled_face)
        self.assertTrue(server.has_biometric())

        # Test valid face scan (very close Euclidean distance)
        same_person_scan = [v + 0.002 for v in enrolled_face]
        token = server.verify_face_descriptor(same_person_scan)
        self.assertTrue(bool(token))

        # Test different person scan (far Euclidean distance)
        different_person_scan = [-v for v in enrolled_face]
        with self.assertRaisesRegex(ValueError, 'Khuôn mặt không khớp'):
            server.verify_face_descriptor(different_person_scan)

        # Test remove
        server.remove_biometric()
        self.assertFalse(server.has_biometric())


if __name__ == '__main__':
    unittest.main()
