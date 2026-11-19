"""R2 End-to-End Integration Tests: Worker 8870 Lifecycle + Real Concrete FHE LR Training."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from finance_input import AccessScope

from portal.agent2_he_training_runtime import TrainingLinuxRuntime
from portal.agent2_he4_runtime import linux_path
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.import_files import ImportFailure, canonical
from sme_fraud.lr_fhe_training import (
    LRFHETrainingService,
    SUPPORTED_FEATURES,
    _verify_ciphertexts_preflight,
)
from sme_fraud.review_server import make_server
from test_portal_auth import PortalHarness

REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGED_ROOT = REPO_ROOT / 'agent2' / '.runtime' / 'he-training-managed-v1'
CLOUD_BUNDLE = MANAGED_ROOT / 'cloud' / 'code'
CLOUD_CFG = MANAGED_ROOT / 'cloud' / 'worker-config.json'
BUILD_DIR = MANAGED_ROOT / 'cloud' / 'build'
ENTERPRISE_ROOT = MANAGED_ROOT / 'enterprise'
WSL_PYTHON = '/home/sang/.local/share/agent2/he4/bin/python'
WSL_DISTRO = 'Debian'


def _make_isolated_worker_config(tmp: Path, port: int) -> tuple[Path, Path, str]:
    """Create isolated worker-config.json & runtime-config.json sharing read-only keys/build, isolated state DB."""
    orig = json.loads(CLOUD_CFG.read_text(encoding='utf-8'))
    state_dir = tmp / 'cloud_state'
    state_dir.mkdir(parents=True, exist_ok=True)
    wcfg = dict(orig, state=linux_path(state_dir))
    wcfg_path = tmp / 'worker-config.json'
    wcfg_path.write_text(json.dumps(wcfg, ensure_ascii=False), encoding='utf-8')

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pub_hex = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex((MANAGED_ROOT / 'cloud' / 'worker-signing.key').read_text().strip())
    ).public_key().public_bytes_raw().hex()

    # Copy enterprise C001/C002 key dirs using hardlinks so live enterprise dirs remain untouched
    ent_copy = tmp / 'enterprise'
    for cid in ('C001', 'C002'):
        src_c = ENTERPRISE_ROOT / cid
        dst_c = ent_copy / cid
        dst_c.mkdir(parents=True, exist_ok=True)
        for f in ('enterprise.json', 'wrapping.dpapi.json', 'node-signing.dpapi.json'):
            shutil.copy2(src_c / f, dst_c / f)
        (dst_c / 'crypto').mkdir(exist_ok=True)
        for f in ('context.sealed', 'evaluation.keys'):
            try:
                (dst_c / 'crypto' / f).hardlink_to(src_c / 'crypto' / f)
            except OSError:
                shutil.copy2(src_c / 'crypto' / f, dst_c / 'crypto' / f)

    rt_cfg = {
        'worker_url': f'http://127.0.0.1:{port}',
        'worker_verify_key': pub_hex,
        'build': str(BUILD_DIR),
        'enterprise_root': str(ent_copy),
        'linux_python': WSL_PYTHON,
        'distro': WSL_DISTRO,
    }
    rt_path = tmp / 'batch-training-runtime.json'
    rt_path.write_text(json.dumps(rt_cfg, ensure_ascii=False), encoding='utf-8')
    return wcfg_path, rt_path, pub_hex


class LRFHER2Tests(unittest.TestCase):
    def setUp(self):
        tmp_base = REPO_ROOT / '.runtime' / 'tmp_r2_tests'
        tmp_base.mkdir(parents=True, exist_ok=True)
        self.tmp_ctx = tempfile.TemporaryDirectory(dir=tmp_base)
        self.tmp = Path(self.tmp_ctx.name)
        self.scope_c1 = AccessScope('demo', frozenset({'C001'}), 'director_c1', frozenset({'data.import', 'evidence.verify', 'model.fit'}))
        self.scope_c1_acct = AccessScope('demo', frozenset({'C001'}), 'acct_c1', frozenset({'data.import'}))
        self.scope_c2 = AccessScope('demo', frozenset({'C002'}), 'director_c2', frozenset({'data.import', 'evidence.verify', 'model.fit'}))

    def tearDown(self):
        self.tmp_ctx.cleanup()

    def test_01_portal_worker_lifecycle_health_timeout_and_controlled_restart(self):
        port = 18871
        wcfg_path, _, _ = _make_isolated_worker_config(self.tmp, port)
        rt = TrainingLinuxRuntime(
            {
                'bundle': str(CLOUD_BUNDLE),
                'config': str(wcfg_path),
                'port': port,
                'distro': WSL_DISTRO,
                'python': WSL_PYTHON,
            },
            self.tmp / 'logs',
            start_timeout=30.0,
            health_timeout=2.0,
        )
        try:
            rt.validate_bundle()
            st_before = rt.state()
            self.assertEqual(st_before['status'], 'stopped')
            self.assertFalse(st_before['ready'])

            st_up = rt.start()
            self.assertTrue(st_up['ready'])
            self.assertEqual(st_up['status'], 'ready')
            self.assertTrue(st_up['owned'])
            self.assertTrue(st_up['batch_training'])
            self.assertIsNotNone(st_up['latency_ms'])

            st_re = rt.restart()
            self.assertTrue(st_re['ready'])
            self.assertEqual(st_re['restart_count'], 1)
        finally:
            rt.stop()
        self.assertEqual(rt.state()['status'], 'stopped')

    def test_02_adapter_2_feature_lock_and_preflight_crypto_no_plaintext_fallback(self):
        wcfg_path, rt_path, _ = _make_isolated_worker_config(self.tmp, 19998)
        svc = LRFHETrainingService(
            self.tmp / 'lr.sqlite3',
            runtime_config_path=rt_path,
            worker_config_path=wcfg_path,
            http_timeout=1.0,
        )

        # Valid dataset summary
        plan = svc.prepare_dataset(self.scope_c1, {'source_mode': 'verified_test_dataset', 'batch_count': 2, 'epochs': 1})
        self.assertEqual(plan['valid_samples'], 8)
        self.assertEqual(plan['label_0_count'], 4)
        self.assertEqual(plan['label_1_count'], 4)
        self.assertEqual(plan['supported_feature_count'], 2)
        self.assertEqual(plan['total_system_features'], 33)
        self.assertFalse(plan['allow_33_features'])

        # Reject 33 features strictly!
        with self.assertRaises(ImportFailure) as ctx33:
            svc.prepare_dataset(
                self.scope_c1,
                {'source_mode': 'verified_test_dataset', 'selected_features': [f'f_{i}' for i in range(33)]},
            )
        self.assertEqual(ctx33.exception.code, 'CIRCUIT_FEATURE_LIMIT_EXCEEDED')

        # Reject batch_count * epochs > 4
        with self.assertRaises(ImportFailure) as ctx_lim:
            svc.prepare_dataset(self.scope_c1, {'source_mode': 'verified_test_dataset', 'batch_count': 3, 'epochs': 2})
        self.assertEqual(ctx_lim.exception.code, 'BATCH_UPDATE_LIMIT')

        # Reject plaintext leak & tampered hash in ciphertext preflight
        import base64
        import hashlib
        plain_bytes = b'[[1,0],[0,1],[1,1],[0,0]]' * 3
        plain_b64 = base64.b64encode(plain_bytes).decode('ascii')
        plain_sha = hashlib.sha256(plain_bytes).hexdigest()
        with self.assertRaises(ImportFailure) as ctx_ct:
            _verify_ciphertexts_preflight(
                [{'index': 0, 'x_cipher': plain_b64, 'x_cipher_sha256': '0' * 64}],
                [],
                {'weights_cipher': plain_b64, 'weights_cipher_sha256': plain_sha},
            )
        self.assertEqual(ctx_ct.exception.code, 'CIPHERTEXT_PREFLIGHT_FAILED')

        json_plain = b'[{"x":[1,0],"y":1},{"x":[0,1],"y":0}]'
        with self.assertRaises(ImportFailure) as ctx_plain:
            _verify_ciphertexts_preflight(
                [{'index': 0, 'x_cipher': base64.b64encode(json_plain).decode('ascii'), 'x_cipher_sha256': hashlib.sha256(json_plain).hexdigest()}],
                [],
                {'weights_cipher': base64.b64encode(json_plain).decode('ascii'), 'weights_cipher_sha256': hashlib.sha256(json_plain).hexdigest()},
            )
        self.assertEqual(ctx_plain.exception.code, 'CIPHERTEXT_PREFLIGHT_FAILED')

        # Worker down -> FHE training MUST fail with ZERO plaintext fallback!
        with self.assertRaises(ImportFailure) as ctx_down:
            svc.start_training(
                self.scope_c1,
                {'mode': 'fhe_cloud_ciphertext', 'source_mode': 'verified_test_dataset', 'batch_count': 2, 'epochs': 1},
                'test-down-1',
            )
        self.assertEqual(ctx_down.exception.code, 'HE_TRAINING_WORKER_UNAVAILABLE')

        # Tampered evaluation key grant -> FHE inspection fails BEFORE train!
        bad_wcfg = json.loads(wcfg_path.read_text(encoding='utf-8'))
        bad_wcfg['grants'][0]['evaluation_keys_sha256'] = 'f' * 64
        wcfg_path.write_text(json.dumps(bad_wcfg), encoding='utf-8')
        crypto_bad = svc.inspect_crypto_context(self.scope_c1, verify_eval_key_hash=True)
        self.assertFalse(crypto_bad['ready_for_fhe'])
        self.assertFalse(crypto_bad['keys']['evaluation_key_verified'])

    def test_03_real_concrete_fhe_e2e_checkpoint_resume_duplicate_guard_validation_and_http_rbac(self):
        port = 18872
        wcfg_path, rt_path, _ = _make_isolated_worker_config(self.tmp, port)
        worker_rt = TrainingLinuxRuntime(
            {
                'bundle': str(CLOUD_BUNDLE),
                'config': str(wcfg_path),
                'port': port,
                'distro': WSL_DISTRO,
                'python': WSL_PYTHON,
            },
            self.tmp / 'logs',
            start_timeout=30.0,
            health_timeout=2.0,
        )
        worker_rt.start()
        try:
            svc = LRFHETrainingService(
                self.tmp / 'lr-e2e.sqlite3',
                runtime_config_path=rt_path,
                worker_config_path=wcfg_path,
                http_timeout=3.0,
            )

            # 1. Mode A: Local quantized reference on small valid labeled dataset
            ref_res = svc.start_training(
                self.scope_c1,
                {'mode': 'local_quantized_reference', 'source_mode': 'verified_test_dataset', 'batch_count': 2, 'epochs': 1},
                'idem-ref-001',
            )
            ref_job = ref_res['job']
            self.assertEqual(ref_job['mode'], 'local_quantized_reference')
            self.assertFalse(ref_job['native_fhe_executed'])
            self.assertEqual(ref_job['completed_updates'], 2)
            self.assertTrue(ref_job['validation']['implementation_error']['pass'])

            # 2. Mode B: REAL Concrete 2.11.0 FHE via Worker 8870 (confirm first with defer_execution=True)
            fhe_init = svc.start_training(
                self.scope_c1,
                {
                    'mode': 'fhe_cloud_ciphertext',
                    'source_mode': 'verified_test_dataset',
                    'batch_count': 2,
                    'epochs': 1,
                    'defer_execution': True,
                },
                'idem-fhe-001',
            )
            job_id = fhe_init['job']['job_id']
            self.assertTrue(job_id.startswith('lrfhe_'))
            self.assertTrue(fhe_init['job']['worker_job_id'].startswith('btr_'))
            self.assertEqual(fhe_init['job']['completed_updates'], 0)
            self.assertEqual(fhe_init['job']['artifact_stage'], 'train_checkpoint')
            self.assertTrue(fhe_init['job']['is_train_checkpoint'])
            self.assertFalse(fhe_init['job']['is_releasable_model'])
            self.assertTrue(fhe_init['job']['preflight']['evaluation_key_verified'])
            self.assertTrue(fhe_init['job']['preflight']['ciphertext_verified'])

            # Cannot promote raw train_checkpoint before validation!
            with self.assertRaises(ImportFailure) as ctx_prom_early:
                svc.promote_to_releasable_model(
                    self.scope_c1,
                    {'job_id': job_id, 'reason': 'Attempt premature release of checkpoint', 'reviewed_checked': True},
                    'idem-prom-early',
                )
            self.assertEqual(ctx_prom_early.exception.code, 'CHECKPOINT_NOT_VALIDATED')

            # 3. Execute FHE SGD steps via Resume (from cursor 0 -> 2/2)
            run_res = svc.resume_job(
                self.scope_c1,
                {'job_id': job_id, 'expected_cursor': 0, 'auto_decrypt': False},
                'idem-resume-001',
            )
            run_job = run_res['job']
            self.assertEqual(run_job['completed_updates'], 2)
            self.assertEqual(run_job['total_updates'], 2)
            self.assertEqual(run_job['status'], 'checkpoint_completed')
            self.assertEqual(run_job['artifact_stage'], 'train_checkpoint')
            self.assertFalse(run_job['is_releasable_model'])
            self.assertEqual(len(run_job['checkpoints']), 3)  # cursor 0, 1, 2

            # 4. Duplicate batch rejection on resume!
            with self.assertRaises(ImportFailure) as ctx_dup1:
                svc.resume_job(self.scope_c1, {'job_id': job_id, 'expected_cursor': 0}, 'idem-dup-1')
            self.assertEqual(ctx_dup1.exception.code, 'DUPLICATE_BATCH_ON_RESUME')

            with self.assertRaises(ImportFailure) as ctx_dup2:
                svc.resume_job(self.scope_c1, {'job_id': job_id, 'batch_index': 0, 'epoch': 1}, 'idem-dup-2')
            self.assertEqual(ctx_dup2.exception.code, 'DUPLICATE_BATCH_ON_RESUME')

            with self.assertRaises(ImportFailure) as ctx_dup3:
                svc.resume_job(self.scope_c1, {'job_id': job_id, 'step_cursor': 1}, 'idem-dup-3')
            self.assertEqual(ctx_dup3.exception.code, 'DUPLICATE_BATCH_ON_RESUME')

            # Idempotent resume when already completed (no re-execution)
            idem_done = svc.resume_job(self.scope_c1, {'job_id': job_id, 'expected_cursor': 2}, 'idem-done-1')
            self.assertTrue(idem_done['already_completed'])
            self.assertEqual(idem_done['new_updates_applied'], 0)

            # 5. Authorization check on local decryption + cross-company isolation
            with self.assertRaises(ImportFailure) as ctx_acct:
                svc.decrypt_and_validate(self.scope_c1_acct, {'job_id': job_id}, 'idem-dec-acct')
            self.assertEqual(ctx_acct.exception.code, 'DECRYPT_PERMISSION_DENIED')

            with self.assertRaises(ImportFailure) as ctx_c2:
                svc.decrypt_and_validate(self.scope_c2, {'job_id': job_id}, 'idem-dec-c2')
            self.assertEqual(ctx_c2.exception.code, 'LR_FHE_JOB_NOT_FOUND')

            # 6. Authorized local decryption + parity & quantization comparison!
            dec_res = svc.decrypt_and_validate(self.scope_c1, {'job_id': job_id}, 'idem-dec-ok')
            dec_job = dec_res['job']
            self.assertTrue(dec_job['native_fhe_executed'])
            self.assertTrue(dec_job['decrypted_model']['decrypted_locally'])
            self.assertEqual(dec_job['decrypted_model']['weights_code'], ref_job['decrypted_model']['weights_code'])

            val = dec_job['validation']
            # Exact parity with quantized oracle -> 0 implementation error!
            self.assertTrue(val['implementation_error']['pass'])
            self.assertEqual(val['implementation_error']['weight_max_abs_diff'], 0.0)
            self.assertEqual(val['implementation_error']['loss_abs_diff'], 0.0)
            self.assertEqual(val['implementation_error']['pred_prob_max_abs_diff'], 0.0)
            # Quantization error vs float LR explicitly measured & separated!
            self.assertIn('weight_max_abs_diff', val['quantization_error'])
            self.assertIn('loss_abs_diff', val['quantization_error'])
            self.assertIn('class_agreement_rate', val['quantization_error'])
            self.assertTrue(val['quantization_error']['within_standard'])
            self.assertEqual(dec_job['artifact_stage'], 'validated_checkpoint')
            self.assertFalse(dec_job['is_releasable_model'])

            # 7. Explicit promotion: train_checkpoint -> releasable_model
            prom_res = svc.promote_to_releasable_model(
                self.scope_c1,
                {
                    'job_id': job_id,
                    'reason': 'Đã đối chiếu giải mã local khớp oracle lượng tử hóa (0 lỗi triển khai) và sai số lượng tử hóa trong chuẩn.',
                    'reviewed_checked': True,
                },
                'idem-prom-ok',
            )
            prom_job = prom_res['job']
            self.assertEqual(prom_job['artifact_stage'], 'releasable_model')
            self.assertTrue(prom_job['is_releasable_model'])
            self.assertFalse(prom_job['is_train_checkpoint'])
            self.assertTrue(prom_res['releasable_model']['version_tag'].startswith('C001-lr-fhe-'))
        finally:
            worker_rt.stop()

    def test_04_http_rbac_and_33_feature_rejection(self):
        from sme_fraud.snapshots import SnapshotStore
        with PortalHarness() as h:
            h.agent.shutdown()
            h.agent.server_close()
            snap_store = SnapshotStore(self.tmp / 'snaps.sqlite3')
            res_obj = AnalysisResources(self.tmp / 'models.sqlite3', self.tmp / 'bindings.json')
            h.agent = make_server(0, h.authorizer, snap_store, res_obj)
            h.agent.daemon_threads = False
            import portal.server as portal_mod
            portal_mod.CFG['agents']['agent2']['port'] = h.agent.server_port
            t = threading.Thread(target=h.agent.serve_forever, daemon=True)
            t.start()
            h.threads.append(t)

            # Unauthenticated (with X-Platform but no X-Session) -> 401
            with self.assertRaises(HTTPError) as e401:
                urlopen(Request(
                    h.portal_url + '/agent2/api/v1/companies/C001/model-lifecycle/lr-fhe/status',
                    headers={'Origin': h.portal_url, 'X-Platform': '1'},
                ))
            self.assertEqual(e401.exception.code, 401)

            # Accountant -> 403
            with self.assertRaises(HTTPError) as e403:
                urlopen(Request(
                    h.portal_url + '/agent2/api/v1/companies/C001/model-lifecycle/lr-fhe/status',
                    headers={'Origin': h.portal_url, 'X-Platform': '1', 'X-Session': h.token},
                ))
            self.assertEqual(e403.exception.code, 403)

            # Director + model.fit -> 200 status & 400 on 33 features!
            pol = deepcopy(json.loads(h.access.read_text('utf-8')))
            for m in pol['memberships']:
                m['role'] = 'director'
                m['permissions'] = ['data.import', 'evidence.verify', 'model.fit']
            h.access.write_bytes(canonical(pol))

            with urlopen(Request(
                h.portal_url + '/agent2/api/v1/companies/C001/model-lifecycle/lr-fhe/status',
                headers={'Origin': h.portal_url, 'X-Platform': '1', 'X-Session': h.token},
            )) as r200:
                self.assertEqual(r200.code, 200)
                st_body = json.loads(r200.read())
                self.assertEqual(st_body['supported_feature_count'], 2)
                self.assertFalse(st_body['allow_33_features'])

            # HTTP 33-feature attempt -> 400 CIRCUIT_FEATURE_LIMIT_EXCEEDED
            bad_req = Request(
                h.portal_url + '/agent2/api/v1/companies/C001/model-lifecycle/lr-fhe/prepare',
                data=json.dumps({'selected_features': [f'col_{i}' for i in range(33)]}).encode('utf-8'),
                headers={
                    'Origin': h.portal_url, 'X-Platform': '1', 'X-Session': h.token,
                    'Content-Type': 'application/json',
                },
                method='POST',
            )
            with self.assertRaises(HTTPError) as e400:
                urlopen(bad_req)
            self.assertEqual(e400.exception.code, 400)
            err_payload = json.loads(e400.exception.read())
            self.assertEqual(err_payload['errors'][0]['code'], 'CIRCUIT_FEATURE_LIMIT_EXCEEDED')


if __name__ == '__main__':
    unittest.main()
