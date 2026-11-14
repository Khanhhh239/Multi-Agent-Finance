"""Contract & security tests for `c3` profile support in `service.Worker`."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.he4 import VERSION
from experiments.he4.service import Worker
from experiments.he_inference.http_common import ServiceError
from experiments.he_inference.protocol import public_hex, sha, sign

BUILDS_ROOT = Path(r'D:\agent22\.runtime\he4')


class C3WorkerContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.node_key = Ed25519PrivateKey.generate()
        self.worker_key = Ed25519PrivateKey.generate()
        self.grants = root / 'grants.json'
        self.grants.write_text(
            json.dumps(
                dict(
                    version='he-worker-grants/1.0.0',
                    grants=[
                        dict(
                            tenant_id='t',
                            company_id='C001',
                            node_verify_key=public_hex(self.node_key),
                            active=True,
                        )
                    ],
                )
            ),
            encoding='utf-8',
        )
        self.state_dir = root / 'state'

    def _packet(self, fields):
        import time

        return sign(
            dict(
                version=VERSION,
                tenant_id='t',
                company_id='C001',
                node_verify_key=public_hex(self.node_key),
                expires_at=int(time.time()) + 120,
                **fields,
            ),
            self.node_key,
        )

    def test_v1_worker_without_c3_rejects_c3_profile(self):
        builds = {
            'rules': BUILDS_ROOT / 'build-rules-difference-v1',
            'graph': BUILDS_ROOT / 'build-graph-difference-v1',
            'statistics': BUILDS_ROOT / 'build-statistics-v1',
        }
        worker = Worker(self.state_dir, self.grants, self.worker_key, builds)
        self.addCleanup(worker.close)
        c3_manifest = json.loads((BUILDS_ROOT / 'build-c3-v1' / 'manifest.json').read_bytes())
        pkt = self._packet(
            dict(
                profile='c3',
                circuit_sha256=c3_manifest['files']['server.zip'],
                evaluation_keys_sha256='0' * 64,
                arguments_sha256=['0' * 64] * 10,
                session_id='s1',
                nonce='n1',
            )
        )
        with self.assertRaises(ServiceError) as ctx:
            worker.score(pkt)
        self.assertEqual(ctx.exception.code, 'HE4_CIRCUIT_INCOMPATIBLE')

    def test_c3_worker_enforces_exact_ten_argument_hashes_and_pinned_circuit(self):
        c3_dir = BUILDS_ROOT / 'build-c3-v1'
        c3_manifest = json.loads((c3_dir / 'manifest.json').read_bytes())
        c3_sha = c3_manifest['files']['server.zip']
        worker = Worker(self.state_dir, self.grants, self.worker_key, {'c3': c3_dir})
        self.addCleanup(worker.close)

        scope = worker.blobs.scope('t', 'C001', public_hex(self.node_key))
        blob = b'dummy-cipher-payload'
        h = sha(blob)
        worker.blobs.put(scope, h, len(blob), io.BytesIO(blob))

        # Wrong argument count (6 instead of 10) rejected cleanly before native launch
        bad_pkt = self._packet(
            dict(
                profile='c3',
                circuit_sha256=c3_sha,
                evaluation_keys_sha256=h,
                arguments_sha256=[h] * 6,
                session_id='s2',
                nonce='n2',
            )
        )
        with self.assertRaises(ServiceError) as ctx:
            worker.score(bad_pkt)
        self.assertEqual(ctx.exception.code, 'HE4_ARGUMENTS')

        # Wrong circuit hash rejected cleanly before native launch
        bad_circuit = self._packet(
            dict(
                profile='c3',
                circuit_sha256='f' * 64,
                evaluation_keys_sha256=h,
                arguments_sha256=[h] * 10,
                session_id='s3',
                nonce='n3',
            )
        )
        with self.assertRaises(ServiceError) as ctx2:
            worker.score(bad_circuit)
        self.assertEqual(ctx2.exception.code, 'HE4_CIRCUIT_INCOMPATIBLE')


if __name__ == '__main__':
    unittest.main()

