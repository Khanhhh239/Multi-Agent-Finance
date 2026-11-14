"""Seven milestone assertions; runner maps only these test IDs to the R1 catalog."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sme_fraud.import_files import canonical
from sme_fraud.snapshot_features import build_from_snapshot, build_feature_rows
from sme_fraud.snapshots import SnapshotStore
import test_snapshot_features as fixture
import test_snapshots as snapshot_tests
from test_validation_backend import bundle_for


class R1AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=SnapshotStore(Path(self.temp.name)/'snapshots.sqlite3')

    def http(self):
        server=snapshot_tests.SnapshotApiTests('test_full_http_upload_preview_confirm_snapshot_and_download')
        server.setUp();self.addCleanup(server.doCleanups)
        return server

    def test_R1_01(self):
        a=fixture.committed(self.store,'C001',key='r1-company-a-key')
        b=fixture.committed(self.store,'C002',key='r1-company-b-key')
        one=build_from_snapshot(self.store,fixture.scope('C001'),a,fixture.AS_OF)
        two=build_from_snapshot(self.store,fixture.scope('C002'),b,fixture.AS_OF)
        self.assertEqual({r['company_id'] for r in one['rows']},{'C001'})
        self.assertEqual({r['company_id'] for r in two['rows']},{'C002'})
        self.assertAlmostEqual(fixture.feature(one,'C001','T001')['prior_type_history_log_count'],math.log(2),places=7)
        self.assertEqual(fixture.feature(two,'C002','T001')['prior_type_history_log_count'],0)

    def test_R1_02(self):
        original=fixture.bundle('C001')
        without_late=json.loads(json.dumps(original))
        without_late['supporting_documents']=[d for d in without_late['supporting_documents'] if d['record_id']!='DOC_LATE']
        first=fixture.committed(self.store,data=without_late,key='r1-before-late-key')
        second=fixture.committed(self.store,data=original,key='r1-after-late-key')
        before=build_from_snapshot(self.store,fixture.scope(),first,fixture.AS_OF)
        after=build_from_snapshot(self.store,fixture.scope(),second,fixture.AS_OF)
        self.assertNotEqual(first,second)
        self.assertNotEqual(before['snapshot']['data_checksum'],after['snapshot']['data_checksum'])
        self.assertEqual(before['features'],after['features']);self.assertEqual(before['missing'],after['missing'])
        self.assertEqual(before['evidence'],after['evidence'])

    def test_R1_03(self):
        api=self.http();draft,old=api.ready();base='imports/'+draft['import_id']
        code,changed=api.call('PUT',base+'/mapping',dict(expected_revision=1,mapping={'tables':{'transactions':{'description':'adjustment_reason'}}}),headers={'Idempotency-Key':'r1-mapping-change'})
        self.assertEqual(code,200);self.assertEqual(changed['revision'],2)
        self.assertEqual(api.call('POST',base+'/commit',snapshot_tests.commit_fields(old),headers={'Idempotency-Key':'r1-stale-mapping'})[0],409)
        self.assertEqual(api.call('PUT',base+'/mapping',dict(expected_revision=2,mapping={}),headers={'Idempotency-Key':'r1-mapping-reset'})[0],200)
        code,preview=api.call('POST',base+'/preview',dict(expected_revision=3));self.assertEqual(code,200)
        data=bundle_for();data['transactions'][0]['description']='Changed file after preview'
        code,changed=api.call('PUT',base+'/source',raw=canonical(data),headers={'Idempotency-Key':'r1-source-change','X-File-Name':'changed.json','X-Expected-Revision':'3'})
        self.assertEqual(code,200);self.assertEqual(changed['revision'],4)
        self.assertEqual(api.call('POST',base+'/commit',snapshot_tests.commit_fields(preview),headers={'Idempotency-Key':'r1-stale-source'})[0],409)
        with closing(sqlite3.connect(api.store.path)) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM snapshots').fetchone()[0],0)
        code,fresh=api.call('POST',base+'/preview',dict(expected_revision=4));self.assertEqual(code,200)
        self.assertEqual(api.call('POST',base+'/commit',snapshot_tests.commit_fields(fresh),headers={'Idempotency-Key':'r1-fresh-commit'})[0],200)

    def test_R1_04(self):
        api=self.http();draft,report=api.ready();path='imports/'+draft['import_id']+'/commit'
        body=snapshot_tests.commit_fields(report)
        def save(_):return api.call('POST',path,body,headers={'Idempotency-Key':'r1-ten-retries-key'})
        with ThreadPoolExecutor(max_workers=10) as workers:responses=list(workers.map(save,range(10)))
        responses += [save(i) for i in range(10)]
        self.assertTrue(all(status==200 for status,value in responses))
        self.assertEqual(len({value['snapshot']['snapshot_id'] for status,value in responses}),1)
        with closing(sqlite3.connect(api.store.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM snapshots').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT count(*) FROM import_audit WHERE action='committed'").fetchone()[0],1)

    def test_R1_05(self):
        source=fixture.bundle('C001');snapshot=fixture.committed(self.store,data=source,key='r1-signed-input-key')
        result=build_from_snapshot(self.store,fixture.scope(),snapshot,'2026-10-13T00:00:00+07:00')
        self.assertEqual(len(result['rows']),len(source['transactions']))
        self.assertEqual(fixture.feature(result,'C001','ADJ001')['amount_negative'],1)
        self.assertEqual(fixture.feature(result,'C001','Z0001')['amount_zero'],1)
        self.assertTrue(any(e['signed_amount_vnd']==-2000000 for e in result['evidence']))
        self.assertIsNone(fixture.feature(result,'C001','T002')['journal_line_count'])
        self.assertTrue(any(any(row) for row in result['missing']))

    def test_R1_06(self):
        source=fixture.bundle('C001');one=build_feature_rows(source,fixture.scope(),fixture.AS_OF)
        for id in ('T001','T002'):
            values=fixture.feature(one,'C001',id)
            self.assertAlmostEqual(values['prior_type_history_log_count'],math.log(2),places=7)
            self.assertEqual(values['prior_invoice_payment_count'],1)
        for rows in source.values():
            if isinstance(rows,list):rows.reverse()
        two=build_feature_rows(source,fixture.scope(),fixture.AS_OF)
        self.assertEqual(one['features'],two['features']);self.assertEqual(one['rows'],two['rows'])

    def test_R1_07(self):
        self.http().test_all_routes_deny_company_b_before_body_or_storage_access()
        self.http().test_foreign_resource_ids_on_authorized_company_route_return_no_records()
        self.http().test_permission_revoked_after_body_read_blocks_commit()


if __name__=='__main__':unittest.main()
