"""Tests for full 35-rule baseline vs 35-rule + ML selection comparison and locking."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest

from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.comparison_store import ComparisonStore
from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from sme_fraud.rule35_comparison import (
    BUDGET,
    POLICY,
    make_rule35_plan,
    rule35_cases_for,
    rule35_report_for,
)
from sme_fraud.rule35_ml_eval_demo import (
    COMPANY_METHODS,
    EVAL_AS_OF,
    build_eval_source,
    build_fit_source,
    fit_config,
)
from sme_fraud.rule_snapshot import analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore


def _policy(token, reader_token):
    exp = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    return dict(
        policy_version='1.0.0',
        principals=[
            dict(
                actor_id='cmp35-director',
                tenant_id='demo',
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                status='active',
                expires_at=exp,
                memberships=[
                    dict(company_id=c, role='director', status='active', permissions=['data.import', 'model.fit'])
                    for c in ('C001', 'C002')
                ],
            ),
            dict(
                actor_id='cmp35-reader',
                tenant_id='demo',
                token_sha256=hashlib.sha256(reader_token.encode()).hexdigest(),
                status='active',
                expires_at=exp,
                memberships=[
                    dict(company_id=c, role='accountant', status='active', permissions=['data.import'])
                    for c in ('C001', 'C002')
                ],
            ),
        ],
    )


def _commit(store, scope, data, key):
    draft = store.upload(scope, canonical(data), f'{key}.json', key + '-u')
    p = store.preview(scope, draft['import_id'], 1)
    if p['status'] == 'rejected':
        raise AssertionError(p['errors'])
    req = {k: p[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
    req.update(expected_revision=p['revision'], acknowledge=True)
    return store.commit(scope, draft['import_id'], req, key + '-c')['snapshot']


def _rehash(bundle):
    src = bundle['source']
    for table, rows in src['tables'].items():
        src['coverage'][table] = dict(
            src['coverage'][table],
            record_count=len(rows),
            records_sha256=digest(canonical(rows)),
        )
    return bundle


class Rule35ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.token = secrets.token_urlsafe(24)
        cls.reader_token = secrets.token_urlsafe(24)
        cls.header = 'Bearer ' + cls.token
        cls.reader_header = 'Bearer ' + cls.reader_token
        cls.policy_path = cls.base / 'policy.json'
        cls.policy_path.write_bytes(canonical(_policy(cls.token, cls.reader_token)))
        cls.auth = FileAuthorizer(cls.policy_path)
        cls.snapshots = SnapshotStore(cls.base / 'snapshots.sqlite3')
        cls.models = MethodStore(cls.base / 'models.sqlite3')
        cls.review_key = digest(b'test-rule35-reviews').encode()[:32]
        cls.cmp_key = digest(b'test-rule35-comparisons').encode()[:32]

        cls.eval_data = {}
        cls.eval_manifest = {}
        cls.analyses = {}
        bindings = []

        for company, ml_method in COMPANY_METHODS.items():
            scope = cls.auth.authorize(cls.header, company)
            fit_data = build_fit_source(company, tenant_id='demo')
            fit_snap = _commit(cls.snapshots, scope, fit_data, f'fit-{company}')
            rz = run_fit_job(cls.snapshots, cls.models, cls.auth, cls.header, company,
                             fit_config(fit_snap['snapshot_id'], 'robust_z'), f'fit-rz-{company}')
            ml = run_fit_job(cls.snapshots, cls.models, cls.auth, cls.header, company,
                             fit_config(fit_snap['snapshot_id'], ml_method), f'fit-ml-{company}')
            self_assert_status = rz['job']['status'] == 'succeeded' and ml['job']['status'] == 'succeeded'
            if not self_assert_status:
                raise AssertionError((rz, ml))
            bindings.append(dict(
                tenant_id='demo',
                company_id=company,
                statistics_artifact_id=rz['job']['artifact_id'],
                ml_artifacts={ml_method: ml['job']['artifact_id']},
            ))
            ev_data = build_eval_source(company, tenant_id='demo')
            ev_snap = _commit(cls.snapshots, scope, ev_data, f'eval-{company}')
            cls.eval_data[company] = ev_data
            cls.eval_manifest[company] = ev_snap

        cls.bindings_file = cls.base / 'analysis-bindings.json'
        cls.bindings_file.write_bytes(canonical(dict(version=BINDINGS_VERSION, bindings=bindings)))
        cls.resources = AnalysisResources(model_db=cls.base / 'models.sqlite3', bindings_file=cls.bindings_file)

        for company in COMPANY_METHODS:
            scope = cls.auth.authorize(cls.header, company)
            cls.analyses[company] = analyze_rule_snapshot(
                cls.snapshots, scope, cls.eval_manifest[company]['snapshot_id'], EVAL_AS_OF,
                technical=True, resources=cls.resources,
            )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _scope(self, company):
        return self.auth.authorize(self.header, company)

    def test_01_c001_c002_full_35_rule_baseline_and_ml_fill_from_25_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            reviews = ReviewStore(Path(td) / 'reviews.sqlite3', self.review_key)

            # C001: 3 rule hits (P1 simultaneous pair + C2) -> IF adds 2 = 5/5.
            c1_scope = self._scope('C001')
            c1_cases = rule35_cases_for(self.snapshots, c1_scope, self.analyses['C001'], reviews, raw_data=self.eval_data['C001'])
            c1_plan = make_rule35_plan(
                self.analyses['C001'], c1_cases, self.eval_manifest['C001'],
                ml_method='isolation_forest', raw_data=self.eval_data['C001'],
            )
            c1_report = rule35_report_for(c1_plan, c1_cases, redaction='technical')
            self.assertEqual([k[0] for k in c1_plan['baseline']], ['C1_EV_01_P1A', 'C1_EV_02_P1B', 'C1_EV_03_C2'])
            self.assertEqual(len(c1_plan['added']), 2)
            self.assertEqual(len(c1_plan['combined']), 5)
            self.assertEqual(c1_report['ml_addition_summary']['status'], 'ml_filled_remaining_slots')
            self.assertEqual(c1_report['ml_addition_summary']['added_after_all_applicable_rules_no_hit'], 2)
            self.assertTrue(c1_plan['candidate_isolation']['history_excluded_from_candidates'])
            self.assertEqual(c1_plan['candidate_isolation']['history_only_count'], 42)
            self.assertEqual(c1_report['coverage']['total_candidates'], 25)
            self.assertEqual(c1_report['coverage']['master_quality_dedup_groups'], 1)
            self.assertFalse(c1_plan['he_execution'])

            # C002: 4 non-P1 rule hits (A6, B1/B2, B2, E2) -> ECOD adds 1 clean anomaly = 5/5.
            c2_scope = self._scope('C002')
            c2_cases = rule35_cases_for(self.snapshots, c2_scope, self.analyses['C002'], reviews, raw_data=self.eval_data['C002'])
            c2_plan = make_rule35_plan(
                self.analyses['C002'], c2_cases, self.eval_manifest['C002'],
                ml_method='ecod', raw_data=self.eval_data['C002'],
            )
            c2_report = rule35_report_for(c2_plan, c2_cases, redaction='technical')
            self.assertEqual([k[0] for k in c2_plan['baseline']], ['C2_EV_01_A6', 'C2_EV_02_B1', 'C2_EV_03_B2', 'C2_EV_04_E2'])
            self.assertEqual([k[0] for k in c2_plan['added']], ['C2_EV_07_ML_CLEAN'])
            self.assertEqual(c2_report['added'][0]['ml_addition_basis'], 'all_applicable_rules_evaluated_no_hit')
            self.assertEqual(c2_report['baseline']['metrics']['selected'], 4)
            self.assertEqual(c2_report['baseline']['metrics']['unused_slots'], 1)
            self.assertEqual(c2_report['combined']['metrics']['selected'], 5)
            # Metrics remain null before human review, zero synthetic feedback.
            self.assertIsNone(c2_report['combined']['metrics']['accuracy'])
            self.assertIsNone(c2_report['combined']['metrics']['declared_precision_resolved'])
            self.assertIsNone(c2_report['combined']['metrics']['saved_connected_seconds'])
            self.assertEqual(c2_report['combined']['metrics']['pending'], 5)

    def test_02_deterministic_order_and_b5_e4_master_scope_guards(self):
        with tempfile.TemporaryDirectory() as td:
            reviews = ReviewStore(Path(td) / 'reviews.sqlite3', self.review_key)
            scope = self._scope('C001')
            cases = rule35_cases_for(self.snapshots, scope, self.analyses['C001'], reviews, raw_data=self.eval_data['C001'])
            plan1 = make_rule35_plan(self.analyses['C001'], cases, self.eval_manifest['C001'], ml_method='isolation_forest')

            shuffled = deepcopy(self.analyses['C001'])
            shuffled['rows'].reverse()
            shuffled_cases = list(reversed(cases))
            plan2 = make_rule35_plan(shuffled, shuffled_cases, self.eval_manifest['C001'], ml_method='isolation_forest')
            for field in ('baseline', 'combined', 'added', 'removed', 'deferred_rule_alerts', 'rule_groups'):
                self.assertEqual(plan1[field], plan2[field])

            # Scope rules (D1-D6, F4) cannot appear as row alerts, nor B5/E4 carry points.
            bad_scope = deepcopy(self.analyses['C001'])
            d1_entry = next(e for e in bad_scope['rows'][0]['rule_coverage']['rules'] if e['rule_id'] == 'D1')
            d1_entry['status'] = 'evaluated_hit'
            with self.assertRaises(ValueError):
                make_rule35_plan(bad_scope, cases, self.eval_manifest['C001'], ml_method='isolation_forest')

            bad_master = deepcopy(self.analyses['C001'])
            b5_entry = next(e for e in bad_master['rows'][0]['rule_coverage']['rules'] if e['rule_id'] == 'B5')
            b5_entry['score'] = 5
            with self.assertRaises(ValueError):
                make_rule35_plan(bad_master, cases, self.eval_manifest['C001'], ml_method='isolation_forest')

    def test_03_simultaneous_group_deferral_and_budget_full_behavior(self):
        with tempfile.TemporaryDirectory() as td:
            reviews = ReviewStore(Path(td) / 'reviews.sqlite3', self.review_key)
            scope = self._scope('C001')
            cases = rule35_cases_for(self.snapshots, scope, self.analyses['C001'], reviews, raw_data=self.eval_data['C001'])

            # Construct synthetic analysis with 4 early single hits + 1 simultaneous 2-tx P1 batch group later -> whole group deferred.
            syn = deepcopy(self.analyses['C001'])
            syn['catalogue_results'] = [c for c in syn['catalogue_results'] if c['rule_id'] != 'P1']
            syn['catalogue_results'].append(dict(
                rule_id='P1',
                groups=[dict(
                    event_id='BE_SIM_DEFER',
                    status='evaluated',
                    signal=True,
                    points=20,
                    hard_trigger=1,
                    suppressed_reason='',
                    transaction_ids=['C1_EV_15_NORM', 'C1_EV_16_NORM'],
                )],
            ))
            # Clear P1/C2 on early rows, mark 4 specific single hits on EV_09..EV_12.
            early_singles = {'C1_EV_09_NORM', 'C1_EV_10_NORM', 'C1_EV_11_NORM', 'C1_EV_12_NORM'}
            for r in syn['rows']:
                for re in r['rule_coverage']['rules']:
                    if re['rule_id'] not in ('D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'F4', 'B5', 'E4', 'E3'):
                        if re['status'] == 'evaluated_hit':
                            re.update(status='evaluated_no_hit', matched=False, score=0, hits=[])
                        if r['transaction_id'] in early_singles and re['rule_id'] == 'C2':
                            re.update(status='evaluated_hit', matched=True, score=20,
                                      hits=[dict(rule_id='C2', points=20, hard_trigger=1, scoring_role='transaction')])
            # Ensure EV_15/EV_16 sort AFTER EV_09..EV_12 by keeping their original event_at (earlier/later order).
            plan_defer = make_rule35_plan(syn, cases, self.eval_manifest['C001'], ml_method='isolation_forest')
            self.assertEqual([k[0] for k in plan_defer['baseline']], sorted(early_singles))
            self.assertEqual([k[0] for k in plan_defer['deferred_rule_alerts']], ['C1_EV_15_NORM', 'C1_EV_16_NORM'])
            self.assertEqual(len(plan_defer['added']), 1)
            self.assertEqual(len(plan_defer['combined']), BUDGET)

            # Now test exact 5-hit saturated budget -> ML adds 0 with explicit budget_full_no_slots message.
            five_hits = deepcopy(syn)
            five_hits['catalogue_results'] = [c for c in five_hits['catalogue_results'] if c['rule_id'] != 'P1']
            for r in five_hits['rows']:
                if r['transaction_id'] == 'C1_EV_13_NORM':
                    c2_e = next(e for e in r['rule_coverage']['rules'] if e['rule_id'] == 'C2')
                    c2_e.update(status='evaluated_hit', matched=True, score=20,
                                hits=[dict(rule_id='C2', points=20, hard_trigger=1, scoring_role='transaction')])
            plan_full = make_rule35_plan(five_hits, cases, self.eval_manifest['C001'], ml_method='isolation_forest')
            self.assertEqual(len(plan_full['baseline']), 5)
            self.assertEqual(plan_full['added'], [])
            self.assertEqual(plan_full['combined'], plan_full['baseline'])
            self.assertEqual(plan_full['ml_addition_status'], 'budget_full_no_slots')
            self.assertIn('không còn chỗ trong ngân sách', plan_full['ml_addition_note'].lower())

    def test_04_missing_source_gap_and_ml_unavailable_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            reviews = ReviewStore(Path(td) / 'reviews.sqlite3', self.review_key)
            scope = self._scope('C001')

            # Variant with missing recipient_bank_code -> A1/A2/A3/B1 unavailable; ML additions labeled partial_rule_source_gap.
            gap_data = deepcopy(self.eval_data['C001'])
            for tx in gap_data['source']['tables']['transactions']:
                if tx['transaction_id'] == 'C1_EV_08_ML_SECOND':
                    tx['recipient_bank_code'] = ''
            _rehash(gap_data)
            gap_snap = _commit(self.snapshots, scope, gap_data, 'c001-gap-eval')
            gap_ana = analyze_rule_snapshot(self.snapshots, scope, gap_snap['snapshot_id'], EVAL_AS_OF,
                                            technical=True, resources=self.resources)
            gap_cases = rule35_cases_for(self.snapshots, scope, gap_ana, reviews, raw_data=gap_data)
            gap_plan = make_rule35_plan(gap_ana, gap_cases, gap_snap, ml_method='isolation_forest', raw_data=gap_data)
            gap_report = rule35_report_for(gap_plan, gap_cases)
            # Per-transaction rule availability (native_rule_node): only C1_EV_08_ML_SECOND lacks recipient_bank_code -> B1 unavailable on it alone.
            self.assertEqual(gap_report['ml_addition_summary']['added_with_partial_rule_source_gap'], 1)
            self.assertEqual(gap_report['ml_addition_summary']['added_after_all_applicable_rules_no_hit'], 1)
            by_added_id = {item['record_id']: item for item in gap_report['added']}
            self.assertIn('B1', by_added_id['C1_EV_08_ML_SECOND']['unavailable_rule_ids'])
            self.assertEqual(by_added_id['C1_EV_07_ML_CLEAN']['unavailable_rule_ids'], [])

            # Variant with ML unpinned (AnalysisResources()) -> ml_unavailable keeps baseline rules intact.
            no_ml_ana = analyze_rule_snapshot(self.snapshots, scope, self.eval_manifest['C001']['snapshot_id'], EVAL_AS_OF,
                                              technical=True, resources=AnalysisResources())
            no_ml_cases = rule35_cases_for(self.snapshots, scope, no_ml_ana, reviews, raw_data=self.eval_data['C001'])
            no_ml_plan = make_rule35_plan(no_ml_ana, no_ml_cases, self.eval_manifest['C001'], ml_method='isolation_forest')
            self.assertEqual(no_ml_plan['ml_addition_status'], 'ml_unavailable')
            self.assertEqual(no_ml_plan['added'], [])
            self.assertEqual(no_ml_plan['combined'], no_ml_plan['baseline'])

    def test_05_store_restart_immutability_feedback_metric_update_and_http_api(self):
        with tempfile.TemporaryDirectory() as td:
            rev_path = Path(td) / 'reviews.sqlite3'
            cmp_path = Path(td) / 'comparisons.sqlite3'
            reviews = ReviewStore(rev_path, self.review_key)
            comparisons = ComparisonStore(cmp_path, self.cmp_key)

            scope_c1 = self._scope('C001')
            scope_c2 = self._scope('C002')
            c1_cases = rule35_cases_for(self.snapshots, scope_c1, self.analyses['C001'], reviews, raw_data=self.eval_data['C001'])
            c2_cases = rule35_cases_for(self.snapshots, scope_c2, self.analyses['C002'], reviews, raw_data=self.eval_data['C002'])

            # Verify SHARED_AUDIT_00 case_id isolation between C001 & C002.
            c1_shared = next(c for c in c1_cases if c['record_id'] == 'SHARED_AUDIT_00')
            c2_shared = next(c for c in c2_cases if c['record_id'] == 'SHARED_AUDIT_00')
            self.assertNotEqual(c1_shared['case_id'], c2_shared['case_id'])

            plan_c1 = make_rule35_plan(self.analyses['C001'], c1_cases, self.eval_manifest['C001'], ml_method='isolation_forest')
            saved = comparisons.put(scope_c1, plan_c1)

            # Simulated process restart: re-open ComparisonStore & ReviewStore from disk.
            restarted_cmp = ComparisonStore(cmp_path, self.cmp_key)
            reloaded = restarted_cmp.get(scope_c1, self.analyses['C001']['analysis_id'])
            self.assertEqual(reloaded['plan_sha256'], saved['plan_sha256'])
            # Cross-company read via C002 returns None (scoped isolation).
            self.assertIsNone(restarted_cmp.get(scope_c2, self.analyses['C001']['analysis_id']))

            # Conflicting plan tamper is rejected with 409 COMPARISON_PLAN_CONFLICT.
            altered = deepcopy(plan_c1)
            altered['added'] = []
            with self.assertRaises(ImportFailure) as conflict:
                restarted_cmp.put(scope_c1, altered)
            self.assertEqual(conflict.exception.status, 409)

            # Save human review feedback on one ML-added case -> updates metrics without changing plan selection or hash.
            added_key = tuple(plan_c1['added'][0])
            added_case = next(c for c in c1_cases if (c['record_id'], c['revision']) == added_key)
            lease = reviews.start(scope_c1, added_case['case_id'])['lease']
            reviews.save(
                scope_c1, added_case['case_id'], 0,
                dict(
                    outcome='confirmed_risk',
                    usefulness='yes',
                    explanation='Manual invoice check found missing support docs and ledger mismatch.',
                    action='Request original supporting invoice before settlement.',
                    missing_materials='',
                    evidence_ids=[added_case['evidence'][0]['evidence_id']],
                    checks_completed=True,
                ),
                [e['evidence_id'] for e in added_case['evidence']],
                lease,
                'review-save-1',
            )
            updated_cases = rule35_cases_for(self.snapshots, scope_c1, self.analyses['C001'], reviews, raw_data=self.eval_data['C001'])
            updated_report = rule35_report_for(reloaded['plan'], updated_cases, redaction='technical')
            self.assertEqual(updated_report['combined']['metrics']['reviewed'], 1)
            self.assertEqual(updated_report['combined']['metrics']['declared_problem_transactions'], 1)
            self.assertEqual(updated_report['added'][0]['usefulness'], 'yes')
            self.assertEqual([tuple(x) for x in reloaded['plan']['added']], [tuple(x) for x in plan_c1['added']])

            # Real HTTP endpoint check (/analyses/<ana_...>/comparison) via make_server.
            server = make_server(
                port=0, authorizer=self.auth, snapshot_store=self.snapshots,
                analysis_resources=self.resources, review_store=reviews, comparison_store=restarted_cmp,
            )
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            try:
                port = server.server_port
                def req(method, path, body=None, token=self.token):
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                    headers = {'Authorization': 'Bearer ' + token} if token else {}
                    payload = None
                    if body is not None:
                        payload = json.dumps(body).encode()
                        headers['Content-Type'] = 'application/json'
                    conn.request(method, path, payload, headers)
                    resp = conn.getresponse()
                    raw = resp.read().decode('utf-8')
                    conn.close()
                    return resp.status, json.loads(raw)

                ana_c2 = self.analyses['C002']['analysis_id']
                url_c2 = f'/api/v1/companies/C002/analyses/{ana_c2}/comparison'
                self.assertEqual(req('GET', url_c2)[0], 404)
                st, r_post = req('POST', url_c2, dict(
                    policy=POLICY, budget=BUDGET,
                    snapshot_id=self.eval_manifest['C002']['snapshot_id'], as_of=EVAL_AS_OF, ml_method='ecod',
                ))
                self.assertEqual(st, 200, r_post)
                self.assertNotIn('raw_score', json.dumps(r_post))
                self.assertNotIn('artifact_id', json.dumps(r_post))
                st_get, r_get = req('GET', url_c2)
                self.assertEqual(st_get, 200, r_get)
                self.assertEqual(r_get['plan_sha256'], r_post['plan_sha256'])
                # Non-director reader cannot read technical comparison creation/details.
                self.assertEqual(req('GET', url_c2, token=self.reader_token)[0], 403)
                # Cross-company access fails cleanly.
                self.assertEqual(req('GET', f'/api/v1/companies/C001/analyses/{ana_c2}/comparison')[0], 404)
                # Invalid policy/budget rejected with 400.
                self.assertEqual(req('POST', url_c2, dict(policy='weighted', budget=5, snapshot_id=self.eval_manifest['C002']['snapshot_id'], as_of=EVAL_AS_OF))[0], 400)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
