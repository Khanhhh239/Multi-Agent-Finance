"""Label audit, immutable source/locks, retries, authorization and real HTTP."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import os
import json
import secrets
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from training_snapshot_support import native, canonical_source, scope, commit, request
from sme_fraud.import_files import ImportFailure, canonical, digest
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.label_packets import LabelStore, source_packet
from sme_fraud.label_api import sources
from sme_fraud.review_server import make_server
from test_portal_auth import PortalHarness
from portal import server as portal


class LabelPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snapshots = SnapshotStore(self.root / 'snapshots.sqlite3')
        self.key = os.urandom(32)
        self.labels = LabelStore(self.root / 'labels.sqlite3', self.key)
        self.scope = scope(permissions={'data.import', 'evidence.verify', 'model.fit'})
        self.source = native()
        sid = commit(self.snapshots, self.source, self.scope)
        self.request = request(sid, self.source)
        self.packet = self.labels.create(self.scope, source_packet(self.snapshots, self.scope, self.request))

    def change(self, action='save', index=0, outcome='verified_fraud', packet=None, authority=None, **kw):
        packet = packet or self.packet
        body = dict(expected_revision=packet['revision'], request_id=secrets.token_hex(16))
        if action == 'save':
            case = packet['cases'][index]
            body['label'] = dict(record_id=case['record_id'], revision=case['revision'], outcome=outcome,
                explanation='Synthetic test: documents manually compared.',
                evidence_ids=[case['evidence'][0]['evidence_id']], documents_checked=True)
        body.update(kw)
        return self.labels.change(authority or self.scope, packet['packet_id'], action, body)

    def denied(self, code, fn):
        with self.assertRaises(ImportFailure) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code)

    def test_both_source_profiles_start_null_and_preserve_evidence(self):
        for source in (self.source, canonical_source()):
            sid = commit(self.snapshots, source, self.scope, key='p-' + digest(canonical(source))[:12])
            packet = self.labels.create(self.scope, source_packet(self.snapshots, self.scope, request(sid, source)))
            self.assertEqual([r['outcome'] for r in packet['labels']], [None] * 4)
            self.assertTrue(all(c['evidence'] for c in packet['cases']))
            self.assertTrue(all(not e['original_verified'] for c in packet['cases'] for e in c['evidence']))
            self.assertEqual(packet, self.labels.create(self.scope, source_packet(self.snapshots, self.scope, request(sid, source))))

    def test_saving_one_keeps_unrelated_labels_and_unknown_is_null(self):
        first = self.change()
        second = self.change(index=1, outcome='verified_non_fraud', packet=first)
        third = self.change(index=2, outcome=None, packet=second)
        self.assertEqual([r['outcome'] for r in third['labels']], ['verified_fraud', 'verified_non_fraud', None, None])
        self.assertEqual(third['labels'][0], first['labels'][0])
        self.assertIsNone(third['labels'][2]['verified_by'])
        self.assertEqual(third['labels'][1]['verified_by'], self.scope.actor_id)

    def test_unknown_can_lock_but_cannot_train(self):
        locked = self.change('lock')
        out = self.labels.export(self.scope, locked['packet_id'], locked['revision'], locked['lock_sha256'])
        self.assertFalse(out['training_ready'])
        self.assertFalse(out['training_started'])
        self.assertEqual([r['outcome'] for r in out['labels']], [None] * 4)
        self.assertEqual(out['verification_mode'], 'synthetic_expected')

    def test_complete_balanced_labels_ready_only_after_lock(self):
        p = self.packet
        for i in range(4):
            p = self.change(index=i, packet=p, outcome='verified_fraud' if i % 2 else 'verified_non_fraud')
        self.denied('LABEL_LOCK_MISMATCH', lambda: self.labels.export(self.scope, p['packet_id'], p['revision'], None))
        p = self.change('lock', packet=p)
        self.assertTrue(self.labels.export(self.scope, p['packet_id'], p['revision'], p['lock_sha256'])['training_ready'])

    def test_one_class_or_missing_predictor_stays_ineligible_after_verification(self):
        for missing in (False, True):
            with self.subTest(missing_predictor=missing):
                if missing:
                    data = canonical_source()
                    data['approvals'] = []
                    sid = commit(self.snapshots, data, self.scope, key='missing-predictor')
                    p = self.labels.create(self.scope, source_packet(self.snapshots, self.scope, request(sid, data)))
                    self.assertEqual(p['binding']['feature_status'], 'rejected')
                else:
                    p = self.packet
                for i in range(4):
                    p = self.change(index=i, packet=p, outcome='verified_non_fraud' if missing and i % 2 else 'verified_fraud')
                p = self.change('lock', packet=p)
                self.assertFalse(self.labels.export(self.scope, p['packet_id'], p['revision'], p['lock_sha256'])['training_ready'])

    def test_optimistic_conflict_and_same_request_retry(self):
        body = dict(expected_revision=1, request_id='same-request-12345678')
        first = self.labels.change(self.scope, self.packet['packet_id'], 'lock', body)
        self.assertEqual(first, self.labels.change(self.scope, self.packet['packet_id'], 'lock', body))
        self.denied('LABEL_RETRY_CONFLICT', lambda: self.labels.change(self.scope, self.packet['packet_id'], 'reopen', body))
        self.denied('LABEL_REVISION_CONFLICT', lambda: self.change())

    def test_lock_cannot_edit_reopen_keeps_original_export(self):
        saved = self.change()
        locked = self.change('lock', packet=saved)
        self.denied('LABEL_LOCKED', lambda: self.change(packet=locked))
        reopened = self.change('reopen', packet=locked)
        self.assertEqual(reopened['labels'], locked['labels'])
        changed = self.change(outcome=None, packet=reopened)
        self.assertIsNone(changed['labels'][0]['outcome'])
        original = self.labels.export(self.scope, locked['packet_id'], locked['revision'], locked['lock_sha256'])
        self.assertEqual(original['labels'][0]['outcome'], 'verified_fraud')
        self.denied('LABEL_LOCK_MISMATCH', lambda: self.labels.export(self.scope, locked['packet_id'], changed['revision'], locked['lock_sha256']))

    def test_evidence_must_be_exact_case_and_fields_not_client_identity(self):
        c = self.packet['cases'][0]
        label = dict(record_id=c['record_id'], revision=c['revision'], outcome='verified_fraud', explanation='Reason long enough.', evidence_ids=['lev_'+'0'*64], documents_checked=True)
        self.denied('LABEL_EVIDENCE_BINDING', lambda: self.change(label=label))
        label['evidence_ids'] = [c['evidence'][0]['evidence_id']]
        for field, value in [('documents_checked', False), ('evidence_ids', []), ('explanation', '')]:
            bad = dict(label, **{field: value})
            self.denied('LABEL_EVIDENCE_REQUIRED', lambda: self.change(label=bad))
        self.denied('LABEL_FIELDS', lambda: self.change(label=dict(label, verified_by='forged')))
        self.denied('LABEL_OUTCOME', lambda: self.change(label=dict(label, outcome='confirmed_risk')))

    def test_reader_can_view_verified_without_verification_permission(self):
        p = self.change()
        reader = replace(self.scope, actor_id='other-reader', permissions=frozenset({'data.import'}))
        self.assertEqual(self.labels.get(reader, p['packet_id'])['labels'], p['labels'])
        self.denied('LABEL_VERIFICATION_DENIED', lambda: self.change(authority=reader))
        self.denied('LABEL_VERIFICATION_DENIED', lambda: self.labels.create(reader, self.packet))

    def test_shared_company_audit_records_each_authenticated_reviewer(self):
        p = self.change()
        other = replace(self.scope, actor_id='second-reviewer')
        p = self.change(index=1, packet=p, authority=other)
        self.assertEqual(p['labels'][0]['verified_by'], self.scope.actor_id)
        self.assertEqual(p['labels'][1]['verified_by'], other.actor_id)

    def test_other_company_same_ids_and_other_tenant_cannot_read(self):
        for authority in (scope('C002'), scope(tenant='other')):
            self.denied('LABEL_PACKET_NOT_FOUND', lambda: self.labels.get(authority, self.packet['packet_id']))
        s = scope('C002', permissions=self.scope.permissions)
        data = native('C002')
        sid = commit(self.snapshots, data, s)
        second = self.labels.create(s, source_packet(self.snapshots, s, request(sid, data)))
        self.assertNotEqual(second['packet_id'], self.packet['packet_id'])
        self.assertEqual(second['labels'][0]['record_id'], self.packet['labels'][0]['record_id'])

    def test_restart_wrong_key_and_db_payload_is_sealed(self):
        p = self.change()
        again = LabelStore(self.labels.path, self.key)
        self.assertEqual(again.get(self.scope, p['packet_id']), p)
        self.assertNotIn(b'Synthetic test:', self.labels.path.read_bytes())
        with self.assertRaises(Exception):
            LabelStore(self.labels.path, os.urandom(32))

    def test_revocation_before_commit_rolls_back(self):
        calls = []
        def check():
            calls.append(1)
            return self.scope if len(calls) == 1 else replace(self.scope, permissions=frozenset({'data.import'}))
        body = dict(expected_revision=1, request_id='revoke-write-123456', label=dict(record_id=self.packet['cases'][0]['record_id'], revision=1, outcome=None, explanation='', evidence_ids=[], documents_checked=False))
        self.denied('AUTH_CONTEXT_CHANGED', lambda: self.labels.change(self.scope, self.packet['packet_id'], 'save', body, check))
        self.assertEqual(self.labels.get(self.scope, self.packet['packet_id'])['revision'], 1)

    def test_source_time_selection_and_new_snapshot_do_not_reuse_labels(self):
        future = deepcopy(self.request)
        future['as_of'] = '2025-08-11T00:00:00+07:00'
        future['training_end'] = future['as_of']
        future['training_start'] = '2025-08-10T00:00:00+07:00'
        self.denied('LABEL_SOURCE_UNAVAILABLE', lambda: source_packet(self.snapshots, self.scope, future))
        data = deepcopy(self.source)
        data['source']['tables']['transactions'][0]['amount_vnd'] += 1
        data['source']['coverage']['transactions']['records_sha256'] = digest(canonical(data['source']['tables']['transactions']))
        sid = commit(self.snapshots, data, self.scope, key='new-source')
        fresh = self.labels.create(self.scope, source_packet(self.snapshots, self.scope, request(sid, data)))
        self.assertNotEqual(fresh['packet_id'], self.packet['packet_id'])
        self.assertTrue(all(r['outcome'] is None for r in fresh['labels']))

    def test_catalogue_is_company_scoped_and_returns_exact_source(self):
        catalogue = sources(self.snapshots, self.scope, None)
        self.assertEqual(len(catalogue['snapshots']), 1)
        source = sources(self.snapshots, self.scope, None, self.request['snapshot_id'])
        self.assertEqual(len(source['rows']), 4)
        self.assertTrue(all(isinstance(r['amount_vnd'], str) for r in source['rows']))
        self.assertEqual(sources(self.snapshots, scope('C002'), None)['snapshots'], [])

    def test_simulated_evidence_does_not_verify_real_labels(self):
        source = source_packet(self.snapshots, self.scope, self.request)
        source['binding']['simulated'] = False
        p = self.labels.create(self.scope, source)
        self.denied('LABEL_SIMULATED_EVIDENCE', lambda: self.change(packet=p))

    def test_append_only_history_and_tampered_cipher_fail_closed(self):
        p = self.change()
        conn = sqlite3.connect(self.labels.path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM packets')
        conn.rollback()
        conn.execute('DROP TRIGGER packets_update')
        conn.execute('UPDATE packets SET payload=? WHERE revision=?', (b'corrupted', p['revision']))
        conn.commit(); conn.close()
        self.denied('LABEL_STORAGE_INTEGRITY', lambda: self.labels.get(self.scope, p['packet_id']))

    def test_actual_parallel_writes_do_not_overwrite_each_other(self):
        barrier = threading.Barrier(2)
        results = []
        def write(index):
            barrier.wait()
            try:
                self.change(index=index)
                results.append('saved')
            except ImportFailure as error:
                results.append(error.code)
        threads = [threading.Thread(target=write, args=(i,)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertCountEqual(results, ['saved', 'LABEL_REVISION_CONFLICT'])
        p = self.labels.get(self.scope, self.packet['packet_id'])
        self.assertEqual(sum(r['outcome'] is not None for r in p['labels']), 1)

    def test_canonical_simulated_invoice_keeps_its_source_badge(self):
        data = canonical_source()
        for rows in data.values():
            if isinstance(rows, list):
                for r in rows: r['source']['is_simulated'] = False
        sample = json.loads((Path(__file__).resolve().parents[1] / 'sme_fraud/web/import-demo.json').read_bytes())
        data['invoices'] = sample['invoices']
        allocation = deepcopy(sample['payment_allocations'][0])
        allocation['transaction_ref'] = dict(record_id=data['transactions'][0]['record_id'], revision=1)
        allocation['source']['is_simulated'] = False
        data['payment_allocations'] = [allocation]
        sid = commit(self.snapshots, data, self.scope, key='real-mode-synthetic-doc')
        p = self.labels.create(self.scope, source_packet(self.snapshots, self.scope, request(sid, data)))
        self.assertFalse(p['binding']['simulated'])
        invoice = next(e for e in p['cases'][0]['evidence'] if e['table'] == 'invoices')
        self.assertTrue(invoice['simulated'])
        c = p['cases'][0]
        label = dict(record_id=c['record_id'], revision=c['revision'], outcome='verified_fraud', explanation='Synthetic fixture to test refusal.', evidence_ids=[invoice['evidence_id']], documents_checked=True)
        self.denied('LABEL_SIMULATED_EVIDENCE', lambda: self.change(packet=p, label=label))


class LabelPortalTests(unittest.TestCase):
    def test_real_portal_proxy_permissions_scope_and_persistence(self):
        with PortalHarness() as h:
            h.agent.shutdown(); h.agent.server_close()
            labels = LabelStore(h.root / 'labels.sqlite3', os.urandom(32))
            h.agent = make_server(0, h.authorizer, h.store, label_store=labels)
            portal.CFG['agents']['agent2']['port'] = h.agent.server_port
            thread = threading.Thread(target=h.agent.serve_forever, daemon=True); thread.start(); h.threads.append(thread)
            s = scope(permissions={'data.import', 'evidence.verify'})
            data = native(); sid = commit(h.store, data, s)
            q = request(sid, data)
            url = h.url('label-packets')
            self.assertEqual(h.request('/agent2/label-verification')[0], 200)
            self.assertEqual(h.request(url, q)[0], 403)
            h.policy['memberships'][0]['permissions'].append('evidence.verify'); h.write_policy()
            status, p = h.request(url, q)
            self.assertEqual(status, 200, p)
            self.assertEqual(h.request(h.url('label-sources/'+sid))[0], 200)
            body = dict(expected_revision=p['revision'], request_id='http-lock-123456789')
            status, locked = h.request(url+'/'+p['packet_id']+'/lock', body)
            self.assertEqual(status, 200, locked)
            self.assertEqual(locked['history'][-1]['actor_id'], 'portal-reviewer')
            h.policy['memberships'][0]['permissions'] = ['data.import']; h.write_policy()
            self.assertEqual(h.request(url+'/'+p['packet_id'])[0], 200)
            status, exported = h.request(url+'/'+p['packet_id']+'/export', dict(revision=locked['revision'], lock_sha256=locked['lock_sha256']))
            self.assertEqual(status, 200, exported)
            self.assertFalse(exported['training_started'])
            self.assertEqual(h.request(h.url('label-packets/'+p['packet_id'], 'C002'))[0], 404)
            self.assertEqual(h.request(url+'/'+p['packet_id'], method='PUT')[0], 405)
            self.assertEqual(h.request(url, token=False)[0], 401)
            h.policy['memberships'][0]['status'] = 'revoked'; h.write_policy()
            self.assertEqual(h.request(url+'/'+p['packet_id'])[0], 403)


if __name__ == '__main__':
    unittest.main()
