"""Tests for Area B (Model Training, Evaluation, Approval, Rollback & Queue Integration)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch

from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.import_files import ImportFailure, canonical, digest
from sme_fraud.investigation import Investigation
from sme_fraud.method_store import MethodStore
from sme_fraud.ml_estimators import CompanyEstimator
from sme_fraud.model_lifecycle import ModelLifecycle
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.review_server import make_server
from sme_fraud.rule35_ml_eval_demo import build_eval_source, build_fit_source
from sme_fraud.snapshots import SnapshotStore
from test_portal_auth import PortalHarness, portal


def _policy(dir_token: str, acc_token: str) -> dict:
    exp = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    return {
        'policy_version': '1.0.0',
        'principals': [
            {
                'actor_id': 'ml-director',
                'tenant_id': 'demo',
                'token_sha256': hashlib.sha256(dir_token.encode()).hexdigest(),
                'status': 'active',
                'expires_at': exp,
                'memberships': [
                    {'company_id': c, 'role': 'director', 'status': 'active', 'permissions': ['data.import', 'evidence.verify', 'model.fit']}
                    for c in ('C001', 'C002')
                ],
            },
            {
                'actor_id': 'ml-accountant',
                'tenant_id': 'demo',
                'token_sha256': hashlib.sha256(acc_token.encode()).hexdigest(),
                'status': 'active',
                'expires_at': exp,
                'memberships': [
                    {'company_id': c, 'role': 'accountant', 'status': 'active', 'permissions': ['data.import']}
                    for c in ('C001', 'C002')
                ],
            },
        ],
    }


def _commit(store: SnapshotStore, scope, data: dict, key: str) -> dict:
    draft = store.upload(scope, canonical(data), f'{key}.json', key + '-upload')
    prev = store.preview(scope, draft['import_id'], 1)
    assert prev['status'] != 'rejected', prev.get('errors')
    req = {k: prev[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
    req.update(expected_revision=prev['revision'], acknowledge=True)
    return store.commit(scope, draft['import_id'], req, key + '-commit')['snapshot']


class ModelLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.dir_tok = secrets.token_urlsafe(24)
        cls.acc_tok = secrets.token_urlsafe(24)
        cls.dir_hdr = 'Bearer ' + cls.dir_tok
        cls.acc_hdr = 'Bearer ' + cls.acc_tok
        cls.policy_path = cls.base / 'policy.json'
        cls.policy_path.write_bytes(canonical(_policy(cls.dir_tok, cls.acc_tok)))
        cls.auth = FileAuthorizer(cls.policy_path)
        cls.snapshots = SnapshotStore(cls.base / 'snapshots.sqlite3')
        cls.model_db = cls.base / 'models.sqlite3'
        MethodStore(cls.model_db)
        cls.bindings_file = cls.base / 'analysis-bindings.json'
        cls.bindings_file.write_bytes(canonical({'version': BINDINGS_VERSION, 'bindings': []}))
        cls.resources = AnalysisResources(cls.model_db, cls.bindings_file)
        cls.rel_store = ReleaseStore(cls.base / 'releases.sqlite3', b'm' * 32)
        cls.cq_store = CaseQueueStore(cls.base / 'case-queue.sqlite3')
        cls.release_svc = ReleaseService(cls.rel_store, cls.snapshots, cls.resources, cls.cq_store)
        cls.lifecycle = ModelLifecycle(
            cls.base / 'model-lifecycle.sqlite3',
            snapshot_store=cls.snapshots,
            analysis_resources=cls.resources,
            authorizer=cls.auth,
            case_queue_store=cls.cq_store,
            release_service=cls.release_svc,
        )

        cls.fit_snaps = {}
        cls.eval_snaps = {}
        for comp in ('C001', 'C002'):
            sc = cls.auth.authorize_director(cls.dir_hdr, comp)
            cls.fit_snaps[comp] = _commit(cls.snapshots, sc, build_fit_source(comp), f'mlc-fit-{comp}')
            cls.eval_snaps[comp] = _commit(cls.snapshots, sc, build_eval_source(comp), f'mlc-eval-{comp}')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _dir(self, comp='C001'):
        return self.auth.authorize_director(self.dir_hdr, comp)

    def _acc(self, comp='C001'):
        return self.auth.authorize(self.acc_hdr, comp)

    def test_01_shared_data_profile_and_33_features_without_upload(self):
        sc = self._dir('C001')
        ov = self.lifecycle.overview(sc)
        self.assertEqual(ov['company_id'], 'C001')
        self.assertEqual(ov['shared_data']['snapshot_count'], 2)
        self.assertEqual(ov['feature_contract']['total_features'], 33)
        self.assertIn('isolation_forest', [a['id'] for a in ov['algorithms']])
        self.assertIn('autoencoder', [a['id'] for a in ov['algorithms']])

        prof = self.lifecycle.profile_snapshot(sc, self.eval_snaps['C001']['snapshot_id'])
        self.assertEqual(prof['snapshot']['transaction_count'], 67)
        self.assertGreater(prof['data_quality_score'], 50)
        self.assertTrue(prof['recommended_split']['split_feasible'])
        self.assertEqual(len(prof['feature_contract']['features']), 33)
        self.assertIn('labels', prof['feature_contract']['excluded_predictors'])

    def test_02_train_isolation_forest_and_autoencoder_evaluate_without_refit_and_govern_approval_rollback(self):
        sc1 = self._dir('C001')
        sc2 = self._dir('C002')
        fit_id = self.fit_snaps['C001']['snapshot_id']
        eval_id = self.eval_snaps['C001']['snapshot_id']

        # Train candidate v1 (Isolation Forest)
        r_if = self.lifecycle.train_candidate(
            sc1, self.dir_hdr,
            {
                'snapshot_id': fit_id,
                'eval_snapshot_id': eval_id,
                'method_id': 'isolation_forest',
                'missing_policy': 'median_flags',
                'history_start': '2026-07-01T00:00:00+07:00',
                'history_end': '2026-08-31T23:59:59+07:00',
                'reference_start': '2026-09-01T00:00:00+07:00',
                'reference_end': '2026-09-21T00:00:00+07:00',
                'evaluation_start': '2026-10-01T00:00:00+07:00',
            },
            'test-train-if-c001-01',
        )
        v1 = r_if['version']
        self.assertEqual(v1['version_tag'], 'C001-v1')
        self.assertEqual(v1['status'], 'pending_approval')
        self.assertTrue(v1['evaluation']['technical_ready'])
        self.assertTrue(v1['evaluation']['missing_robustness_pass'])
        self.assertEqual(v1['evaluation']['label_basis'], 'scenario_unsupervised')
        self.assertIsNone(v1['evaluation']['verified_useful_hits'])

        # Unapproved candidate CANNOT be scored into Area A queue!
        with self.assertRaises(ImportFailure) as err:
            self.lifecycle.score_to_queue(sc1, {'snapshot_id': eval_id, 'version_id': v1['version_id']}, 'unapproved-score-01')
        self.assertEqual(err.exception.code, 'MODEL_APPROVAL_REQUIRED')

        # Train candidate v2 (Autoencoder)
        r_ae = self.lifecycle.train_candidate(
            sc1, self.dir_hdr,
            {
                'snapshot_id': fit_id,
                'eval_snapshot_id': eval_id,
                'method_id': 'autoencoder',
                'missing_policy': 'median_flags',
                'history_start': '2026-07-01T00:00:00+07:00',
                'history_end': '2026-08-31T23:59:59+07:00',
                'reference_start': '2026-09-01T00:00:00+07:00',
                'reference_end': '2026-09-21T00:00:00+07:00',
                'evaluation_start': '2026-10-01T00:00:00+07:00',
            },
            'test-train-ae-c001-02',
        )
        v2 = r_ae['version']
        self.assertEqual(v2['version_tag'], 'C001-v2')
        self.assertTrue(v2['evaluation']['top_attributions'])

        # Re-evaluation NEVER refits any model
        with patch.object(CompanyEstimator, 'fit', side_effect=AssertionError('Must never fit during evaluate')):
            reev = self.lifecycle.evaluate_version(sc1, v2['version_id'], eval_id)
        self.assertEqual(reev['version']['version_id'], v2['version_id'])

        # Approval requires reviewed_evaluation=True and reason >= 10 chars
        with self.assertRaises(ImportFailure):
            self.lifecycle.approve_and_activate(sc1, {'version_id': v1['version_id'], 'mode': 'shadow', 'reason': 'ok', 'reviewed_evaluation': False}, 'bad-app-01')

        # Approve v1 into active -> updates C001 binding atomically
        ap1 = self.lifecycle.approve_and_activate(
            sc1,
            {'version_id': v1['version_id'], 'mode': 'active', 'reason': 'Đạt đủ 4 tiêu chí kiểm tra chất lượng trên tập tách kỳ.', 'reviewed_evaluation': True},
            'approve-v1-0001',
        )
        self.assertEqual(ap1['version']['status'], 'active')
        sel_after_v1, _ = self.resources.selection(sc1)
        self.assertEqual(sel_after_v1['ml_artifacts'], {'isolation_forest': v1['artifact_id']})

        # Approve v2 into shadow -> v1 becomes superseded, C001 binding switches to autoencoder
        ap2 = self.lifecycle.approve_and_activate(
            sc1,
            {'version_id': v2['version_id'], 'mode': 'shadow', 'reason': 'Chạy thử Autoencoder đối chiếu đặc trưng tái tạo.', 'reviewed_evaluation': True},
            'approve-v2-0002',
        )
        self.assertEqual(ap2['version']['status'], 'shadow')
        sel_after_v2, _ = self.resources.selection(sc1)
        self.assertEqual(sel_after_v2['ml_artifacts'], {'autoencoder': v2['artifact_id']})

        # Score to Area A queue using approved v2 WITHOUT fitting!
        with patch.object(CompanyEstimator, 'fit', side_effect=AssertionError('Must never fit during queue scoring')):
            scored = self.lifecycle.score_to_queue(
                sc1,
                {'snapshot_id': eval_id, 'version_id': v2['version_id']},
                'score-queue-v2-001',
            )
        self.assertGreater(scored['admitted_cases'], 0)
        self.assertEqual(scored['version_tag'], 'C001-v2')

        # Verify Area A Investigation immediately displays prioritized queue traced to C001-v2!
        inv = Investigation(self.release_svc.workspace)
        q = inv.queue(sc1, scored['run_id'])
        self.assertTrue(q['rows'])
        first = q['rows'][0]
        self.assertEqual(first['explanation']['model_version_tag'], 'C001-v2')
        self.assertTrue(any(m['artifact_id'] == v2['artifact_id'] for m in first['model_trace']))
        self.assertTrue(first['explanation']['components_reconcile'])

        # Rollback from v2 back to v1!
        rb = self.lifecycle.rollback_version(
            sc1,
            {'target_version_id': v1['version_id'], 'reason': 'Hoàn nguyên về Isolation Forest v1 sau đợt chạy thử.'},
            'rollback-to-v1-01',
        )
        self.assertEqual(rb['version']['version_id'], v1['version_id'])
        self.assertEqual(rb['version']['status'], 'active')
        sel_rb, _ = self.resources.selection(sc1)
        self.assertEqual(sel_rb['ml_artifacts'], {'isolation_forest': v1['artifact_id']})

        # Cross-company isolation: C002 cannot see or rollback C001 versions
        ov2 = self.lifecycle.overview(sc2)
        self.assertEqual(ov2['versions'], [])
        with self.assertRaises(ImportFailure) as c_err:
            self.lifecycle.rollback_version(sc2, {'target_version_id': v1['version_id'], 'reason': 'Cross company probe attempt'}, 'cross-rb-001')
        self.assertEqual(c_err.exception.status, 404)

    def test_03_rbac_denies_accountant_without_model_fit_on_http_api(self):
        with PortalHarness() as h:
            h.agent.shutdown()
            h.agent.server_close()
            h.agent = make_server(
                0, h.authorizer, self.snapshots, self.resources,
                case_queue_store=self.cq_store, release_service=self.release_svc,
            )
            portal.CFG['agents']['agent2']['port'] = h.agent.server_port
            t = threading.Thread(target=h.agent.serve_forever, daemon=True)
            t.start()
            h.threads.append(t)

            # Unauthenticated request denied with 401
            st_unauth, _ = h.request(h.url('model-lifecycle'), token=False)
            self.assertEqual(st_unauth, 401)

            # Accountant without director role denied with 403
            acc_policy = deepcopy(json.loads(h.access.read_text('utf-8')))
            for m in acc_policy['memberships']:
                m['role'] = 'accountant'
                m['permissions'] = ['data.import']
            h.access.write_bytes(canonical(acc_policy))
            st_acc, _ = h.request(h.url('model-lifecycle'))
            self.assertEqual(st_acc, 403)

            # Director with model.fit succeeds on GET overview
            dir_policy = deepcopy(acc_policy)
            for m in dir_policy['memberships']:
                m['role'] = 'director'
                m['permissions'] = ['data.import', 'evidence.verify', 'model.fit']
            h.access.write_bytes(canonical(dir_policy))
            st_ok, body_ok = h.request(h.url('model-lifecycle'))
            self.assertEqual(st_ok, 200, body_ok)
            self.assertEqual(body_ok['company_id'], 'C001')


if __name__ == '__main__':
    unittest.main()
