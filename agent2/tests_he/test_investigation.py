"""Independent investigation projection, PIT graphs and durable workflow contracts."""
import unittest
import base64
from copy import deepcopy
from unittest.mock import patch
from dataclasses import replace
from sme_fraud.investigation import Investigation,graph
from sme_fraud.import_files import ImportFailure
from test_bundle_workspace import BundleWorkspaceTests

class InvestigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):BundleWorkspaceTests.setUpClass()
    @classmethod
    def tearDownClass(cls):BundleWorkspaceTests.tearDownClass()
    def setUp(self):
        self.h=BundleWorkspaceTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.work=self.h.work;self.scope=self.h.scope;self.view=Investigation(self.work);self.run=self.h.run_id
    def test_queue_exact_saved_scores_candidates_only_and_no_rescoring(self):
        before=self.h.result['result']['pipeline']['cases']
        expected={p['transaction_id']:p['candidate_score'] for c in before for p in c['score_breakdown']['per_candidate']}
        with patch.object(self.h.svc,'run',side_effect=AssertionError('Must not score or fit')):
            result=self.view.queue(self.scope,self.run)
        self.assertTrue(result['rows']);self.assertEqual([r['score'] for r in result['rows']],sorted((r['score'] for r in result['rows']),reverse=True))
        for r in result['rows']:
            self.assertEqual(r['score'],expected[r['transaction_id']]);self.assertEqual(r['run_id'],self.run)
            self.assertEqual(r['snapshot_id'],self.h.report['snapshot_id']);self.assertIn(r['review_id'],[c['review_id'] for c in self.h.report['cases']])
            self.assertTrue(r['model_trace']);self.assertEqual(r['status'],'new')
            if r['explanation']['components_reconcile']:
                self.assertAlmostEqual(sum(p['contribution'] or 0 for p in r['explanation']['contributions']),r['score'])
        p1=next(r for r in result['rows'] if any(c['case_id']==r['case_id'] and 'P1' in c['actionable_rule_ids'] for c in before))
        self.assertIn('P1',[s['rule_id'] for s in p1['signals']])
    def test_missing_saved_candidate_score_is_unavailable_never_case_score(self):
        observed=self.work.observation(self.scope,self.run);clone=deepcopy(observed)
        for c in clone['result']['pipeline']['cases']:c['score_breakdown']['per_candidate']=[]
        with patch.object(self.work,'observation',return_value=clone):
            result=self.view.queue(self.scope,self.run)
        self.assertTrue(all(r['score'] is None and r['score_status']=='unavailable' for r in result['rows']))
    def test_detail_binding_graph_evidence_and_cross_company_denial(self):
        row=self.view.queue(self.scope,self.run)['rows'][0]
        detail=self.view.detail(self.scope,self.run,row['transaction_id'],review_id=row['review_id'])
        self.assertEqual(detail['bundle_id'],self.h.report['bundle_id']);self.assertTrue(detail['evidence'])
        self.assertTrue(detail['graph']['nodes']);self.assertTrue(detail['graph']['edges'])
        for edge in detail['graph']['edges']:
            self.assertEqual(edge['evidence']['snapshot_id'],detail['snapshot_id']);self.assertFalse(edge['evidence']['original_verified'])
        other=self.h.h.fixture.company_ctx['C002']['scope']
        with self.assertRaises(ImportFailure):self.view.detail(other,self.run,row['transaction_id'])
        with self.assertRaises(ImportFailure):self.view.detail(self.scope,self.run,'not-a-candidate')
    def test_start_survives_reopen_and_review_versions_and_attachments_persist(self):
        row=self.view.queue(self.scope,self.run)['rows'][0];rid=row['review_id'];tid=row['transaction_id']
        start=self.work.action(self.scope,self.run,rid,'start',{})
        self.view.record(self.scope,rid,'request-start-001','started',lambda:self.scope)
        self.view.record(self.scope,rid,'request-start-001','started',lambda:self.scope)
        again=Investigation(self.work)
        self.assertEqual(again.detail(self.scope,self.run,tid,review_id=rid)['status'],'in_review')
        self.assertEqual(len(again.events(self.scope,rid)),1)
        att=self.work.action(self.scope,self.run,rid,'attachments',{'name':'evidence.pdf','content':base64.b64encode(b'%PDF-1.4\nsource').decode()})
        self.view.record(self.scope,rid,att['attachment_id'],'attached',lambda:self.scope)
        body=dict(expected_revision=0,request_id='save-investigation-001',lease=start['lease'],feedback=self.h.feedback())
        saved=self.work.action(self.scope,self.run,rid,'save',body)
        self.view.record(self.scope,rid,body['request_id'],'saved',lambda:self.scope)
        self.assertEqual(self.work.action(self.scope,self.run,rid,'save',body)['revision'],1)
        detail=again.detail(self.scope,self.run,tid,review_id=rid)
        self.assertEqual(detail['status'],'waiting_evidence');self.assertEqual(detail['review']['history'][0]['actor_id'],self.scope.actor_id)
        self.assertEqual(detail['review']['attachments'][0]['name'],'evidence.pdf')
        self.assertEqual(self.work.reviews.attachment(self.scope,rid,att['attachment_id'])['content'],base64.b64encode(b'%PDF-1.4\nsource').decode())
    def test_revocation_rolls_back_workflow_write(self):
        row=self.view.queue(self.scope,self.run)['rows'][0]
        with self.assertRaises(ImportFailure):self.view.record(self.scope,row['review_id'],'revoked-start-001','started',lambda:replace(self.scope,permissions=frozenset()))
        self.assertEqual(self.view.events(self.scope,row['review_id']),[])

class GraphTests(unittest.TestCase):
    def test_pit_same_names_distinct_ids_weak_edges_and_exact_source(self):
        from sme_fraud.auth import AccessScope
        scope=AccessScope('t',frozenset({'C001'}),'a',frozenset({'data.import'}))
        at='2026-01-10T12:00:00Z';known='2026-01-01T00:00:00Z'
        tx=dict(transaction_id='T1',amount_vnd=-9007199254740993,posted_at=known,observed_at=known,creator_id='E1',approver_id='E2',vendor_id='V1',invoice_number='INV1')
        data={'source':{'is_simulated':True,'tables':{'transactions':[tx,dict(tx,transaction_id='T2'),dict(tx,transaction_id='LATE',observed_at='2026-02-01T00:00:00Z')],
            'employees':[dict(employee_id=e,full_name='Cùng tên',revision=1,observed_at=known,address='Địa chỉ A',bank_account='001',bank_code='B') for e in ('E1','E2')],
            'vendors':[dict(vendor_id='V1',name='NCC',revision=1,observed_at=known,address='Địa chỉ A',bank_account='001',bank_code='B')],
            'invoices':[dict(invoice_id='LATE-INVOICE',observed_at='2026-02-01T00:00:00Z')]
        }}}
        result=graph(scope,{'snapshot_id':'s1'},data,'T1',at)
        people=[n for n in result['nodes'] if n['table']=='employees']
        self.assertEqual(len(people),2);self.assertNotEqual(people[0]['id'],people[1]['id'])
        self.assertNotIn('LATE',str(result));self.assertTrue(any(e['context_only'] for e in result['edges']))
        root=next(n for n in result['nodes'] if n['id']==result['root']);self.assertEqual(root['record']['amount_vnd'],'-9007199254740993')
        self.assertTrue(any(n['record_id']=='T2' for n in result['nodes']))
        self.assertTrue(all(e['evidence']['sha256'] and not e['evidence']['original_verified'] for e in result['edges']))

if __name__=='__main__':unittest.main()
