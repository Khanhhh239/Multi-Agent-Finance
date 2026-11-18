"""Coordinator, HTTP recovery, Portal/API & RBAC tests for `agent2-rule-snapshot/1.0.0`."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'tests') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tests'))
if str(ROOT / 'tests_he') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tests_he'))

import test_he4_rule_snapshot_p1 as tp
from experiments.he4 import c3_circuit, circuits
from experiments.he4.coordinator import FourJobs, Settings, wire
from experiments.he4.rule_snapshot_coordinator import RULE_SNAPSHOT_RESULT_VERSION
from experiments.he4.web import FourWorkbench
from experiments.he_inference.enterprise_server import EnterpriseNode
from experiments.he_inference.http_common import ServiceError
from experiments.he_inference.key_manager import create_key
from experiments.he_inference.protocol import public_hex, sha, sign
from sme_fraud import rule_snapshot as rs
from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDING_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.he_workbench import HEWorkbench
from sme_fraud.import_files import canonical, digest
from sme_fraud.method_store import MethodStore
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields
from test_validation_backend import policy_for

BUILDS = Path(r'D:\agent22\.runtime\he4')
BUILD_PATHS = {
    'rules': str(BUILDS / 'build-rules-difference-v1'),
    'c3': str(BUILDS / 'build-c3-v1'),
    'graph': str(BUILDS / 'build-graph-difference-v1'),
    'statistics': str(BUILDS / 'build-statistics-v1'),
}


def _eval_plain(profile: str, values: list):
    arrs = [np.asarray(v, dtype=np.int64) for v in values]
    if profile == 'rules':
        return circuits.p1(*arrs).tolist()
    if profile == 'c3':
        return c3_circuit.c3(*arrs).tolist()
    if profile == 'graph':
        return circuits.graph(*arrs).tolist()
    if profile == 'statistics':
        return int(circuits.robust_z(*arrs))
    raise ValueError(profile)


def _manifest_sha(profile: str) -> str:
    return json.loads((Path(BUILD_PATHS[profile]) / 'manifest.json').read_bytes())['files']['server.zip']


def _multi_company_snapshot(company: str, positive: bool) -> dict:
    c = tp.Case()
    c.at = datetime(2025, 8, 12, 11, 0, tzinfo=timezone(timedelta(hours=7)))
    c.tables['employees'] = [c.director, c.maker, c.worker]
    c.tables['customers'] = c.tables['customers'][:1]
    c.tables['entity_links'] = []
    c.tables['attendance'] = [
        r
        for r in c.tables['attendance']
        if r['employee_id'] == c.worker['employee_id'] and r['payroll_period'] == '2025-08'
    ][:1]
    c.tables['vendor_status_history'] = [
        r for r in c.tables['vendor_status_history'] if r['vendor_id'] == c.vendor['vendor_id']
    ]
    for i, emp in enumerate(c.tables['employees']):
        emp.update(
            bank_account=f'SIM_STAFF_{i}',
            bank_code='SIMBANK',
            phone=f'090100000{i}',
            address=f'SIM_STAFF_ADDRESS_{i}',
            national_id=f'07909900010{i}',
        )
    c.vendor.update(
        name='Orchid marine instruments',
        bank_account='SIM_VENDOR',
        bank_code='SIMBANK',
        phone='0902000000',
        address='SIM_VENDOR_ADDRESS',
        national_id='079088000111',
    )
    v2 = deepcopy(c.vendor)
    v2['vendor_id'] = 'SIM_VENDOR_2'
    v2['name'] = 'Second Supplier Co'
    if positive:
        v2['phone'] = c.vendor['phone']
        v2['bank_account'] = '88889999000'
        v2['address'] = 'OTHER STREET 99'
        v2['national_id'] = '079088000222'
        c.vendor['national_id'] = c.worker['national_id']
    else:
        v2['phone'] = '0909888777'
        v2['bank_account'] = '77776666555'
        v2['address'] = 'DISTINCT AVE 22'
        v2['national_id'] = '079088000333'
    c.tables['vendors'] = [c.vendor, v2]

    prior = c.pay(c.at - timedelta(days=1), 6_000_000, invoice_number='INV_MULTI', invoice_gross_vnd=10_000_000)
    prior['transaction_id'] = f'PRIOR_{company}'
    prior['created_at'] = (c.at - timedelta(days=1, minutes=5)).isoformat()
    prior['approved_at'] = (c.at - timedelta(days=1)).isoformat()

    target_amt = 6_000_000 if positive else 2_000_000
    target = c.pay(
        c.at - timedelta(minutes=10),
        target_amt,
        invoice_number='INV_MULTI',
        invoice_gross_vnd=10_000_000,
    )
    target['transaction_id'] = 'AUDIT_0000'
    if positive:
        target['created_at'] = (c.at - timedelta(minutes=10, seconds=15)).isoformat()
        target['approved_at'] = (c.at - timedelta(minutes=10)).isoformat()
        target['recipient_account'] = c.worker['bank_account']
        target['recipient_bank_code'] = c.worker['bank_code']
    else:
        target['created_at'] = (c.at - timedelta(minutes=20)).isoformat()
        target['approved_at'] = (c.at - timedelta(minutes=10)).isoformat()

    payroll = c.pay(c.at - timedelta(minutes=15), 9_000_000, kind='payroll')
    payroll['transaction_id'] = f'PAYROLL_{company}'
    payroll['employee_id'] = c.worker['employee_id']
    payroll['payroll_period'] = '2025-08'
    payroll['recipient_account'] = c.worker['bank_account']
    payroll['recipient_bank_code'] = c.worker['bank_code']
    payroll['created_at'] = (c.at - timedelta(minutes=25)).isoformat()
    payroll['approved_at'] = (c.at - timedelta(minutes=15)).isoformat()

    future_ts = (c.at + timedelta(hours=2)).isoformat()
    future = c.pay(c.at + timedelta(hours=2), target_amt, invoice_number='INV_MULTI', invoice_gross_vnd=10_000_000)
    future['transaction_id'] = f'FUTURE_{company}'
    future['posted_at'] = future_ts
    future['observed_at'] = future_ts
    future['created_at'] = (c.at - timedelta(minutes=5)).isoformat()
    future['approved_at'] = future_ts

    # Keep c.rows aligned with c.tables['transactions'] before finish() runs enrich_accounting.
    c.rows = [prior, target, payroll, future]
    c.tables['transactions'] = c.rows
    tp.authorities(c)
    src = tp.finish(c, company)
    # Keep source as_of at c.at while future tx carries a +2h observed/posted timestamp.
    src['tenant_id'] = 'demo'
    src['as_of'] = c.at.isoformat()
    for cov in src['coverage'].values():
        cov['observed_at'] = src['as_of']
        cov['covered_through'] = src['as_of']
    tp._rehash(src)
    return tp._wrap(src, ['AUDIT_0000', payroll['transaction_id'], future['transaction_id']])


class _SyntheticBridge:
    """Fast deterministic bridge keeping real key-epoch, digest, and circuit semantics."""

    def __init__(self, fail_profile_key: str | None = None):
        self.calls = []
        self.fail_profile_key = fail_profile_key
        self.missing_profiles = set()

    def public_key(self, scope, bundle_path):
        profile = json.loads((Path(bundle_path) / 'manifest.json').read_bytes())['profile']
        p = Path(bundle_path)
        return p / 'client.specs.json'

    def encrypt(self, scope, bundle_path, values, output, *, recover_uncommitted=False):
        manifest = json.loads((Path(bundle_path) / 'manifest.json').read_bytes())
        profile = manifest['profile']
        if profile in self.missing_profiles or (self.fail_profile_key and profile == self.fail_profile_key):
            from experiments.he_inference.protocol import HEUnavailable
            raise HEUnavailable('he4_key_not_provisioned')
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        arg_hashes = []
        for idx, v in enumerate(values):
            blob = canonical(v)
            (out_dir / f'argument-{idx}.cipher').write_bytes(blob)
            arg_hashes.append(sha(blob))
        self.calls.append(('encrypt', next(iter(scope.company_ids)), profile, out_dir.name))
        binding = dict(
            tenant_id=scope.tenant_id,
            company_id=next(iter(scope.company_ids)),
            profile=profile,
            circuit_sha256=manifest['files']['server.zip'],
            specs_sha256=manifest['files']['client.specs.json'],
        )
        return dict(
            binding=binding,
            key_epoch='key_' + hashlib.sha256((profile + binding['company_id']).encode()).hexdigest(),
            evaluation_keys_sha256=sha(Path(bundle_path, 'client.specs.json').read_bytes()),
            arguments_sha256=arg_hashes,
        )

    def decrypt(self, scope, bundle_path, cipher_path, cipher_sha256, output_path, context):
        manifest = json.loads((Path(bundle_path) / 'manifest.json').read_bytes())
        profile = manifest['profile']
        if sha(Path(cipher_path).read_bytes()) != cipher_sha256:
            from experiments.he_inference.protocol import HEUnavailable
            raise HEUnavailable('he4_response_integrity')
        self.calls.append(('decrypt', next(iter(scope.company_ids)), profile))
        return json.loads(Path(cipher_path).read_bytes().decode())


class RuleSnapshotCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.director_tok = secrets.token_urlsafe(32)
        self.acct_tok = secrets.token_urlsafe(32)
        policy = policy_for(self.director_tok)
        policy['principals'][0]['memberships'] = [
            dict(company_id=c, role='director', status='active', permissions=['data.import', 'model.fit'])
            for c in ('C001', 'C002')
        ]
        acct_principal = policy_for(self.acct_tok)['principals'][0]
        acct_principal['actor_id'] = 'acct_1'
        acct_principal['memberships'] = [
            dict(company_id='C001', role='accountant', status='active', permissions=['data.import']),
            dict(company_id='C002', role='accountant', status='active', permissions=['data.import']),
        ]
        policy['principals'].append(acct_principal)
        self.policy_path = self.root / 'policy.json'
        self.policy_path.write_bytes(canonical(policy))
        self.auth = FileAuthorizer(self.policy_path)

        self.snapshots = SnapshotStore(self.root / 'snapshots.sqlite3')
        self.models = MethodStore(self.root / 'models.sqlite3')

        self.sids = {}
        self.data = {}
        for company, pos in (('C001', True), ('C002', False)):
            sc = self.auth.authorize('Bearer ' + self.director_tok, company)
            doc = _multi_company_snapshot(company, pos)
            self.data[company] = doc
            self.sids[company] = tp._commit(self.snapshots, sc, doc, f'snap-{company}')

        self.state_key = self.root / 'state.key.json'
        create_key(self.state_key, purpose='state-wrapping')
        self.worker_key = Ed25519PrivateKey.generate()
        self.worker_hex = public_hex(self.worker_key)
        self.prov_key = Ed25519PrivateKey.generate()

        self.bindings_v4 = self.root / 'he4_bindings.json'
        self.bindings_v4.write_bytes(
            canonical(
                dict(
                    version='he4-company-bindings/1.0.0',
                    bindings=[
                        dict(tenant_id='demo', company_id=c, statistics_artifact_id=None)
                        for c in ('C001', 'C002')
                    ],
                )
            )
        )
        self.ui_bindings = self.root / 'ui_bindings.json'
        self.ui_bindings.write_bytes(canonical(dict(version='he-ui-bindings/1.0.0', bindings=[])))

        self.config_v1_1 = dict(
            version='he4-enterprise/1.1.0',
            state_dir=str(self.root / 'jobs'),
            enterprise_root=str(self.root / 'enterprise'),
            state_key_file=str(self.state_key),
            worker_url='http://127.0.0.1:18999',
            worker_verify_key=self.worker_hex,
            builds=dict(BUILD_PATHS),
            bindings_file=str(self.bindings_v4),
            linux_distro='Debian',
            linux_python='/home/sang/.local/share/agent2/he4/bin/python',
        )

    def _mock_worker_handlers(self):
        self.uploaded = {}
        self.sessions = {}
        self.worker_log = []
        self.paused_until = None
        self.lose_reply = False
        self.require_admit = False
        self.tamper_result = False
        parent = self

        def fake_upload(url, scope, prov_key, verify_key, path, kind):
            data = Path(path).read_bytes()
            h = sha(data)
            parent.uploaded[(scope.tenant_id, next(iter(scope.company_ids)), h)] = data
            return h

        def fake_download(url, scope, prov_key, digest_hex, out_path):
            data = parent.uploaded[(scope.tenant_id, next(iter(scope.company_ids)), digest_hex)]
            Path(out_path).write_bytes(data)

        def fake_post(url, route, payload, timeout=30):
            inner = payload['payload']
            if route == '/v1/readiness':
                resp_inner = dict(inner, worker_verify_key=parent.worker_hex)
                if inner.get('version') != 'he-worker-readiness/1.0.0':
                    resp_inner['builds'] = {k: _manifest_sha(k) for k in BUILD_PATHS}
                return sign(resp_inner, parent.worker_key)
            company = inner['company_id']
            tenant = inner['tenant_id']
            req_sha = sha(wire(payload))
            if route == '/v1/evaluate':
                parent.worker_log.append(('evaluate', inner['profile'], inner['session_id']))
                args = [json.loads(parent.uploaded[(tenant, company, h)].decode()) for h in inner['arguments_sha256']]
                res_bytes = canonical(_eval_plain(inner['profile'], args))
                res_sha = sha(res_bytes)
                parent.uploaded[(tenant, company, res_sha)] = res_bytes
                signed_res = sign(
                    dict(
                        version='he4-worker/0.1.0',
                        tenant_id=tenant,
                        company_id=company,
                        session_id=inner['session_id'],
                        nonce=inner['nonce'],
                        request_sha256=req_sha,
                        circuit_sha256=('0' * 64) if parent.tamper_result else inner['circuit_sha256'],
                        result_sha256=res_sha,
                    ),
                    parent.worker_key,
                )
                parent.sessions[(inner['session_id'], inner['nonce'])] = dict(
                    req=payload, req_sha=req_sha, signed=signed_res, admitted=not parent.require_admit
                )
                if parent.lose_reply:
                    raise ServiceError(503, 'WORKER_CONNECTION_UNAVAILABLE')
                return signed_res
            if route == '/v1/results':
                parent.worker_log.append(('results', inner['session_id']))
                entry = parent.sessions.get((inner['session_id'], inner['nonce']))
                if not entry or not entry['admitted']:
                    raise ServiceError(409, 'RESULT_NOT_READY')
                return entry['signed']
            if route == '/v1/resume':
                outer_req = inner['request']
                p = outer_req['payload']
                parent.worker_log.append(('resume', p['session_id']))
                if parent.require_admit:
                    raise ServiceError(409, 'HE4_REQUEST_NOT_ADMITTED')
                entry = parent.sessions[(p['session_id'], p['nonce'])]
                return entry['signed']
            if route == '/v1/admit':
                outer_req = inner['request']
                p = outer_req['payload']
                parent.worker_log.append(('admit', p['session_id']))
                entry = parent.sessions.get((p['session_id'], p['nonce']))
                if not entry:
                    args = [json.loads(parent.uploaded[(tenant, company, h)].decode()) for h in p['arguments_sha256']]
                    res_bytes = canonical(_eval_plain(p['profile'], args))
                    res_sha = sha(res_bytes)
                    parent.uploaded[(tenant, company, res_sha)] = res_bytes
                    entry = dict(
                        req=outer_req,
                        req_sha=sha(wire(outer_req)),
                        signed=sign(
                            dict(
                                version='he4-worker/0.1.0',
                                tenant_id=tenant,
                                company_id=company,
                                session_id=p['session_id'],
                                nonce=p['nonce'],
                                request_sha256=sha(wire(outer_req)),
                                circuit_sha256=p['circuit_sha256'],
                                result_sha256=res_sha,
                            ),
                            parent.worker_key,
                        ),
                    )
                    parent.sessions[(p['session_id'], p['nonce'])] = entry
                entry['admitted'] = True
                return entry['signed']
            raise AssertionError(f'unexpected route {route}')

        return fake_upload, fake_download, fake_post

    def test_v1_0_0_rejects_c3_and_rule_snapshot_while_v1_1_0_allows(self):
        cfg_v1 = dict(
            self.config_v1_1,
            version='he4-enterprise/1.0.0',
            builds={k: BUILD_PATHS[k] for k in ('rules', 'statistics', 'graph')},
        )
        # 1.0.0 Settings rejects 'c3'
        with self.assertRaises(ValueError):
            Settings(dict(cfg_v1, builds=BUILD_PATHS))
        # 1.1.0 Settings works with or without 'statistics'
        s1 = Settings(self.config_v1_1)
        self.assertTrue(s1.supports_rule_snapshot)
        s2 = Settings(dict(self.config_v1_1, builds={k: BUILD_PATHS[k] for k in ('rules', 'c3', 'graph')}))
        self.assertTrue(s2.supports_rule_snapshot)

        # Plain HEWorkbench (with an active UI binding) still rejects agent2-rule-snapshot/1.0.0 with 422 HE_PROFILE_UNSUPPORTED
        bound_ui = self.root / 'bound_ui_bindings.json'
        bound_ui.write_bytes(
            canonical(
                dict(
                    version='he-ui-bindings/1.0.0',
                    bindings=[dict(tenant_id='demo', company_id='C001', artifact_id='mth_' + ('a' * 64))],
                )
            )
        )
        node = EnterpriseNode(self.auth, self.models.path, self.snapshots.path, self.config_v1_1['worker_url'], self.worker_hex, self.prov_key)
        node.enable_jobs(self.root / 'legacy_jobs', self.state_key, required_provider='windows-dpapi-current-user')
        plain_wb = HEWorkbench(node, bound_ui)
        sc = self.auth.authorize('Bearer ' + self.director_tok, 'C001')
        from sme_fraud.import_files import ImportFailure
        with self.assertRaises(ImportFailure) as cm:
            plain_wb.submit(sc, lambda: sc, 'C001', 'Bearer ' + self.director_tok, 'req-12345678', dict(snapshot_id=self.sids['C001']))
        node.jobs.close()
        self.assertEqual(cm.exception.code, 'HE_PROFILE_UNSUPPORTED')

        # 1.0.0 FourWorkbench rejects rule-snapshot with 422 HE_PROFILE_UNSUPPORTED
        node1 = EnterpriseNode(self.auth, self.models.path, self.snapshots.path, self.config_v1_1['worker_url'], self.worker_hex, self.prov_key)
        node1.enable_jobs(self.root / 'legacy_jobs_1', self.state_key, required_provider='windows-dpapi-current-user')
        wb1 = FourWorkbench(node1, self.ui_bindings, cfg_v1)
        node1.jobs.close()
        with self.assertRaises(ImportFailure) as cm2:
            wb1.submit(sc, lambda: sc, 'C001', 'Bearer ' + self.director_tok, 'req-12345678', dict(snapshot_id=self.sids['C001']))
        self.assertEqual(cm2.exception.code, 'HE_PROFILE_UNSUPPORTED')

    def test_staged_order_provenance_parity_and_portal_apis(self):
        fake_up, fake_dl, fake_post = self._mock_worker_handlers()
        bridge = _SyntheticBridge()

        node = EnterpriseNode(self.auth, self.models.path, self.snapshots.path, self.config_v1_1['worker_url'], self.worker_hex, self.prov_key)
        node.enable_jobs(self.root / 'legacy_jobs', self.state_key, required_provider='windows-dpapi-current-user')
        with (
            patch('experiments.he4.coordinator.upload', side_effect=fake_up),
            patch('experiments.he4.coordinator.download', side_effect=fake_dl),
            patch('experiments.he4.coordinator.post', side_effect=fake_post),
            patch('experiments.he4.web.post', side_effect=fake_post),
            patch('experiments.he_inference.readiness.post', side_effect=fake_post),
        ):
            wb = FourWorkbench(node, self.ui_bindings, self.config_v1_1)
            # Replace FourJobs with workers=1 and synthetic bridge
            node.jobs.close()
            node.jobs = FourJobs(node, wb.settings, workers=0, bridge=bridge)
            srv = make_server(0, self.auth, self.snapshots, AnalysisResources(self.models.path, self.ui_bindings), he_backend=wb)
            thread = threading.Thread(target=srv.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(lambda: (srv.shutdown(), srv.server_close(), node.jobs.close()))

            def req(path, body=None, token=None, headers=None):
                tok = token or self.director_tok
                hdrs = {'Authorization': f'Bearer {tok}'}
                if body is not None:
                    hdrs['Content-Type'] = 'application/json'
                if headers:
                    hdrs.update(headers)
                with closing(http.client.HTTPConnection('127.0.0.1', srv.server_address[1], timeout=10)) as conn:
                    conn.request('POST' if body is not None else 'GET', path, None if body is None else json.dumps(body).encode(), hdrs)
                    resp = conn.getresponse()
                    raw = resp.read()
                    ct = resp.getheader('Content-Type') or ''
                    return resp.status, json.loads(raw) if 'json' in ct else raw

            # 1. datasets() includes agent2-rule-snapshot/1.0.0 for C001 and C002
            st, ds1 = req('/api/v1/companies/C001/he/datasets')
            self.assertEqual(st, 200, ds1)
            self.assertTrue(ds1['available'])
            self.assertTrue(ds1['rule_snapshot_he_supported'])
            self.assertIn(self.sids['C001'], [d['snapshot_id'] for d in ds1['datasets']])
            self.assertNotIn(self.sids['C002'], json.dumps(ds1))

            # 2. Wrong as_of rejected on FourJobs.submit directly
            with self.assertRaises(ServiceError) as err_asof:
                node.jobs.submit('C001', 'Bearer ' + self.director_tok, 'bad-asof-key-1234', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of='2025-08-12T12:00:00+07:00'))
            self.assertEqual(err_asof.exception.code, 'HE4_AS_OF_MISMATCH')

            # 3. Submit via Portal route for BOTH C001 and C002 with shared AUDIT_0000
            jobs = {}
            for company in ('C001', 'C002'):
                st, job = req(f'/api/v1/companies/{company}/he/jobs', body=dict(snapshot_id=self.sids[company]), headers={'Idempotency-Key': f'run-{company}-0001'})
                self.assertEqual(st, 202, job)
                jobs[company] = job['job_id']
                sc = self.auth.authorize('Bearer ' + self.director_tok, company)
                while node.jobs._process(sc, jobs[company]):
                    pass

            # Check staged order on C001 evaluate calls: rules -> c3 -> graph
            c1_profiles = [ev[1] for ev in self.worker_log[:]]
            r_idxs = [i for i, p in enumerate(c1_profiles) if p == 'rules']
            c_idxs = [i for i, p in enumerate(c1_profiles) if p == 'c3']
            g_idxs = [i for i, p in enumerate(c1_profiles) if p == 'graph']
            self.assertTrue(r_idxs and c_idxs and g_idxs)

            # 4. Director result vs Accountant masked result & native 3-way parity on C001
            st, res_c1_dir = req(f"/api/v1/companies/C001/he/jobs/{jobs['C001']}/result")
            self.assertEqual(st, 200)
            self.assertEqual(res_c1_dir['version'], RULE_SNAPSHOT_RESULT_VERSION)
            self.assertFalse(res_c1_dir['aggregation']['available'])
            self.assertEqual(res_c1_dir['provenance']['covered_rule_count'], 5)
            self.assertEqual(res_c1_dir['provenance']['total_rule_count'], 35)
            self.assertIn('plan_sha256', res_c1_dir)
            self.assertEqual(set(res_c1_dir['provenance']['evaluation_keys_sha256_by_profile']), {'rules', 'c3', 'graph'})

            # Actor isolation: accountant cannot read director's job directly
            self.assertEqual(req(f"/api/v1/companies/C001/he/jobs/{jobs['C001']}/result", token=self.acct_tok)[0], 404)

            # Accountant submits own run and sees masked result (no plan_sha256/evaluation_keys_sha256)
            st_aj, job_acct = req(
                '/api/v1/companies/C001/he/jobs',
                body=dict(snapshot_id=self.sids['C001']),
                token=self.acct_tok,
                headers={'Idempotency-Key': 'run-acct-c1-0001'},
            )
            self.assertEqual(st_aj, 202, job_acct)
            sc_acct = self.auth.authorize('Bearer ' + self.acct_tok, 'C001')
            while node.jobs._process(sc_acct, job_acct['job_id']):
                pass
            st, res_c1_acct = req(f"/api/v1/companies/C001/he/jobs/{job_acct['job_id']}/result", token=self.acct_tok)
            self.assertEqual(st, 200, res_c1_acct)
            self.assertNotIn('plan_sha256', json.dumps(res_c1_acct))
            self.assertIsInstance(res_c1_acct['rows'][0]['amount_vnd'], str)

            # Verify all 3 candidates kept + outcomes match native rule_snapshot.analyze
            native_c1 = rs.analyze(self.snapshots, self.auth.authorize('Bearer ' + self.director_tok, 'C001'), self.sids['C001'], self.data['C001']['source']['as_of'], technical=True)
            rows_c1 = {r['record_id']: r for r in res_c1_dir['rows']}
            self.assertEqual(list(rows_c1.keys()), ['AUDIT_0000', 'PAYROLL_C001', 'FUTURE_C001'])

            audit_c1 = rows_c1['AUDIT_0000']
            for gk in ('p1', 'c3', 'b1', 'b5_e4'):
                self.assertTrue(audit_c1['groups'][gk]['available'], gk)
                self.assertTrue(audit_c1['groups'][gk]['matched'], gk)
            self.assertEqual(audit_c1['branches']['statistics']['status'], 'unavailable')
            self.assertEqual(audit_c1['branches']['statistics']['reason'], 'rule_snapshot_he_unsupported')
            self.assertEqual(audit_c1['branches']['ml']['status'], 'unavailable')
            self.assertEqual(audit_c1['branches']['ml']['reason'], 'rule_snapshot_he_unsupported')

            pay_c1 = rows_c1['PAYROLL_C001']
            self.assertEqual(pay_c1['groups']['p1']['status'], 'not_applicable')
            self.assertFalse(pay_c1['groups']['c3']['matched'])
            self.assertFalse(pay_c1['groups']['b1']['matched'])

            fut_c1 = rows_c1['FUTURE_C001']
            self.assertFalse(fut_c1['available'])
            self.assertEqual(fut_c1['reason'], 'transaction_not_known_at_cutoff')
            for gk in ('p1', 'c3', 'b1', 'b5_e4'):
                self.assertEqual(fut_c1['groups'][gk]['status'], 'unavailable')

            # Cross-check exact native status/matched for AUDIT_0000
            nat_audit = {r['rule_id']: r for r in native_c1['rows'][0]['rule_coverage']['rules']}
            self.assertEqual(audit_c1['groups']['p1']['matched'], nat_audit['P1']['matched'])
            self.assertEqual(audit_c1['groups']['c3']['matched'], nat_audit['C3']['matched'])
            self.assertEqual(audit_c1['groups']['b1']['matched'], nat_audit['B1']['matched'])
            self.assertEqual(audit_c1['groups']['b5_e4']['matched'], nat_audit['B5']['matched'])

            # 5. C002 shared AUDIT_0000 is clean negative & completely isolated from C001
            st, res_c2 = req(f"/api/v1/companies/C002/he/jobs/{jobs['C002']}/result")
            self.assertEqual(st, 200)
            audit_c2 = {r['record_id']: r for r in res_c2['rows']}['AUDIT_0000']
            for gk in ('p1', 'c3', 'b1', 'b5_e4'):
                self.assertFalse(audit_c2['groups'][gk]['matched'], gk)
            self.assertEqual(req(f"/api/v1/companies/C002/he/jobs/{jobs['C001']}/result")[0], 404)

            # 6. Review & Workspace API end-to-end (including start/save review and CSV export) on accountant's own run
            st, ws = req(f"/api/v1/companies/C001/workspace/runs/{job_acct['job_id']}", token=self.acct_tok)
            self.assertEqual(st, 200, ws)
            self.assertEqual(ws['row_count'], 3)
            self.assertEqual([c['record_id'] for c in ws['cases']], ['AUDIT_0000', 'PAYROLL_C001', 'FUTURE_C001'])
            case0 = ws['cases'][0]
            self.assertEqual(len(case0['checks']), 6)
            self.assertTrue(case0['payment_signal'])
            prefix = f"/api/v1/companies/C001/he/jobs/{job_acct['job_id']}/reviews/{case0['case_id']}"
            st, started = req(prefix + '/start', body={}, token=self.acct_tok)
            self.assertEqual(st, 200)
            st, saved = req(
                prefix + '/save',
                body=dict(
                    lease=started['lease'],
                    expected_revision=0,
                    request_id='save-c1-001',
                    feedback=dict(
                        outcome='confirmed_risk',
                        usefulness='yes',
                        explanation='Đã đối chiếu đủ chứng từ P1/C3/B1/B5.',
                        action='Tạm giữ chi',
                        missing_materials='',
                        evidence_ids=[case0['evidence'][0]['evidence_id']],
                        checks_completed=True,
                    ),
                ),
                token=self.acct_tok,
            )
            self.assertEqual(st, 200, saved)
            st, csv_bytes = req(f"/api/v1/companies/C001/workspace/runs/{job_acct['job_id']}/report.csv", token=self.acct_tok)
            self.assertEqual(st, 200)
            self.assertTrue(csv_bytes.startswith(b'\xef\xbb\xbf'))
            self.assertIn(b'AUDIT_0000', csv_bytes)

    def test_recovery_r1_r2_r3_r4_tamper_partial_key_and_config_change(self):
        fake_up, fake_dl, fake_post = self._mock_worker_handlers()
        bridge = _SyntheticBridge()
        node = EnterpriseNode(self.auth, self.models.path, self.snapshots.path, self.config_v1_1['worker_url'], self.worker_hex, self.prov_key)
        node.enable_jobs(self.root / 'legacy_jobs', self.state_key, required_provider='windows-dpapi-current-user')

        with (
            patch('experiments.he4.coordinator.upload', side_effect=fake_up),
            patch('experiments.he4.coordinator.download', side_effect=fake_dl),
            patch('experiments.he4.coordinator.post', side_effect=fake_post),
        ):
            legacy_jobs = node.jobs
            self.addCleanup(legacy_jobs.close)
            jobs = FourJobs(node, Settings(self.config_v1_1), workers=0, bridge=bridge)
            node.jobs = jobs
            self.addCleanup(jobs.close)
            sc = self.auth.authorize('Bearer ' + self.director_tok, 'C001')

            # R2 Lost reply -> restart /v1/results recovers cached without re-encrypting
            self.lose_reply = True
            st = jobs.submit('C001', 'Bearer ' + self.director_tok, 'recover-r2-0001', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of=self.data['C001']['source']['as_of']))
            jid = st['job_id']
            # Idempotent resubmit returns SAME job_id
            st2 = jobs.submit('C001', 'Bearer ' + self.director_tok, 'recover-r2-0001', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of=self.data['C001']['source']['as_of']))
            self.assertEqual(st2['job_id'], jid)

            self.assertTrue(jobs._process(sc, jid))  # retryable after first task lost reply
            enc_count_before = sum(1 for c in bridge.calls if c[0] == 'encrypt')
            self.lose_reply = False
            while jobs._process(sc, jid):
                pass
            enc_count_after = sum(1 for c in bridge.calls if c[0] == 'encrypt')
            # Wait: task 0 did NOT re-encrypt; remaining tasks 1..N encrypted once each
            self.assertTrue(any(ev[0] == 'results' for ev in self.worker_log))
            self.assertEqual(jobs.result('C001', 'Bearer ' + self.director_tok, jid)[0], 200)
            self.assertGreaterEqual(enc_count_after, enc_count_before)

            # R3 7h pause -> /v1/resume blocked -> /v1/admit succeeds with same nonce
            self.sessions.clear()
            self.worker_log.clear()
            self.lose_reply = True
            self.require_admit = True
            st_r3 = jobs.submit('C001', 'Bearer ' + self.director_tok, 'recover-r3-0001', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of=self.data['C001']['source']['as_of']))
            jid3 = st_r3['job_id']
            self.assertTrue(jobs._process(sc, jid3))
            self.lose_reply = False
            while jobs._process(sc, jid3):
                pass
            self.assertTrue(any(ev[0] == 'admit' for ev in self.worker_log))
            self.assertEqual(jobs.result('C001', 'Bearer ' + self.director_tok, jid3)[0], 200)

            # Response tamper rejected BEFORE decrypt
            self.require_admit = False
            self.tamper_result = True
            st_bad = jobs.submit('C001', 'Bearer ' + self.director_tok, 'tamper-0001', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of=self.data['C001']['source']['as_of']))
            self.assertFalse(jobs._process(sc, st_bad['job_id']))
            self.assertEqual(jobs.status('C001', 'Bearer ' + self.director_tok, st_bad['job_id'])['reason'], 'he4_response_binding')
            self.tamper_result = False

            # Partial missing key (`he4_key_not_provisioned` on `c3` only) isolates C3 while P1/B1/B5 finish
            bridge.missing_profiles.add('c3')
            st_pk = jobs.submit('C001', 'Bearer ' + self.director_tok, 'partial-key-0001', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of=self.data['C001']['source']['as_of']))
            while jobs._process(sc, st_pk['job_id']):
                pass
            _, pk_res = jobs.result('C001', 'Bearer ' + self.director_tok, st_pk['job_id'])
            audit_pk = pk_res['rows'][0]
            self.assertTrue(audit_pk['groups']['p1']['available'])
            self.assertFalse(audit_pk['groups']['c3']['available'])
            self.assertEqual(audit_pk['groups']['c3']['reason'], 'he4_key_not_provisioned')
            self.assertTrue(audit_pk['groups']['b1']['available'])
            bridge.missing_profiles.clear()

            # Build / config change refuses resume mid-flight
            self.lose_reply = True
            st_cfg = jobs.submit('C001', 'Bearer ' + self.director_tok, 'cfg-change-0001', dict(artifact_id=None, snapshot_id=self.sids['C001'], as_of=self.data['C001']['source']['as_of']))
            self.assertTrue(jobs._process(sc, st_cfg['job_id']))
            jobs.settings.config['builds'] = {k: BUILD_PATHS[k] for k in ('rules', 'c3', 'graph')}
            self.lose_reply = False
            self.assertFalse(jobs._process(sc, st_cfg['job_id']))
            self.assertEqual(jobs.status('C001', 'Bearer ' + self.director_tok, st_cfg['job_id'])['reason'], 'he4_configuration_changed')

    def test_limits_and_missing_sources_stay_unavailable_through_portal(self):
        # 1. Domain/circuit limits (>4 C3 authority rules + >4 B1 graph entities) & B1 missing bank_code -> unavailable
        c = tp.Case()
        c.at = datetime(2025, 8, 12, 11, 0, tzinfo=timezone(timedelta(hours=7)))
        extra_staff = c.g.employee('C001', c.at - timedelta(days=30), role='operations')
        c.tables['employees'] = [c.director, c.maker, c.worker, extra_staff]  # 4 staff + 1 vendor = 5 entities (>4)
        for i, emp in enumerate(c.tables['employees']):
            emp.update(bank_account=f'LIM_BANK_{i}', bank_code='SIMBANK', phone=f'090199000{i}', address=f'LIM_{i}')
        c.vendor.update(bank_account='LIM_VENDOR', bank_code='SIMBANK', phone='0902990000', address='LIM_V', national_id='079077000111')
        # Add 4 extra vendors (5 total >4 graph limit) while keeping vendors coverage complete
        vendors_list = [c.vendor]
        for vi in range(4):
            ev = deepcopy(c.vendor)
            ev['vendor_id'] = f'EXTRA_V_{vi}'
            ev['name'] = f'Extra Vendor {vi}'
            ev['bank_account'] = f'EV_BANK_{vi}'
            ev['phone'] = f'090888000{vi}'
            ev['address'] = f'EV_ADDR_{vi}'
            vendors_list.append(ev)
        c.tables['vendors'] = vendors_list
        c.tables['customers'] = c.tables['customers'][:1]
        c.tables['entity_links'] = []
        c.tables['attendance'] = []
        c.tables['vendor_status_history'] = [r for r in c.tables['vendor_status_history'] if r['vendor_id'] == c.vendor['vendor_id']]
        tx = c.pay(c.at - timedelta(minutes=10), 60_000_000, invoice_number='INV_LIM', invoice_gross_vnd=60_000_000)
        tx['created_at'] = (c.at - timedelta(minutes=10, seconds=10)).isoformat()
        tx['approved_at'] = (c.at - timedelta(minutes=10)).isoformat()
        tx['recipient_bank_code'] = ''
        c.rows = [tx]
        c.tables['transactions'] = c.rows
        tp.authorities(c)
        # Add 4 more matching authority rules for director -> 5 total (>4 C3 authority limit)
        base_rule = deepcopy(c.tables['approval_authorities'][1])
        for idx in range(4):
            extra_rule = deepcopy(base_rule)
            extra_rule['authority_id'] = f'EXTRA_RULE_{idx}'
            extra_rule['min_amount_vnd'] = idx * 1_000_000
            c.tables['approval_authorities'].append(extra_rule)
        src = tp.finish(c, 'C001')
        src['tenant_id'] = 'demo'
        doc = tp._wrap(src, [tx['transaction_id']])

        sc = self.auth.authorize('Bearer ' + self.director_tok, 'C001')
        sid = tp._commit(self.snapshots, sc, doc, 'snap-limits')

        fake_up, fake_dl, fake_post = self._mock_worker_handlers()
        bridge = _SyntheticBridge()
        node = EnterpriseNode(self.auth, self.models.path, self.snapshots.path, self.config_v1_1['worker_url'], self.worker_hex, self.prov_key)
        node.enable_jobs(self.root / 'legacy_jobs_lim', self.state_key, required_provider='windows-dpapi-current-user')
        node.jobs.close()
        with (
            patch('experiments.he4.coordinator.upload', side_effect=fake_up),
            patch('experiments.he4.coordinator.download', side_effect=fake_dl),
            patch('experiments.he4.coordinator.post', side_effect=fake_post),
        ):
            jobs = FourJobs(node, Settings(dict(self.config_v1_1, state_dir=str(self.root / 'jobs_lim'))), workers=0, bridge=bridge)
            self.addCleanup(jobs.close)
            st = jobs.submit('C001', 'Bearer ' + self.director_tok, 'lim-check-0001', dict(artifact_id=None, snapshot_id=sid, as_of=src['as_of']))
            while jobs._process(sc, st['job_id']):
                pass
            code, res = jobs.result('C001', 'Bearer ' + self.director_tok, st['job_id'])
            self.assertEqual(code, 200)
            row = res['rows'][0]
            self.assertTrue(row['groups']['p1']['available'])
            self.assertFalse(row['groups']['c3']['available'])
            self.assertEqual(row['groups']['c3']['reason'], 'he_c3_authority_limit')
            self.assertFalse(row['groups']['b1']['available'])
            self.assertEqual(row['groups']['b1']['reason'], 'recipient_bank_identity_incomplete')
            self.assertFalse(row['groups']['b5_e4']['available'])
            self.assertEqual(row['groups']['b5_e4']['reason'], 'he_graph_node_limit')


if __name__ == '__main__':
    unittest.main()
