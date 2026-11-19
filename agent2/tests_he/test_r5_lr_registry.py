"""R5 Verification Suite — Validation (9 Metrics), 4-Way Comparison, Quality Gate & 9-State LR Model Registry."""
from __future__ import annotations

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

from finance_input import AccessScope
from sme_fraud.import_files import ImportFailure
from sme_fraud.lr_inference import SupervisedLRAdapter
from sme_fraud.lr_registry import (
    ALLOWED_TRANSITIONS,
    LIFECYCLE_STATES,
    LRModelRegistry,
    LRQualityGateConfig,
    build_representative_sme_eval_dataset,
    compute_binary_classification_metrics,
    compute_pr_auc,
    feature_schema_hash,
)


class R5LRRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_base = REPO / '.runtime' / 'tmp_r5_tests' / uuid.uuid4().hex[:10]
        cls.tmp_base.mkdir(parents=True, exist_ok=True)
        cls.scope_c1 = AccessScope(
            tenant_id='demo',
            company_ids=frozenset({'C001'}),
            actor_id='r5-director-c1',
            permissions=frozenset({'data.import', 'evidence.verify', 'model.fit'}),
        )
        cls.scope_acc = AccessScope(
            tenant_id='demo',
            company_ids=frozenset({'C001'}),
            actor_id='r5-accountant-c1',
            permissions=frozenset({'data.import'}),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp_base, ignore_errors=True)

    def _make_registry(self, name: str, gate_cfg: LRQualityGateConfig | None = None) -> LRModelRegistry:
        return LRModelRegistry(
            self.tmp_base / f'{name}_{uuid.uuid4().hex[:6]}' / 'lr-registry.sqlite3',
            quality_gate_config=gate_cfg,
        )

    def test_01_all_9_mandatory_metrics_and_exact_pr_auc(self):
        y_true = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        probs = [0.90, 0.80, 0.70, 0.30, 0.65, 0.25, 0.20, 0.20, 0.15, 0.10]
        m = compute_binary_classification_metrics(y_true, probs, threshold=0.50)
        self.assertEqual(m['confusion_matrix'], {'tp': 3, 'fp': 1, 'tn': 5, 'fn': 1})
        self.assertAlmostEqual(m['recall_class_1'], 0.75, places=4)
        self.assertAlmostEqual(m['precision_class_1'], 0.75, places=4)
        self.assertAlmostEqual(m['f1_score'], 0.75, places=4)
        self.assertEqual(m['false_positives_per_1000'], 100.0)
        self.assertGreater(m['pr_auc'], 0.80)
        self.assertLessEqual(m['pr_auc'], 1.0)
        # Tied scores handled deterministically (no order inflation)
        pr_tied = compute_pr_auc([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5])
        self.assertAlmostEqual(pr_tied, 0.5, places=6)

    def test_02_quality_gate_blocks_high_recall_excessive_fp_and_insufficient_positives_and_forged_flag(self):
        reg = self._make_registry('gate')

        # 1. Forging quality_approved=True on register MUST be rejected!
        with self.assertRaises(ImportFailure) as ctx:
            reg.register_model(self.scope_c1, {'coefficients': [0.5, 0.5], 'intercept': -0.5, 'quality_approved': True})
        self.assertEqual(ctx.exception.code, 'QUALITY_APPROVAL_MUST_BE_EVIDENCE_BASED')

        # 2. Tiny holdout (only 2 positives) -> BLOCKED (INSUFFICIENT_POSITIVE_SAMPLES), quality_approved=False!
        r_small = reg.register_model(self.scope_c1, {'coefficients': [1.0, 1.0], 'intercept': -1.0, 'train_time_seconds': 2.5})['model']
        self.assertEqual(r_small['lifecycle_state'], 'VALIDATING')
        self.assertFalse(r_small['quality_approved'])

        v_small = reg.validate_model(self.scope_c1, {'registry_id': r_small['registry_id'], 'eval_mode': 'small_job_holdout'})['model']
        self.assertEqual(v_small['lifecycle_state'], 'BLOCKED')
        self.assertFalse(v_small['quality_approved'])
        codes_small = {b['code'] for b in v_small['quality_gate']['blocking_reasons']}
        self.assertIn('INSUFFICIENT_POSITIVE_SAMPLES', codes_small)

        # 3. High Recall (100% > 90%) achieved via predicting almost everything positive -> FP/1000 explodes -> BLOCKED!
        r_noisy = reg.register_model(self.scope_c1, {'coefficients': [0.1, 0.1], 'intercept': 2.0, 'train_time_seconds': 1.2})['model']
        v_noisy = reg.validate_model(
            self.scope_c1,
            {'registry_id': r_noisy['registry_id'], 'eval_mode': 'representative_sme_benchmark', 'threshold': 0.10},
        )['model']
        self.assertEqual(v_noisy['metrics']['recall_class_1'], 1.0)
        self.assertGreater(v_noisy['metrics']['false_positives_per_1000'], 500.0)
        self.assertEqual(v_noisy['lifecycle_state'], 'BLOCKED')
        self.assertFalse(v_noisy['quality_approved'])
        codes_noisy = {b['code'] for b in v_noisy['quality_gate']['blocking_reasons']}
        self.assertIn('EXCESSIVE_FALSE_POSITIVES_PER_1000', codes_noisy)
        self.assertIn('PRECISION_BELOW_FLOOR', codes_noisy)

        # 4. Failed FHE implementation parity -> BLOCKED even with great accuracy!
        r_bad_fhe = reg.register_model(self.scope_c1, {
            'coefficients': [1.5, 1.5], 'intercept': -1.0, 'train_time_seconds': 3.0,
            'fhe_error': {'implementation_error': {'pass': False, 'weight_max_abs_diff': 0.5}},
        })['model']
        v_bad_fhe = reg.validate_model(self.scope_c1, {'registry_id': r_bad_fhe['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']
        self.assertEqual(v_bad_fhe['lifecycle_state'], 'BLOCKED')
        self.assertFalse(v_bad_fhe['quality_approved'])
        self.assertIn('FHE_PARITY_FAILED', {b['code'] for b in v_bad_fhe['quality_gate']['blocking_reasons']})

    def test_03_four_way_comparison_and_real_incremental_value_of_lr(self):
        reg = self._make_registry('compare')
        # First model v1 (weaker weights) -> validated on representative benchmark (N=200, 24 positives)
        m1 = reg.register_model(self.scope_c1, {
            'coefficients': [0.5, 0.5], 'intercept': -0.5, 'train_time_seconds': 4.1,
            'circuit_version': 'legacy_s2_v1',
            'training_data_provenance': {'source_mode': 'verified_test_dataset', 'train_sample_count': 16, 'train_positive_count': 8, 'train_negative_count': 8, 'simulated': True},
        })['model']
        v1 = reg.validate_model(self.scope_c1, {'registry_id': m1['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']

        # Check all 9 mandatory metrics exist on v1!
        met = v1['metrics']
        for key in ('recall_class_1', 'precision_class_1', 'f1_score', 'pr_auc', 'confusion_matrix', 'false_positives_per_1000', 'train_time_seconds', 'inference_time_ms', 'fhe_error_vs_reference'):
            self.assertIn(key, met)
            self.assertIsNotNone(met[key])

        # Check all 4 comparison benchmarks exist!
        cmp1 = v1['comparisons']
        self.assertIn('lr_baseline', cmp1)
        self.assertIn('previous_lr_version', cmp1)
        self.assertFalse(cmp1['previous_lr_version']['available'])
        self.assertEqual(cmp1['previous_lr_version']['reason'], 'NO_PREVIOUS_LR_VERSION')
        self.assertIn('pipeline_4_methods', cmp1)
        self.assertIn('pipeline_5_methods', cmp1)

        # Check true incremental value: 5-method pipeline catches stealth fraud cases missed by 4-method pipeline!
        inc = v1['incremental_value']
        self.assertGreater(inc['newly_caught_fraud_count'], 0, inc)
        self.assertGreater(inc['delta_recall'], 0.0, inc)
        self.assertEqual(inc['verdict'], 'positive_incremental_value')
        self.assertGreater(met['recall_class_1'], 0.90)
        self.assertLessEqual(met['false_positives_per_1000'], 150.0)
        self.assertTrue(v1['quality_approved'], v1['quality_gate'])
        self.assertEqual(v1['lifecycle_state'], 'CANDIDATE')

        # Second model v2 -> compares directly against v1 as `previous_lr_version`!
        m2 = reg.register_model(self.scope_c1, {
            'coefficients': [1.0, 1.0], 'intercept': -1.0, 'train_time_seconds': 5.2,
            'circuit_version': 'fhe_sgd_s16_v2',
        })['model']
        v2 = reg.validate_model(self.scope_c1, {'registry_id': m2['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']
        self.assertTrue(v2['comparisons']['previous_lr_version']['available'])
        self.assertEqual(v2['comparisons']['previous_lr_version']['model_version'], 'C001-lr-v1')
        self.assertIsNotNone(v2['incremental_value']['vs_previous_lr'])

    def test_04_strict_9_state_lifecycle_transitions_rollback_rejected_blocked_and_metadata(self):
        reg = self._make_registry('lifecycle')

        # Register & validate v1 -> CANDIDATE
        v1 = reg.register_model(self.scope_c1, {'coefficients': [0.5, 0.5], 'intercept': -0.5, 'train_time_seconds': 3.5, 'circuit_version': 'legacy_s2_v1'})['model']
        v1 = reg.validate_model(self.scope_c1, {'registry_id': v1['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']
        self.assertEqual(v1['lifecycle_state'], 'CANDIDATE')
        self.assertTrue(v1['quality_approved'])

        # RBAC check: accountant without model.fit cannot transition
        with self.assertRaises(ImportFailure) as ctx_rbac:
            reg.transition_state(self.scope_acc, {'registry_id': v1['registry_id'], 'target_state': 'SHADOW', 'reason': 'Thử chuyển trạng thái không có quyền fit.'})
        self.assertEqual(ctx_rbac.exception.status, 403)

        # Skipping SHADOW (CANDIDATE -> APPROVED or CANDIDATE -> ACTIVE) MUST fail!
        with self.assertRaises(ImportFailure) as ctx_skip:
            reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'APPROVED', 'reason': 'Cố gắng bỏ qua bước SHADOW.', 'reviewed_evidence': True})
        self.assertEqual(ctx_skip.exception.code, 'INVALID_LIFECYCLE_TRANSITION')

        # CANDIDATE -> SHADOW
        v1 = reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'SHADOW', 'reason': 'Đưa phiên bản v1 vào chế độ chạy thử shadow.'})['model']
        self.assertEqual(v1['lifecycle_state'], 'SHADOW')

        # SHADOW -> APPROVED requires reviewed_evidence=True!
        with self.assertRaises(ImportFailure) as ctx_chk:
            reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'APPROVED', 'reason': 'Phê duyệt thiếu tích xác nhận bằng chứng.', 'reviewed_evidence': False})
        self.assertEqual(ctx_chk.exception.code, 'EVIDENCE_REVIEW_CHECK_REQUIRED')

        v1 = reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'APPROVED', 'reason': 'Đã đối chiếu đủ 9 metrics, FP/1000 và giá trị bổ sung 5 phương pháp.', 'reviewed_evidence': True})['model']
        self.assertEqual(v1['lifecycle_state'], 'APPROVED')
        self.assertIsNotNone(v1['approval_record'])
        self.assertEqual(v1['approval_record']['approved_by'], 'r5-director-c1')
        self.assertEqual(v1['approval_record']['signature_envelope']['algorithm'], 'ed25519')

        # APPROVED -> ACTIVE
        v1 = reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'ACTIVE', 'reason': 'Kích hoạt phiên bản v1 làm LR chính thức cho doanh nghiệp C001.'})['model']
        self.assertEqual(v1['lifecycle_state'], 'ACTIVE')
        self.assertIsNotNone(v1['activation_timestamp'])
        self.assertEqual(v1['feature_schema_hash'], feature_schema_hash())
        self.assertTrue(v1['training_data_provenance']['privacy_redacted'])

        # Promote v2 -> ACTIVE (records rollback_target = v1!)
        v2 = reg.register_model(self.scope_c1, {'coefficients': [1.0, 1.0], 'intercept': -1.0, 'train_time_seconds': 4.0, 'circuit_version': 'fhe_sgd_s16_v2'})['model']
        v2 = reg.validate_model(self.scope_c1, {'registry_id': v2['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']
        v2 = reg.transition_state(self.scope_c1, {'registry_id': v2['registry_id'], 'target_state': 'SHADOW', 'reason': 'Chạy thử phiên bản v2 cải tiến.'})['model']
        v2 = reg.transition_state(self.scope_c1, {'registry_id': v2['registry_id'], 'target_state': 'APPROVED', 'reason': 'Phê duyệt v2 đạt đủ cổng chất lượng R5.', 'reviewed_evidence': True})['model']
        v2 = reg.transition_state(self.scope_c1, {'registry_id': v2['registry_id'], 'target_state': 'ACTIVE', 'reason': 'Kích hoạt v2 thay thế v1 với mục tiêu hoàn nguyên.'})['model']
        self.assertEqual(v2['lifecycle_state'], 'ACTIVE')
        self.assertEqual(v2['rollback_target'], v1['registry_id'])

        # ACTIVE -> ROLLED_BACK on v2 restores v1 to ACTIVE!
        v2_rb = reg.transition_state(self.scope_c1, {'registry_id': v2['registry_id'], 'target_state': 'ROLLED_BACK', 'reason': 'Hoàn nguyên từ v2 về v1 theo kiểm tra hậu phát hành.'})['model']
        self.assertEqual(v2_rb['lifecycle_state'], 'ROLLED_BACK')
        ov = reg.overview(self.scope_c1)
        self.assertEqual(ov['active_model']['registry_id'], v1['registry_id'])
        self.assertEqual(ov['active_model']['lifecycle_state'], 'ACTIVE')

        # Also test BLOCKED -> VALIDATING -> CANDIDATE -> REJECTED (terminal)
        v3 = reg.register_model(self.scope_c1, {'coefficients': [0.5, 0.5], 'intercept': -0.5, 'train_time_seconds': 2.0})['model']
        v3 = reg.validate_model(self.scope_c1, {'registry_id': v3['registry_id'], 'eval_mode': 'small_job_holdout'})['model']
        self.assertEqual(v3['lifecycle_state'], 'BLOCKED')
        v3 = reg.validate_model(self.scope_c1, {'registry_id': v3['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']
        self.assertEqual(v3['lifecycle_state'], 'CANDIDATE')
        v3 = reg.transition_state(self.scope_c1, {'registry_id': v3['registry_id'], 'target_state': 'REJECTED', 'reason': 'Loại bỏ ứng viên v3 do trùng cấu hình với v1.'})['model']
        self.assertEqual(v3['lifecycle_state'], 'REJECTED')
        self.assertFalse(v3['quality_approved'])
        # Terminal REJECTED rejects any further transition
        with self.assertRaises(ImportFailure) as ctx_term:
            reg.transition_state(self.scope_c1, {'registry_id': v3['registry_id'], 'target_state': 'SHADOW', 'reason': 'Thử hồi sinh model đã REJECTED.'})
        self.assertEqual(ctx_term.exception.code, 'INVALID_LIFECYCLE_TRANSITION')

        # Verify state_history recorded full immutable chain on v1
        v1_latest = next(m for m in ov['models'] if m['registry_id'] == v1['registry_id'])
        states_seen = [ev['to_state'] for ev in v1_latest['state_history']]
        self.assertEqual(states_seen[:6], ['TRAINING', 'VALIDATING', 'CANDIDATE', 'SHADOW', 'APPROVED', 'ACTIVE'])

    def test_05_r3_pipeline_adapter_enforces_r5_active_and_blocks_unapproved_states(self):
        reg = self._make_registry('r3_bridge')
        adapter = SupervisedLRAdapter(lr_registry=reg)

        # Register v1 (CANDIDATE only, NOT ACTIVE) -> Adapter MUST NOT load it!
        v1 = reg.register_model(self.scope_c1, {'coefficients': [0.5, 0.5], 'intercept': -0.5, 'train_time_seconds': 2.0})['model']
        v1 = reg.validate_model(self.scope_c1, {'registry_id': v1['registry_id'], 'eval_mode': 'representative_sme_benchmark'})['model']
        self.assertEqual(v1['lifecycle_state'], 'CANDIDATE')

        res_cand = adapter.load_approved_model(self.scope_c1, model_id=v1['registry_id'])
        self.assertFalse(res_cand['available'])
        self.assertEqual(res_cand['error_code'], 'LR_MODEL_NOT_ACTIVE_OR_UNAPPROVED')

        # Walk v1 -> SHADOW -> APPROVED -> ACTIVE -> Adapter NOW loads & verifies Ed25519 cleanly!
        reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'SHADOW', 'reason': 'Chuyển shadow để kiểm thử tích hợp.'})
        reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'APPROVED', 'reason': 'Phê duyệt đủ 9 metrics và cổng chất lượng R5.', 'reviewed_evidence': True})
        reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'ACTIVE', 'reason': 'Kích hoạt vào pipeline phát hiện Agent2.'})

        res_act = adapter.load_approved_model(self.scope_c1)
        self.assertTrue(res_act['available'], res_act)
        self.assertEqual(res_act['model']['version_tag'], 'C001-lr-v1')

        # Block v1 (ACTIVE -> BLOCKED) -> Adapter immediately stops serving it (returns unavailable, NEVER 0!)
        reg.transition_state(self.scope_c1, {'registry_id': v1['registry_id'], 'target_state': 'BLOCKED', 'reason': 'Khóa khẩn cấp để kiểm tra drift phân phối.'})
        res_blk = adapter.load_approved_model(self.scope_c1)
        self.assertFalse(res_blk['available'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
