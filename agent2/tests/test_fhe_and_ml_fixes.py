"""Comprehensive mathematical, cryptographic & ML regression tests for Agent 2.

Covers:
  1. Fixed-point binary FHE SGD (`S=16, P=16`, `profile_version="fhe_sgd_s16_v2"`):
     - Legacy `S=2` dead-gradient reproduction vs `S=16` exact outputs (`[2, 2, -4]` and `[4, 4, 0]`).
     - Exhaustive 4,096 binary `(X, y)` combinations from `W=[0, 0, 0]` against scalar oracle,
       LUT bounds (`<= 129` entries, 7-bit TFHE PBS), zero dead non-zero gradients, and
       directional alignment with floating-point logistic SGD.
     - Multi-step & multi-batch trajectory convergence, negative correlation, clipping, and
       legacy `scale=2` profile mismatch protection.
  2. Portable FHE runtime discovery & Cross-Enterprise Encrypted Architecture:
     - Zero hardcoded `/home/sang/...` or `'Debian'` defaults; `AGENT2_HE_PYTHON`,
       `AGENT2_WSL_DISTRO`, and `AGENT2_HE_AGGREGATOR_URL` resolution.
     - Strict cryptographic separation between `EnterpriseKeyHolder` (`sk` at SME premise)
       and `HomomorphicAggregator` (`evk` only, rejects `sk` & plaintext).
     - `ConsortiumKeyCommittee` cross-enterprise encrypted SGD across `N=3` SMEs.
     - End-to-end Windows DPAPI + HTTP Worker + `BatchTrainingManager` honest
       `execution_mode = "fhe_quantized_circuit_verified"` reporting.
  3. Unsupervised ML & Statistical Fixes:
     - `RobustZ`, `FrozenECOD`, and `MLPRegressor` Autoencoder immunity to `missing:<col>`
       optional-field false-fraud spikes (`0.0` spike instead of `50.0` ceiling).
     - `FrozenECOD` `skew_ == 0` continuity and Li et al. (IEEE TKDE 2022, Eq. 7)
       `max(sum(left), sum(right), sum(auto))` tail aggregation.
     - `MLPRegressor` Autoencoder `shuffle=True` determinism & `top_contributing_features`
       per-feature squared reconstruction error attributions.
     - `empirical_rank == 1.0` monotonic excess tie-breaking (`rank(500M) > rank(10M)`)
       and `validation_study.transform_with_reference` integration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
import itertools
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import numpy as np

from finance_input import AccessScope
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he_training import (
    EXECUTION_MODE_VERIFIED,
    LEGACY_PROFILE_VERSION,
    PROFILE_VERSION,
    TARGET,
    resolve_quantization_profile,
)
from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.batch_store import BatchCloudStore
from experiments.he_training.build import build_verified_bundle
from experiments.he_training.circuit import (
    CLIP_B_TABLE,
    CLIP_W_TABLE,
    ROUND4_TABLE,
    SIGMOID_TABLE,
    float_logistic_sgd_step,
    inspect_intermediate_bounds,
    oracle,
    quantized_sigmoid_s16,
    reset_clear_mode,
    round_div4,
    samples,
    update,
)
from experiments.he_training.enterprise import Enterprise
from experiments.he_training.protocol import TrainingError, canonical, sha
from experiments.he_training.runtime import (
    ConsortiumKeyCommittee,
    ENV_HE_AGGREGATOR_URL,
    ENV_HE_PYTHON,
    ENV_WSL_DISTRO,
    EnterpriseKeyHolder,
    HomomorphicAggregator,
    resolve_he_runtime,
    validate_aggregator_endpoint,
)
from experiments.he_training.worker import NativeEvaluator, make_server as make_worker_server
from sme_fraud.batch_training_api import BatchTrainingManager
from sme_fraud.import_files import digest
from sme_fraud.label_packets import LabelStore, source_packet
from sme_fraud.method_preprocess import fit_preprocess, row_values, transform_frame
from sme_fraud.ml_estimators import CompanyEstimator, FrozenECOD
from sme_fraud.score_statistics import empirical_rank
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.unsupervised_statistics import RobustZ
from sme_fraud.validation_study import build_reference_distribution, transform_with_reference


def _logistic_loss(x_rows, y_rows, weights_float) -> float:
    w0, w1, b = weights_float
    losses = []
    for row, yi in zip(x_rows, y_rows):
        z = w0 * row[0] + w1 * row[1] + b
        p = 1.0 / (1.0 + math.exp(-z))
        p = min(1.0 - 1e-12, max(1e-12, p))
        losses.append(-(yi * math.log(p) + (1.0 - yi) * math.log(1.0 - p)))
    return sum(losses) / len(losses)


class FixedPointFHESGDTests(unittest.TestCase):
    def setUp(self):
        reset_clear_mode()

    def test_01_legacy_s2_dead_gradient_reproduction_vs_s16_mandatory_cases_a_and_b(self):
        case_a_x = [[1, 1], [0, 0], [0, 0], [0, 0]]
        case_a_y = [1, 0, 0, 0]
        case_b_x = [[1, 1], [1, 1], [0, 0], [0, 0]]
        case_b_y = [1, 1, 0, 0]

        # Legacy S=2, P=4 round-to-even stays stuck at [0, 0, 0] forever on both Case A and Case B
        w_leg_a = [0, 0, 0]
        w_leg_b = [0, 0, 0]
        for _ in range(8):
            w_leg_a = oracle(case_a_x, case_a_y, w_leg_a, profile_version=LEGACY_PROFILE_VERSION)
            w_leg_b = oracle(case_b_x, case_b_y, w_leg_b, profile_version=LEGACY_PROFILE_VERSION)
        self.assertEqual(w_leg_a, [0, 0, 0])
        self.assertEqual(w_leg_b, [0, 0, 0])

        # New default profile `fhe_sgd_s16_v2` (`S=16, P=16`) produces exact mandatory step-1 updates
        self.assertEqual(quantized_sigmoid_s16(0), 8)
        step1_a_vec = update(np.asarray(case_a_x, dtype=np.int64), np.asarray(case_a_y, dtype=np.int64), np.zeros(3, dtype=np.int64)).tolist()
        step1_a_orc = oracle(case_a_x, case_a_y, [0, 0, 0])
        self.assertEqual(step1_a_vec, [2, 2, -4])
        self.assertEqual(step1_a_orc, [2, 2, -4])

        step1_b_vec = update(np.asarray(case_b_x, dtype=np.int64), np.asarray(case_b_y, dtype=np.int64), np.zeros(3, dtype=np.int64)).tolist()
        step1_b_orc = oracle(case_b_x, case_b_y, [0, 0, 0])
        self.assertEqual(step1_b_vec, [4, 4, 0])
        self.assertEqual(step1_b_orc, [4, 4, 0])

    def test_02_exhaustive_4096_binary_xy_combinations_exact_oracle_and_zero_dead_gradients(self):
        t0 = time.perf_counter()
        w_zero_arr = np.zeros(3, dtype=np.int64)
        w_zero_list = [0, 0, 0]

        total_cases = 0
        nonzero_grad_w0 = 0
        nonzero_grad_w1 = 0
        nonzero_grad_b = 0
        legacy_dead_single_pos = 0

        for x_bits in itertools.product((0, 1), repeat=8):
            x_list = [
                [x_bits[0], x_bits[1]],
                [x_bits[2], x_bits[3]],
                [x_bits[4], x_bits[5]],
                [x_bits[6], x_bits[7]],
            ]
            x_arr = np.asarray(x_list, dtype=np.int64)
            for y_bits in itertools.product((0, 1), repeat=4):
                y_list = list(y_bits)
                y_arr = np.asarray(y_list, dtype=np.int64)
                total_cases += 1

                vec_out = update(x_arr, y_arr, w_zero_arr).tolist()
                orc_out = oracle(x_list, y_list, w_zero_list)
                self.assertEqual(vec_out, orc_out)

                diag = inspect_intermediate_bounds(x_list, y_list, w_zero_list)
                self.assertTrue(diag['lut_indices_valid'])
                self.assertEqual(diag['weights_out'], orc_out)

                # Zero dead-gradient proof: every non-zero true gradient at W=[0,0,0] produces a non-zero update!
                if diag['g_w'][0] != 0:
                    nonzero_grad_w0 += 1
                    self.assertNotEqual(orc_out[0], 0)
                else:
                    self.assertEqual(orc_out[0], 0)

                if diag['g_w'][1] != 0:
                    nonzero_grad_w1 += 1
                    self.assertNotEqual(orc_out[1], 0)
                else:
                    self.assertEqual(orc_out[1], 0)

                if diag['g_b'] != 0:
                    nonzero_grad_b += 1
                    self.assertNotEqual(orc_out[2], 0)
                else:
                    self.assertEqual(orc_out[2], 0)

                # Exact directional sign agreement with floating-point logistic SGD from [0, 0, 0]
                flt = float_logistic_sgd_step(x_list, y_list, [0.0, 0.0, 0.0], learning_rate=1.0)
                for idx in range(3):
                    s_int = (1 if orc_out[idx] > 0 else (-1 if orc_out[idx] < 0 else 0))
                    s_flt = (1 if flt[idx] > 1e-12 else (-1 if flt[idx] < -1e-12 else 0))
                    self.assertEqual(s_int, s_flt)
                    # At W=[0,0,0], W_s16 / 16.0 equals float step EXACTLY to machine precision!
                    self.assertAlmostEqual(orc_out[idx] / 16.0, flt[idx], places=12)

                if sum(y_list) == 1:
                    leg = oracle(x_list, y_list, w_zero_list, profile_version=LEGACY_PROFILE_VERSION)
                    if (diag['g_w'][0] != 0 and leg[0] == 0) or (diag['g_w'][1] != 0 and leg[1] == 0):
                        legacy_dead_single_pos += 1

        elapsed = time.perf_counter() - t0
        self.assertEqual(total_cases, 4096)
        self.assertGreater(nonzero_grad_w0, 2500)
        self.assertGreater(nonzero_grad_w1, 2500)
        self.assertGreater(nonzero_grad_b, 2500)
        self.assertGreater(legacy_dead_single_pos, 500)
        self.assertLess(elapsed, 15.0)

    def test_03_lut_pbs_bounds_negative_rounding_clipping_and_multistep_convergence(self):
        # Verify all 5 TFHE PBS tables fit in 7-bit domain (<= 129 entries)
        self.assertEqual(len(SIGMOID_TABLE), 129)
        self.assertEqual(len(ROUND4_TABLE), 129)
        self.assertEqual(len(CLIP_W_TABLE), 65)
        self.assertEqual(len(CLIP_B_TABLE), 97)

        # Half-away-from-zero symmetric rounding check (fixes banker's rounding dead zone at +-0.5)
        self.assertEqual(round_div4(2), 1)
        self.assertEqual(round_div4(-2), -1)
        self.assertEqual(round_div4(6), 2)
        self.assertEqual(round_div4(-6), -2)
        self.assertEqual(round_div4(1), 0)
        self.assertEqual(round_div4(-1), 0)

        # Exhaustively verify LUT bounds across representative samples + extreme corners
        for x_arr, y_arr, w_arr in samples(PROFILE_VERSION):
            diag = inspect_intermediate_bounds(x_arr, y_arr, w_arr)
            self.assertTrue(diag['lut_indices_valid'])
            self.assertEqual(update(x_arr, y_arr, w_arr).tolist(), diag['weights_out'])
            w0, w1, b = diag['weights_out']
            self.assertTrue(-16 <= w0 <= 16 and -16 <= w1 <= 16 and -32 <= b <= 32)

        # Multi-step convergence & class separation on Case A and Case B over 4 steps
        for x_case, y_case in (
            ([[1, 1], [0, 0], [0, 0], [0, 0]], [1, 0, 0, 0]),
            ([[1, 1], [1, 1], [0, 0], [0, 0]], [1, 1, 0, 0]),
        ):
            loss_init = _logistic_loss(x_case, y_case, [0.0, 0.0, 0.0])
            w_code = [0, 0, 0]
            for _ in range(4):
                w_code = oracle(x_case, y_case, w_code)
            w_flt = [w_code[0] / 16.0, w_code[1] / 16.0, w_code[2] / 16.0]
            loss_after = _logistic_loss(x_case, y_case, w_flt)
            self.assertLess(loss_after, loss_init)
            pos_score = 1.0 / (1.0 + math.exp(-(w_flt[0] + w_flt[1] + w_flt[2])))
            neg_score = 1.0 / (1.0 + math.exp(-w_flt[2]))
            self.assertGreater(pos_score, neg_score + 0.15)

        # Label inversion / negative correlation produces exact opposite weights
        inv_y = [0, 1, 1, 1]
        self.assertEqual(oracle([[1, 1], [0, 0], [0, 0], [0, 0]], inv_y, [0, 0, 0]), [-2, -2, 4])

        # Boundary clipping prevents overflow beyond [-16, 16] and [-32, 32]
        saturated_w = oracle([[1, 1]] * 4, [1, 1, 1, 1], [15, 15, -30])
        self.assertEqual(saturated_w[:2], [16, 16])
        saturated_b_pos = oracle([[1, 1]] * 4, [1, 1, 1, 1], [-16, -16, 30])
        self.assertEqual(saturated_b_pos[2], 32)
        saturated_b_neg = oracle([[1, 1]] * 4, [0, 0, 0, 0], [16, 16, -30])
        self.assertEqual(saturated_b_neg[2], -32)

    def test_04_legacy_profile_recognition_and_strict_mismatch_rejection(self):
        s16 = resolve_quantization_profile(PROFILE_VERSION)
        s2 = resolve_quantization_profile(LEGACY_PROFILE_VERSION)
        self.assertEqual(s16['weight_scale'], 16)
        self.assertEqual(s2['weight_scale'], 2)

        holder_s16 = EnterpriseKeyHolder(tenant_id='t1', company_id='C001', profile_version=PROFILE_VERSION)
        holder_s2 = EnterpriseKeyHolder(
            tenant_id='t1',
            company_id='C001',
            profile_version=LEGACY_PROFILE_VERSION,
            key_epoch=holder_s16.key_epoch,
        )
        enc_s2 = holder_s2.encrypt_labels([1, 0, 1, 0], initialize_weights=True, initial_weights=[2, -2, 4])
        opened_s2 = holder_s2.decrypt_weights(enc_s2['weights_cipher'])
        self.assertEqual(opened_s2['coefficients'], [1.0, -1.0])
        self.assertEqual(opened_s2['intercept'], 2.0)

        # Attempting to decrypt a legacy_s2_v1 ciphertext with an S=16 key holder is strictly blocked
        with self.assertRaisesRegex(TrainingError, 'LEGACY_MODEL_PROFILE_MISMATCH'):
            holder_s16.decrypt_weights(enc_s2['weights_cipher'])


class FHEArchitectureAndConsortiumTests(unittest.TestCase):
    def test_01_no_hardcoded_home_sang_or_debian_defaults_and_portable_env_discovery(self):
        for target in (Enterprise.__init__, CryptoBridge.__init__, BatchTrainingManager.__init__):
            sig_text = str(inspect.signature(target))
            self.assertNotIn('/home/sang', sig_text)
            self.assertNotIn('Debian', sig_text)

        with patch.dict(os.environ, {
            ENV_HE_PYTHON: '/opt/fhe/bin/python',
            ENV_WSL_DISTRO: 'Ubuntu-24.04',
            ENV_HE_AGGREGATOR_URL: 'https://fhe-consortium.example.vn:8443',
        }):
            rt = resolve_he_runtime()
            self.assertEqual(rt['he_python'], '/opt/fhe/bin/python')
            self.assertEqual(rt['wsl_distro'], 'Ubuntu-24.04')
            self.assertEqual(rt['aggregator_url'], 'https://fhe-consortium.example.vn:8443')
            ep = validate_aggregator_endpoint(None)
            self.assertEqual(ep['hostname'], 'fhe-consortium.example.vn')
            self.assertEqual(ep['port'], 8443)
            self.assertTrue(ep['is_remote'])

        # Unconfigured remote host rejected; loopback accepted
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_HE_AGGREGATOR_URL, None)
            self.assertTrue(validate_aggregator_endpoint('http://127.0.0.1:8899')['is_loopback'])
            with self.assertRaisesRegex(TrainingError, 'PROTOTYPE_LOOPBACK_OR_CONFIGURED_AGGREGATOR_ONLY'):
                validate_aggregator_endpoint('https://untrusted-other.example.com:8443')

    def test_02_client_key_holder_vs_untrusted_aggregator_boundary(self):
        holder = EnterpriseKeyHolder(tenant_id='tenant-vn', company_id='SME_01', profile_version=PROFILE_VERSION)
        self.assertTrue(holder.has_secret_key)

        evk_bundle = holder.export_evaluation_keys()
        self.assertFalse(evk_bundle['has_secret_key'])
        self.assertNotIn('secret_key', evk_bundle)
        self.assertNotIn('seed', evk_bundle)

        aggregator = HomomorphicAggregator(evk_bundle)
        self.assertFalse(aggregator.has_secret_key)

        # Aggregator strictly rejects secret keys or plaintext fields
        with self.assertRaisesRegex(TrainingError, 'SECRET_OR_PLAINTEXT_REJECTED_BY_AGGREGATOR'):
            HomomorphicAggregator(dict(evk_bundle, secret_key='leaked'))
        with self.assertRaisesRegex(TrainingError, 'SECRET_OR_PLAINTEXT_REJECTED_BY_AGGREGATOR'):
            aggregator.step({'x': [[1, 1]] * 4, 'x_cipher': 'aa', 'y_cipher': 'bb'}, 'cc')

        # Encrypted Case A execution matches [2, 2, -4] bit-identically
        case_a_x = [[1, 1], [0, 0], [0, 0], [0, 0]]
        case_a_y = [1, 0, 0, 0]
        pkt = holder.encrypt_minibatch(case_a_x, case_a_y, initialize_weights=True)
        step_res = aggregator.step(
            {'x_cipher': pkt['x_cipher'], 'x_cipher_sha256': pkt['x_cipher_sha256'],
             'y_cipher': pkt['y_cipher'], 'y_cipher_sha256': pkt['y_cipher_sha256']},
            pkt['weights_cipher'],
        )
        self.assertEqual(step_res['execution_mode'], EXECUTION_MODE_VERIFIED)
        self.assertFalse(step_res['native_fhe_executed'])
        opened = holder.decrypt_weights(step_res['weights_cipher'], expected_sha256=step_res['weights_cipher_sha256'])
        self.assertEqual(opened['weights_code'], [2, 2, -4])
        self.assertEqual(opened['coefficients'], [0.125, 0.125])
        self.assertEqual(opened['intercept'], -0.25)

    def test_03_cross_enterprise_consortium_encrypted_sgd_three_smes(self):
        committee = ConsortiumKeyCommittee(
            tenant_id='vn-accounting-consortium',
            company_ids=('SME_HANOI', 'SME_DANANG', 'SME_HCMC'),
        )
        aggregator = committee.create_untrusted_aggregator()

        sme_batches_clear = {
            'SME_HANOI': ([[1, 1], [0, 0], [0, 0], [0, 0]], [1, 0, 0, 0]),
            'SME_DANANG': ([[1, 1], [1, 1], [0, 0], [0, 0]], [1, 1, 0, 0]),
            'SME_HCMC': ([[1, 0], [0, 1], [1, 1], [0, 0]], [0, 0, 1, 0]),
        }

        encrypted_submissions = []
        for cid in ('SME_HANOI', 'SME_DANANG', 'SME_HCMC'):
            holder = committee.enterprise_holders[cid]
            # Individual SME holder CANNOT decrypt weights or another SME's ciphertexts!
            self.assertFalse(holder.has_secret_key)
            x_c, y_c = sme_batches_clear[cid]
            enc = holder.encrypt_minibatch(x_c, y_c, initialize_weights=False)
            encrypted_submissions.append(dict(
                company_id=cid,
                x_cipher=enc['x_cipher'],
                x_cipher_sha256=enc['x_cipher_sha256'],
                y_cipher=enc['y_cipher'],
                y_cipher_sha256=enc['y_cipher_sha256'],
            ))

        w0 = committee.encrypt_initial_zero_weights()
        with self.assertRaisesRegex(TrainingError, 'THRESHOLD_SHARES_INSUFFICIENT'):
            committee.enterprise_holders['SME_HANOI'].decrypt_weights(w0['weights_cipher'])

        # Missing 1 of 3 shares cannot open the consortium model
        with self.assertRaisesRegex(TrainingError, 'THRESHOLD_SHARES_INSUFFICIENT'):
            committee.threshold_decrypt_model(
                w0['weights_cipher'],
                contributed_shares={'SME_HANOI': committee.enterprise_shares['SME_HANOI'],
                                    'SME_DANANG': committee.enterprise_shares['SME_DANANG']},
            )

        # Untrusted aggregator chains 2 epochs * 3 SMEs = 6 encrypted SGD updates without decryption
        run_out = aggregator.run_consortium_epoch(encrypted_submissions, w0['weights_cipher'], epochs=2)
        self.assertEqual(run_out['enterprise_count'], 3)
        self.assertEqual(run_out['completed_updates'], 6)
        self.assertFalse(run_out['aggregator_saw_plaintext'])
        self.assertFalse(run_out['aggregator_has_secret_key'])

        opened = committee.threshold_decrypt_model(
            run_out['model_cipher'],
            contributed_shares=committee.enterprise_shares,
            expected_sha256=run_out['model_cipher_sha256'],
        )
        expected_w = [0, 0, 0]
        for _ in range(2):
            for cid in ('SME_HANOI', 'SME_DANANG', 'SME_HCMC'):
                expected_w = oracle(*sme_batches_clear[cid], expected_w)
        self.assertEqual(opened['weights_code'], expected_w)
        self.assertGreater(opened['coefficients'][0] + opened['coefficients'][1], 0.5)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI end-to-end test')
    def test_04_end_to_end_windows_dpapi_enterprise_worker_and_portal_honest_execution_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_dir = root / 'build_s16'
            manifest = build_verified_bundle(build_dir)
            self.assertEqual(manifest['profile_version'], PROFILE_VERSION)
            self.assertEqual(manifest['execution_mode'], EXECUTION_MODE_VERIFIED)
            self.assertFalse(manifest['native_fhe_compiled'])

            scope = AccessScope('tenant-demo', frozenset({'C001'}), 'auditor-1', frozenset({'data.import', 'evidence.verify', 'model.fit'}))
            ent_dir = root / 'enterprise' / 'C001'
            # Provision real BatchEnterprise on pure Windows without WSL!
            node = BatchEnterprise(ent_dir, build_dir, scope)
            evk_path = ent_dir / 'crypto' / 'evaluation.keys'
            self.assertTrue(evk_path.is_file())

            worker_key = Ed25519PrivateKey.generate()
            worker_pub = worker_key.public_key().public_bytes_raw().hex()
            grants = {
                ('tenant-demo', 'C001'): dict(
                    active=True,
                    batch_training=True,
                    node_verify_key=node.public_key,
                    key_epoch=node.meta['key_epoch'],
                    target=TARGET,
                    verification_mode='synthetic_expected',
                    evaluation_keys_file=str(evk_path),
                    evaluation_keys_sha256=sha(evk_path.read_bytes()),
                )
            }
            evaluator = NativeEvaluator(build_dir, grants)
            self.assertEqual(evaluator.execution_mode, EXECUTION_MODE_VERIFIED)
            bstore = BatchCloudStore(root / 'cloud_batch', grants, worker_key, manifest['files']['server.zip'], evaluator)
            server = make_worker_server(0, None, bstore)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            try:
                worker_url = f'http://127.0.0.1:{server.server_port}'
                train_batches = [
                    dict(x=[[1, 1], [0, 0], [0, 0], [0, 0]], row_ids=['T0', 'T1', 'T2', 'T3']),
                    dict(x=[[1, 1], [1, 1], [0, 0], [0, 0]], row_ids=['T4', 'T5', 'T6', 'T7']),
                ]
                eval_batches = [
                    dict(x=[[0, 0], [1, 0], [0, 1], [1, 1]], row_ids=['E0', 'E1', 'E2', 'E3']),
                ]
                node.prepare_batches(train_batches, eval_batches, simulated=True)
                node.upload_batches(worker_url, worker_pub)
                reviews = node.batch_review_templates()
                now_iso = datetime.now(timezone.utc).isoformat()
                outcomes = [['verified_fraud', 'verified_non_fraud', 'verified_non_fraud', 'verified_non_fraud'],
                            ['verified_fraud', 'verified_fraud', 'verified_non_fraud', 'verified_non_fraud']]
                for b_idx, rev in enumerate(reviews):
                    for r_idx, row in enumerate(rev['rows']):
                        row.update(outcome=outcomes[b_idx][r_idx], verified_at=now_iso, evidence_refs=['EV_1'])
                node.confirm_batch_reviews(worker_url, worker_pub, reviews, epochs=1)
                done, _ = node.access_batches(worker_url, worker_pub, 'run')
                self.assertEqual(done['completed_updates'], 2)
                cand = node.receive_batches(worker_url, worker_pub)
                expected_after_2 = oracle(
                    train_batches[1]['x'],
                    [1, 1, 0, 0],
                    oracle(train_batches[0]['x'], [1, 0, 0, 0], [0, 0, 0]),
                )
                self.assertEqual(cand['weights_code'], expected_after_2)
                self.assertEqual(cand['profile_version'], PROFILE_VERSION)
                self.assertEqual(cand['execution_mode'], EXECUTION_MODE_VERIFIED)
                self.assertFalse(cand['native_fhe_executed'])

                # Verify BatchTrainingManager status reports honest execution_mode
                mgr = BatchTrainingManager(
                    root / 'bt.sqlite3',
                    secrets.token_bytes(32),
                    snapshot_store=SnapshotStore(root / 'snap.sqlite3'),
                    label_store=LabelStore(root / 'lbl.sqlite3', secrets.token_bytes(32)),
                    enterprise_root=root / 'enterprise',
                    build=build_dir,
                    worker_url=worker_url,
                    worker_verify_key=worker_pub,
                )
                status = mgr.status(scope)
                self.assertEqual(status['profile_version'], PROFILE_VERSION)
                self.assertEqual(status['execution_mode'], EXECUTION_MODE_VERIFIED)
                self.assertFalse(status['fhe_runtime']['native_fhe_available'])
            finally:
                server.shutdown()
                server.server_close()
                t.join(timeout=3)
                bstore.close()


class UnsupervisedMLAndStatisticsFixesTests(unittest.TestCase):
    def _build_58col_median_flags_frame(self):
        rng = np.random.default_rng(20261118)
        cols = [f'feat_{i:02d}' for i in range(29)]
        contract = dict(version='test-29-features/1.0.0', columns=cols, dtype='float64')
        contract['fingerprint'] = digest(canonical(contract))

        # 32 clean training rows where optional fields feat_20..feat_28 are always present (no missingness in train)
        train_feats = []
        train_missing = []
        origin = datetime(2026, 9, 1, tzinfo=timezone.utc)
        train_rows = []
        for i in range(32):
            vals = [float(rng.normal(10.0 + j * 0.5, 1.0)) for j in range(29)]
            train_feats.append(vals)
            train_missing.append([False] * 29)
            ts = (origin + timedelta(hours=i)).isoformat()
            train_rows.append(dict(row_index=i, tenant_id='demo', company_id='C001', record_id=f'TR_{i}', revision=1, event_at=ts, as_of=ts))
        train_frame = dict(
            as_of=train_rows[-1]['as_of'],
            contract=contract,
            features=train_feats,
            missing=train_missing,
            rows=train_rows,
            evidence=[dict(row_index=i, records=[], missing_reasons={}) for i in range(32)],
        )
        prep = fit_preprocess(train_frame, cols, 'median_flags')
        self.assertEqual(len(prep['output_columns']), 58)

        # Build test rows:
        # Row 0: Completely normal row with 0 missing fields
        # Row 1: Normal row missing 5 optional fields (feat_24..feat_28 = None) -> previously spiked RobustZ to 50.0!
        # Row 2: Genuine fraud magnitude outlier (+18 sigma on feat_00 and feat_01), 0 missing fields
        base_meds = [prep['medians'][c] for c in cols]
        r0_raw = list(base_meds)
        r1_raw = list(base_meds)
        for m_idx in range(24, 29):
            r1_raw[m_idx] = None
        r2_raw = list(base_meds)
        r2_raw[0] += 18.0
        r2_raw[1] += 18.0

        prepared_test = []
        for raw_row in (r0_raw, r1_raw, r2_raw):
            p_row, _, reason = row_values(train_frame, raw_row, prep)
            self.assertIsNone(reason)
            prepared_test.append(p_row)
        return transform_frame(train_frame, prep), np.asarray(prepared_test, dtype=float), prep['output_columns']

    def test_01_robust_z_ecod_and_autoencoder_do_not_spike_on_missing_optional_fields(self):
        x_train, x_test, out_cols = self._build_58col_median_flags_frame()

        # 1. RobustZ: normal row missing 5 optional fields must NOT jump to 50.0 ceiling!
        rz = RobustZ().fit(x_train)
        rz_scores = rz.score(x_test)
        self.assertAlmostEqual(rz_scores[0], 0.0, places=9)
        self.assertAlmostEqual(rz_scores[1], 0.0, places=9)
        self.assertLess(rz_scores[1], 1.0)
        self.assertGreater(rz_scores[2], 15.0)

        # 2. FrozenECOD: normal row missing 5 optional fields scores identically to complete median row, far below fraud!
        ecod = CompanyEstimator('ecod').fit(x_train)
        ecod_scores = ecod.score(x_test)
        self.assertAlmostEqual(ecod_scores[0], ecod_scores[1], places=9)
        self.assertGreater(ecod_scores[2], ecod_scores[1] + 4.0)

        # 3. Autoencoder: normal row missing 5 optional fields has masked MSE, far below genuine fraud!
        ae = CompanyEstimator('autoencoder').fit(x_train)
        ae_scores = ae.score(x_test)
        self.assertLess(ae_scores[1], 1.0)
        self.assertGreater(ae_scores[2], ae_scores[1] * 5.0)

        # Also check explicit feature_names API
        rz_named = RobustZ(feature_names=out_cols).fit(x_train)
        np.testing.assert_allclose(rz_named.score(x_test), rz_scores, atol=1e-12)

    def test_02_frozen_ecod_skew_zero_no_double_penalty_and_li2022_eq7_sum_before_max(self):
        # Symmetric 1D feature (`skew_ == 0`) vs slightly right-skewed (`skew_ > 0`)
        sym = np.array([[-2.0], [-1.0], [0.0], [1.0], [2.0]])
        slight_pos = np.array([[-2.0], [-1.0], [0.0], [1.0], [2.0001]])
        m_sym = FrozenECOD().fit(sym)
        m_pos = FrozenECOD().fit(slight_pos)
        self.assertEqual(m_sym.skew_[0], 0.0)
        self.assertEqual(m_pos.skew_[0], 1.0)

        # At median x = [[0.0]], symmetric score MUST equal -log(3/5), NOT 2 * -log(3/5)!
        s_sym_med = m_sym.score([[0.0]])[0]
        s_pos_med = m_pos.score([[0.0]])[0]
        self.assertAlmostEqual(s_sym_med, -math.log(3.0 / 5.0), places=10)
        self.assertAlmostEqual(s_sym_med, s_pos_med, places=6)

        # Li et al. (IEEE TKDE 2022, Eq. 7) sum-before-max proof:
        # Construct 2 positively skewed features (`skew_ = [+1, +1]`), query at x = [-10.0, +10.0]
        # (extreme left on col 0, extreme right on col 1).
        # Under old buggy elementwise max(left, right).sum(), score would be 2 * log(N + 1).
        # Under exact Eq. 7:
        #   u_left  = [log(N+1), 0]       -> O_left  = log(N+1)
        #   u_right = [0, log(N+1)]       -> O_right = log(N+1)
        #   u_auto  = [0, log(N+1)] (+sk) -> O_auto  = log(N+1)
        #   max(O_left, O_right, O_auto) == log(N + 1), while if skew_ were [-1, +1], u_auto = [log(N+1), log(N+1)] -> 2 * log(N+1)!
        pos_skew_base = np.array([
            [0.0, 0.0],
            [0.1, 0.1],
            [0.2, 0.2],
            [0.3, 0.3],
            [0.5, 0.5],
            [2.0, 2.0],
        ])
        opposite_skew_base = np.array([
            [-2.0, 0.0],
            [-0.5, 0.1],
            [-0.3, 0.2],
            [-0.2, 0.3],
            [-0.1, 0.5],
            [0.0, 2.0],
        ])
        ecod_same_skew = FrozenECOD().fit(pos_skew_base)
        ecod_opp_skew = FrozenECOD().fit(opposite_skew_base)
        self.assertEqual(ecod_same_skew.skew_.tolist(), [1.0, 1.0])
        self.assertEqual(ecod_opp_skew.skew_.tolist(), [-1.0, 1.0])

        q = np.array([[-10.0, 10.0]])
        n = len(pos_skew_base)
        # Skewness now genuinely matters (not masked by elementwise max)!
        self.assertAlmostEqual(ecod_same_skew.score(q)[0], math.log(n + 1), places=10)
        self.assertAlmostEqual(ecod_opp_skew.score(q)[0], 2.0 * math.log(n + 1), places=10)

    def test_03_autoencoder_shuffle_enabled_deterministic_and_feature_attributions(self):
        rng = np.random.default_rng(77)
        # Chronologically drifted normal invoices (Q1 lower regime, Q2 higher regime)
        q1 = rng.normal(-1.5, 0.2, size=(40, 6))
        q2 = rng.normal(+1.5, 0.2, size=(40, 6))
        x_chrono = np.vstack([q1, q2])
        feat_names = ['log_amount', 'round_million', 'hour_sin', 'hour_cos', 'line_count', 'vendor_age_days']

        ae1 = CompanyEstimator('autoencoder', feature_names=feat_names, random_state=42).fit(x_chrono)
        ae2 = CompanyEstimator('autoencoder', feature_names=feat_names, random_state=42).fit(x_chrono)
        self.assertTrue(ae1.model_.shuffle)
        np.testing.assert_allclose(ae1.score(x_chrono[:5]), ae2.score(x_chrono[:5]), atol=1e-12)

        # Anomaly concentrated solely on `log_amount` (column 0)
        anomaly = np.array([[15.0, 0.0, 0.0, 0.0, 0.0, 0.0]])
        explained = ae1.score_with_attributions(anomaly, top_k=3)
        np.testing.assert_allclose(explained['scores'], ae1.score(anomaly), atol=1e-12)
        top_feats = explained['top_contributing_features'][0]
        self.assertEqual(len(top_feats), 3)
        self.assertEqual(top_feats[0]['feature'], 'log_amount')
        self.assertEqual(top_feats[0]['column_index'], 0)
        self.assertGreater(top_feats[0]['share_of_total_error'], 0.70)

    def test_04_empirical_rank_tie_breaking_above_training_max_and_validation_study(self):
        ref_vals = [1.0, 2.0, 2.0, 4.0]
        # Single out-of-sample outlier preserves exact 1.0 compatibility
        np.testing.assert_array_equal(
            empirical_rank(ref_vals, [0.0, 1.0, 2.0, 3.0, 5.0]),
            [0.0, 0.125, 0.5, 0.75, 1.0],
        )

        # Multiple out-of-sample outliers: 10M outlier (score=10.0) vs 500M fraud (score=500.0)
        ranks = empirical_rank([1.0, 1.5, 2.0, 2.5, 3.0, 3.2, 3.5, 4.0], [2.0, 4.0, 10.0, 500.0], break_ties_above_max=True)
        r_mid, r_max_in, r_10m, r_500m = ranks
        self.assertLess(r_mid, r_max_in)
        self.assertLess(r_max_in, r_10m)
        self.assertLess(r_10m, r_500m)
        self.assertLess(r_500m, 1.0)
        self.assertGreaterEqual(r_10m, 0.0)

        # Verify validation_study.transform_with_reference preserves strict ordering between 500M fraud and 10M outlier
        ref_doc = build_reference_distribution(
            'robust_z',
            [1.0, 1.5, 2.0, 2.5, 3.0, 3.2, 3.5, 4.0],
            company_id='C001',
            tenant_id='demo',
            snapshot_id='snp_' + 'a' * 32,
            as_of='2026-09-30T00:00:00Z',
        )
        binding = {
            'reference_id': ref_doc['reference_id'],
            'reference_sha256': ref_doc['reference_sha256'],
            'method_id': 'robust_z',
        }
        mapped = transform_with_reference(
            ref_doc,
            {('TX_10M_EARLY', 1): 10.0, ('TX_500M_FRAUD_LATER', 1): 500.0, ('TX_NORMAL', 1): 2.0},
            expected_binding=binding,
            expected_company='C001',
        )
        self.assertGreater(mapped[('TX_500M_FRAUD_LATER', 1)], mapped[('TX_10M_EARLY', 1)])
        self.assertGreater(mapped[('TX_10M_EARLY', 1)], mapped[('TX_NORMAL', 1)])


if __name__ == '__main__':
    unittest.main()
