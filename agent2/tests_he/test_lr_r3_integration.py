"""R3 Integration & Verification Tests — Supervised Logistic Regression as Agent2's 5th Detection Method.

Covers all 4 R3 workstreams:
  1. Approved LR inference adapter (Ed25519 signature, contract, company scope, 2-feature schema,
     unapproved checkpoint rejection, missing-feature unavailable status without converting to 0,
     local preferred inference + TenSEAL CKKS encrypted evaluation + honest worker 8868 check).
  2. Unified 5-method bundle integration (Rules, Statistics, Graph, Unsupervised ML, Supervised LR)
     preserving all 4 existing methods and never turning `unavailable` into score `0`.
  3. Configurable risk scoring: anti-flat-+10 validation precision dampening, anti-double-counting
     overlap discount (round_million <-> A6, creator_equals_approver <-> C2), validation calibration.
  4. Area A Investigation read-back + verified reviewer label loop (`confirmed_risk` -> 1,
     `legitimate` -> 0 ONLY; strictly excluding `inconclusive` and unreviewed transactions).
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path[:0] = [
    str(ROOT),
    str(ROOT / 'tests'),
    str(ROOT / 'tests_he'),
    str(REPO),
    str(REPO / 'shared' / 'finance_input' / 'src'),
]

import test_release_shadow_plan as support
from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.import_files import canonical
from sme_fraud.investigation import Investigation
from sme_fraud.lr_fhe_training import LRFHETrainingService
from sme_fraud.lr_inference import (
    LR_FEATURE_SCHEMA,
    LR_RELEASE_CONTRACT,
    RiskScoringConfig,
    SupervisedLRAdapter,
    _canonical_signed_payload,
    apply_overlap_deduplication,
    calibrate_risk_scoring_on_validation,
    convert_lr_probability_to_points,
    sign_releasable_lr_model,
    verify_releasable_lr_model,
)
from sme_fraud.model_lifecycle import ModelLifecycle
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore


class LRR3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        support.ShadowPlanTests.setUpClass()
        cls.fixture = support.ShadowPlanTests.fixture
        cls.tmp_base = REPO / '.runtime' / 'tmp_r3_tests' / uuid.uuid4().hex[:10]
        cls.tmp_base.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp_base, ignore_errors=True)
        support.ShadowPlanTests.tearDownClass()

    def _make_isolated_env(self, name: str):
        env_dir = self.tmp_base / f'{name}_{uuid.uuid4().hex[:6]}'
        env_dir.mkdir(parents=True, exist_ok=True)
        f = self.fixture
        c1_art = f.company_ctx['C001']['model_artifacts']['isolation_forest']['artifact_id']
        c2_art = f.company_ctx['C002']['model_artifacts']['ecod']['artifact_id']
        bindings_path = env_dir / 'bindings.json'
        bindings_path.write_bytes(canonical({
            'version': BINDINGS_VERSION,
            'bindings': [
                {'tenant_id': 'demo', 'company_id': 'C001', 'statistics_artifact_id': None, 'ml_artifacts': {'isolation_forest': c1_art}},
                {'tenant_id': 'demo', 'company_id': 'C002', 'statistics_artifact_id': None, 'ml_artifacts': {'ecod': c2_art}},
            ],
        }))
        res = AnalysisResources(f.models.path, bindings_path)
        rel_store = ReleaseStore(env_dir / 'releases.db', b'k' * 32)
        rel_svc = ReleaseService(rel_store, f.snapshots, res, CaseQueueStore(env_dir / 'cases.db'))

        # Register & activate staging bundle for C001 so ReleaseStore has a current pointer
        scope_c1 = f.company_ctx['C001']['scope']
        eval_sid = f.company_ctx['C001']['manifests']['sealed_future_test']['snapshot_id']
        reg = rel_svc.register_plan(scope_c1, support.ShadowPlanTests.packages['C001'], 'reg-r3-' + name)
        b = rel_svc.prepare(scope_c1, eval_sid, 'R3 Base ' + name, 'prep-r3-' + name, plan_id=reg['plan_id'])
        g = rel_svc.qualify(scope_c1, b['bundle_id'], 'staging')
        self.assertTrue(g['technical_ready'])
        a = rel_svc.approve(scope_c1, b['bundle_id'], g['gate_id'], 'staging', 'R3 integration acceptance')
        rel_svc.switch(
            scope_c1,
            dict(bundle_id=b['bundle_id'], gate_id=g['gate_id'], approval_id=a['approval_id'],
                 lane='staging', expected_revision=0, reason='Activate staging for R3', action='activate'),
            'act-r3-' + name,
        )

        ml_svc = ModelLifecycle(
            env_dir / 'lifecycle.db',
            snapshot_store=f.snapshots,
            analysis_resources=res,
            authorizer=None,
            release_service=rel_svc,
        )
        lr_svc = LRFHETrainingService(
            env_dir / 'lr_fhe.db',
            snapshot_store=f.snapshots,
            model_lifecycle=ml_svc,
        )
        ml_svc.lr_fhe = lr_svc
        ws = rel_svc.workspace
        inv = Investigation(ws)
        return env_dir, ml_svc, lr_svc, rel_svc, ws, inv, scope_c1, eval_sid

    def _train_and_promote_lr(self, lr_svc: LRFHETrainingService, scope):
        res = lr_svc.start_training(
            scope,
            {
                'mode': 'local_quantized_reference',
                'source_mode': 'verified_test_dataset',
                'batch_count': 2,
                'epochs': 1,
                'selected_features': ['round_million', 'creator_equals_approver'],
            },
            'r3-train-' + uuid.uuid4().hex[:12],
        )
        job_id = res['job']['job_id']
        prom = lr_svc.promote_to_releasable_model(
            scope,
            {
                'job_id': job_id,
                'reason': 'Đã kiểm tra sai số triển khai = 0.0 và ngưỡng phân loại từ validation cho R3.',
                'reviewed_checked': True,
            },
            'r3-prom-' + uuid.uuid4().hex[:12],
        )
        return res['job'], prom['releasable_model']

    def test_01_adapter_signature_schema_unapproved_and_missing_unavailable(self):
        _, _, lr_svc, _, _, _, scope_c1, _ = self._make_isolated_env('adapter')
        scope_c2 = self.fixture.company_ctx['C002']['scope']
        _, model = self._train_and_promote_lr(lr_svc, scope_c1)

        # Signed releasable model metadata checks
        self.assertEqual(model['artifact_stage'], 'releasable_model')
        self.assertEqual(model['release_contract_version'], LR_RELEASE_CONTRACT)
        self.assertEqual(model['feature_schema']['columns'], ['round_million', 'creator_equals_approver'])
        self.assertIn('signature_envelope', model)
        self.assertEqual(model['signature_envelope']['algorithm'].lower(), 'ed25519')
        self.assertGreaterEqual(model['threshold'], 0.30)
        self.assertLessEqual(model['threshold'], 0.85)

        adapter = SupervisedLRAdapter(lr_training_service=lr_svc)
        loaded = adapter.load_approved_model(scope_c1)
        self.assertTrue(loaded['available'], loaded)

        # 1. Tampered coefficient rejected by Ed25519 signature check
        tampered = deepcopy(model)
        tampered['coefficients'][0] = 9.99
        ok, code, _ = verify_releasable_lr_model(tampered, expected_tenant='demo', expected_company='C001')
        self.assertFalse(ok)
        self.assertEqual(code, 'LR_SIGNATURE_INVALID')

        # 2. Unapproved train checkpoint rejected
        unapproved = deepcopy(model)
        unapproved['artifact_stage'] = 'validated_checkpoint'
        ok, code, _ = verify_releasable_lr_model(unapproved, expected_tenant='demo', expected_company='C001')
        self.assertFalse(ok)
        self.assertEqual(code, 'LR_MODEL_NOT_APPROVED')

        # 3. Feature schema mismatch rejected (even with a valid Ed25519 signature over the mismatched schema!)
        bad_schema = deepcopy(model)
        bad_schema['feature_schema']['columns'] = ['round_million', 'amount_vnd']
        skey = lr_svc._load_or_create_signing_key('C001')
        raw_bad = _canonical_signed_payload(bad_schema)
        from sme_fraud.import_files import digest
        bad_schema['signature_envelope']['payload_sha256'] = digest(raw_bad)
        bad_schema['signature_envelope']['signature_hex'] = skey.sign(raw_bad).hex()
        bad_schema['signature_envelope']['verify_key_hex'] = skey.public_key().public_bytes_raw().hex()
        ok, code, _ = verify_releasable_lr_model(bad_schema, expected_tenant='demo', expected_company='C001')
        self.assertFalse(ok)
        self.assertEqual(code, 'LR_FEATURE_SCHEMA_MISMATCH')

        # 4. Cross-company scope rejected
        bad_co = adapter.load_approved_model(scope_c2, explicit_model=model)
        self.assertFalse(bad_co['available'])
        self.assertEqual(bad_co['error_code'], 'LR_COMPANY_SCOPE_MISMATCH')

        # 5. Missing-feature row -> status='unavailable', score=None (NEVER 0!)
        frame = {
            'contract': {'columns': ['round_million', 'creator_equals_approver']},
            'rows': [
                {'record_id': 'TX_VALID_POS'},
                {'record_id': 'TX_VALID_NEG'},
                {'record_id': 'TX_MISSING'},
            ],
            'features': [
                [1, 1],
                [0, 0],
                [None, 1],
            ],
            'missing': [
                [False, False],
                [False, False],
                [True, False],
            ],
        }
        rows = [
            {'transaction_id': 'TX_VALID_POS', 'rule_coverage': {'rules': []}},
            {'transaction_id': 'TX_VALID_NEG', 'rule_coverage': {'rules': []}},
            {'transaction_id': 'TX_MISSING', 'rule_coverage': {'rules': []}},
        ]
        scored = adapter.score_transaction_rows(scope_c1, frame, rows)
        self.assertTrue(scored['available'])
        self.assertEqual(scored['execution_backend'], 'local_approved_model')

        pos = scored['per_transaction']['TX_VALID_POS']
        neg = scored['per_transaction']['TX_VALID_NEG']
        miss = scored['per_transaction']['TX_MISSING']

        self.assertEqual(pos['status'], 'available')
        self.assertGreater(pos['probability'], neg['probability'])
        self.assertEqual(pos['prediction'], 1)
        self.assertGreater(pos['score'], 0.0)

        self.assertEqual(neg['status'], 'available')
        self.assertEqual(neg['prediction'], 0)
        self.assertLess(neg['score'], pos['score'])

        self.assertEqual(miss['status'], 'unavailable')
        self.assertIsNone(miss['score'])
        self.assertIsNone(miss['probability'])
        self.assertIsNone(miss['prediction'])
        self.assertEqual(miss['error_code'], 'LR_FEATURE_MISSING_OR_OUT_OF_DOMAIN')

    def test_02_ckks_encrypted_evaluation_and_worker_8868_honesty(self):
        _, _, lr_svc, _, _, _, scope_c1, _ = self._make_isolated_env('ckks')
        self._train_and_promote_lr(lr_svc, scope_c1)
        adapter = SupervisedLRAdapter(lr_training_service=lr_svc)

        frame = {
            'contract': {'columns': ['round_million', 'creator_equals_approver']},
            'rows': [
                {'record_id': 'CK_00'},
                {'record_id': 'CK_01'},
                {'record_id': 'CK_10'},
                {'record_id': 'CK_11'},
            ],
            'features': [[0, 0], [0, 1], [1, 0], [1, 1]],
            'missing': [[False, False]] * 4,
        }
        rows = [{'transaction_id': r['record_id'], 'rule_coverage': {'rules': []}} for r in frame['rows']]

        local_res = adapter.score_transaction_rows(scope_c1, frame, rows, execution_preference='local_preferred')
        ckks_res = adapter.score_transaction_rows(scope_c1, frame, rows, execution_preference='ckks_encrypted')
        self.assertTrue(ckks_res['available'], ckks_res)
        self.assertEqual(ckks_res['execution_backend'], 'ckks_tenseal_2col_quadratic_equivalent')
        self.assertIsNotNone(ckks_res['ckks_meta'])
        self.assertLess(ckks_res['ckks_meta']['max_abs_ckks_error'], 1e-3)

        for r in rows:
            tid = r['transaction_id']
            p_loc = local_res['per_transaction'][tid]['probability']
            p_ck = ckks_res['per_transaction'][tid]['probability']
            self.assertAlmostEqual(p_loc, p_ck, places=4)
            self.assertEqual(local_res['per_transaction'][tid]['prediction'], ckks_res['per_transaction'][tid]['prediction'])
            self.assertTrue(ckks_res['per_transaction'][tid]['confidence_metadata']['ckks_encrypted'])

        # Strict cloud_ckks_8868_strict MUST fail honestly without plaintext fallback
        strict_res = adapter.score_transaction_rows(scope_c1, frame, rows, execution_preference='cloud_ckks_8868_strict')
        self.assertFalse(strict_res['available'])
        self.assertEqual(strict_res['error_code'], 'CKKS_WORKER_8868_LR_POLICY_NOT_REGISTERED')
        for r in rows:
            dto = strict_res['per_transaction'][r['transaction_id']]
            self.assertEqual(dto['status'], 'unavailable')
            self.assertIsNone(dto['score'])

    def test_03_risk_scoring_anti_flat_10_dedup_and_calibration(self):
        cfg = RiskScoringConfig(lr_max_points=8.0, overlap_discount_factor=0.70, validation_precision_scaling=True)

        # High recall (95%) but mediocre precision (50%) -> MUST NOT give flat +10 to every transaction!
        val_high_recall_low_prec = {'precision': 0.50, 'recall': 0.95, 'f1': 0.655, 'sample_count': 20}
        val_high_prec = {'precision': 0.92, 'recall': 0.90, 'f1': 0.91, 'sample_count': 20}

        c_low = convert_lr_probability_to_points(0.25, 0.50, validation_metrics=val_high_recall_low_prec, config=cfg)
        c_mid = convert_lr_probability_to_points(0.60, 0.50, validation_metrics=val_high_recall_low_prec, config=cfg)
        c_hi = convert_lr_probability_to_points(0.88, 0.50, validation_metrics=val_high_recall_low_prec, config=cfg)
        c_hi_good_prec = convert_lr_probability_to_points(0.88, 0.50, validation_metrics=val_high_prec, config=cfg)

        self.assertEqual(c_low['prediction'], 0)
        self.assertEqual(c_low['raw_converted_points'], 0.0)
        self.assertEqual(c_mid['prediction'], 1)
        self.assertEqual(c_hi['prediction'], 1)
        # Strictly distinct and strictly below 10.0!
        self.assertGreater(c_mid['raw_converted_points'], 0.0)
        self.assertGreater(c_hi['raw_converted_points'], c_mid['raw_converted_points'])
        self.assertLess(c_hi['raw_converted_points'], 10.0)
        # Low-precision high-recall model is dampened compared to high-precision model
        self.assertLess(c_hi['raw_converted_points'], c_hi_good_prec['raw_converted_points'])

        # Anti-double-counting overlap discount: round_million <-> A6, creator_equals_approver <-> C2
        feats = {'round_million': 1, 'creator_equals_approver': 1}
        coeffs = [0.5, 0.5]
        raw_pts = 5.0
        d_none = apply_overlap_deduplication(raw_pts, feats, coeffs, set(), cfg)
        d_c2 = apply_overlap_deduplication(raw_pts, feats, coeffs, {'C2'}, cfg)
        d_both = apply_overlap_deduplication(raw_pts, feats, coeffs, {'A6', 'C2'}, cfg)

        self.assertFalse(d_none['overlap_applied'])
        self.assertEqual(d_none['effective_lr_points'], raw_pts)

        self.assertTrue(d_c2['overlap_applied'])
        self.assertEqual(d_c2['overlapping_rules'], ['C2'])
        self.assertLess(d_c2['effective_lr_points'], raw_pts)

        self.assertTrue(d_both['overlap_applied'])
        self.assertEqual(d_both['overlapping_rules'], ['A6', 'C2'])
        self.assertLess(d_both['effective_lr_points'], d_c2['effective_lr_points'])

        # Validation calibration tunes supervised_lr_weight & overlap_discount_factor
        val_records = [
            {'y_true': 1, 'rule_score': 10.0, 'ml_score': 0.85, 'lr_raw_points': 4.5, 'lr_overlap_share': 0.5},
            {'y_true': 1, 'rule_score': 0.0, 'ml_score': 0.65, 'lr_raw_points': 5.0, 'lr_overlap_share': 0.0},
            {'y_true': 0, 'rule_score': 0.0, 'ml_score': 0.20, 'lr_raw_points': 0.0, 'lr_overlap_share': 0.0},
            {'y_true': 0, 'rule_score': 5.0, 'ml_score': 0.30, 'lr_raw_points': 0.0, 'lr_overlap_share': 0.5},
        ]
        cal_cfg, cal_report = calibrate_risk_scoring_on_validation(val_records)
        self.assertTrue(cal_report['calibrated'])
        self.assertEqual(cal_cfg.calibration_source, 'validation_ranking_calibrated')
        self.assertGreaterEqual(cal_report['validation_auc'], 0.99)

    def test_04_five_method_bundle_integration_and_investigation_readback(self):
        _, ml_svc, lr_svc, _, _, inv, scope_c1, eval_sid = self._make_isolated_env('five_method')
        # Ensure active unsupervised model C001-v1 exists
        ov = ml_svc.overview(scope_c1)
        self.assertIsNotNone(ov['active_version'])

        # Run A: BEFORE any LR model is promoted -> existing 4 methods MUST work untouched & LR is unavailable (score=None, NEVER 0)
        run_before = ml_svc.score_to_queue(
            scope_c1,
            {'snapshot_id': eval_sid, 'version_id': ov['active_version']['version_id']},
            'r3-score-before-' + uuid.uuid4().hex[:10],
        )
        self.assertFalse(run_before['lr_included'])
        self.assertEqual(run_before['lr_status'], 'unavailable')
        self.assertEqual(run_before['lr_error_code'], 'LR_NO_APPROVED_MODEL')

        q_before = inv.queue(scope_c1, run_before['run_id'])
        self.assertGreater(len(q_before['rows']), 0)
        row_b = q_before['rows'][0]
        self.assertEqual(row_b['lr_status'], 'unavailable')
        self.assertIsNone(row_b['lr_probability'])
        lr_before_dto = row_b['explanation']['supervised_lr']
        self.assertEqual(lr_before_dto['status'], 'unavailable')
        self.assertIsNone(lr_before_dto['score'])
        self.assertFalse(row_b['explanation']['unavailable_treated_as_zero'])
        self.assertTrue(any(u['method_id'] == 'supervised_lr' for u in row_b['explanation']['unavailable_methods']))

        # Now train & promote LR model to releasable_model!
        _, promoted_lr = self._train_and_promote_lr(lr_svc, scope_c1)

        # Run B: WITH approved LR model -> ALL 5 methods active, existing 4 methods untouched, LR participates in score!
        run_after = ml_svc.score_to_queue(
            scope_c1,
            {'snapshot_id': eval_sid, 'version_id': ov['active_version']['version_id'], 'lr_model_id': promoted_lr['model_id']},
            'r3-score-after-' + uuid.uuid4().hex[:10],
        )
        self.assertTrue(run_after['lr_included'])
        self.assertEqual(run_after['lr_status'], 'available')
        self.assertEqual(run_after['lr_model_version'], promoted_lr['version_tag'])

        q_after = inv.queue(scope_c1, run_after['run_id'])
        self.assertGreater(len(q_after['rows']), 0)

        before_by_tid = {r['transaction_id']: r for r in q_before['rows']}
        any_lr_boosted = False
        for r_after in q_after['rows']:
            tid = r_after['transaction_id']
            det = inv.detail(scope_c1, run_after['run_id'], tid, review_id=r_after['review_id'])
            five = det['explanation']['five_methods']
            self.assertEqual(
                [m['method_id'] for m in five],
                ['rules', 'statistics', 'graph', 'unsupervised_ml', 'supervised_lr'],
            )
            lr_dto = det['explanation']['supervised_lr']
            self.assertEqual(lr_dto['status'], 'available')
            self.assertEqual(lr_dto['model_version'], promoted_lr['version_tag'])
            self.assertIsNotNone(lr_dto['probability'])
            self.assertIn(lr_dto['prediction'], (0, 1))
            self.assertTrue(det['explanation']['components_reconcile'], det['explanation'])
            self.assertFalse(det['explanation']['unavailable_treated_as_zero'])

            # Existing rule_score & ml_score preserved identically!
            if tid in before_by_tid:
                rb = before_by_tid[tid]
                self.assertEqual(
                    det['explanation']['raw_components']['rule_score'],
                    rb['explanation']['raw_components']['rule_score'],
                )
                self.assertEqual(
                    det['explanation']['raw_components']['ml_score'],
                    rb['explanation']['raw_components']['ml_score'],
                )
                if (lr_dto.get('score') or 0) > 0:
                    any_lr_boosted = True
                    self.assertGreater(det['score'], rb['score'])

        self.assertTrue(any_lr_boosted, 'Expected at least one queued transaction to receive positive LR risk contribution')

    def test_05_verified_review_labels_feedback_loop(self):
        _, ml_svc, lr_svc, rel_svc, ws, inv, scope_c1, eval_sid = self._make_isolated_env('labels_loop')
        ov = ml_svc.overview(scope_c1)
        _, promoted_lr = self._train_and_promote_lr(lr_svc, scope_c1)
        scored = ml_svc.score_to_queue(
            scope_c1,
            {'snapshot_id': eval_sid, 'version_id': ov['active_version']['version_id'], 'lr_model_id': promoted_lr['model_id']},
            'r3-score-loop-' + uuid.uuid4().hex[:10],
        )
        q = inv.queue(scope_c1, scored['run_id'])
        # Deduplicate by review_id so we review distinct cases
        distinct_cases = []
        seen_rev = set()
        for r in q['rows']:
            if r['review_id'] not in seen_rev:
                seen_rev.add(r['review_id'])
                distinct_cases.append(r)
        self.assertGreaterEqual(len(distinct_cases), 4, 'Need at least 4 distinct queued cases for label-loop test')

        # Case 0 -> confirmed_risk (Vi phạm -> label 1)
        # Case 1 -> legitimate (Hợp lệ -> label 0)
        # Case 2 -> inconclusive (Chưa đủ bằng chứng -> MUST BE EXCLUDED!)
        # Case 3+ -> unreviewed (MUST BE EXCLUDED, NEVER label 0!)
        outcomes_plan = [
            (distinct_cases[0], 'confirmed_risk', 'Xác nhận vi phạm qua đối chiếu hóa đơn và nhật ký phê duyệt.'),
            (distinct_cases[1], 'legitimate', 'Xác nhận hợp lệ, đầy đủ chữ ký phê duyệt độc lập và hóa đơn gốc.'),
            (distinct_cases[2], 'inconclusive', 'Còn thiếu chứng từ gốc nên chưa đủ bằng chứng kết luận.'),
        ]
        for row, outcome_val, expl in outcomes_plan:
            det = inv.detail(scope_c1, scored['run_id'], row['transaction_id'], review_id=row['review_id'])
            ev_ids = [e['evidence_id'] for e in det['evidence'][:1]] or [row['transaction_id']]
            started = ws.action(scope_c1, scored['run_id'], row['review_id'], 'start', {})
            ws.action(
                scope_c1,
                scored['run_id'],
                row['review_id'],
                'save',
                {
                    'expected_revision': det['review']['revision'],
                    'lease': started['lease'],
                    'request_id': 'r3-rev-' + uuid.uuid4().hex[:12],
                    'feedback': {
                        'outcome': outcome_val,
                        'usefulness': 'not_assessed',
                        'explanation': expl,
                        'action': 'Ghi nhận kết quả kiểm tra R3.',
                        'missing_materials': 'Thiếu hóa đơn gốc.' if outcome_val == 'inconclusive' else '',
                        'evidence_ids': ev_ids,
                        'checks_completed': True,
                    },
                },
            )

        collected = lr_svc.collect_verified_review_labels(scope_c1, rel_svc)
        lmap = collected['labels_map']
        self.assertGreaterEqual(collected['fraud_count'], 1)
        self.assertGreaterEqual(collected['legitimate_count'], 1)
        self.assertEqual(lmap[distinct_cases[0]['transaction_id']], 1)
        self.assertEqual(lmap[distinct_cases[1]['transaction_id']], 0)
        self.assertNotIn(distinct_cases[2]['transaction_id'], lmap)
        self.assertNotIn(distinct_cases[3]['transaction_id'], lmap)
        self.assertGreaterEqual(collected['excluded_inconclusive_count'], 1)
        self.assertGreaterEqual(collected['excluded_unverified_count'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
