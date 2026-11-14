"""Business work area: real isolated Portal/CKKS/review stores; no live writes."""
from copy import deepcopy
import csv
import io
import json
import time
import unittest
from web_support import WebHarness
from sme_fraud.workspace_api import csv_report,case_view
from sme_fraud.he_result_view import review_result


class WorkspaceAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=WebHarness().__enter__();cls.company='C001';cls.snapshot=cls.f.pair.env['queries'][cls.company]
        status,job=cls.f.request('jobs',body=dict(snapshot_id=cls.snapshot),headers={'Idempotency-Key':'workspace-api-run'})
        if status!=202:raise AssertionError(job)
        cls.job=job['job_id'];deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            if cls.f.request('jobs/'+cls.job+'/result')[0]==200:return
            time.sleep(.1)
        raise AssertionError('fixture result timeout')

    @classmethod
    def tearDownClass(cls):cls.f.__exit__()

    def url(self,tail='',company='C001'):return '/agent2/api/v1/companies/'+company+'/workspace'+tail

    def test_overview_has_company_data_and_existing_runs_without_model_configuration(self):
        status,value=self.f.h.request(self.url());self.assertEqual(status,200,value)
        self.assertEqual(value['company_id'],'C001');self.assertFalse(value['can_manage'])
        self.assertIn(self.job,[r['job_id'] for r in value['runs']]);self.assertIn(self.snapshot,[d['snapshot_id'] for d in value['datasets']])
        self.assertNotIn(self.f.pair.env['queries']['C002'],json.dumps(value));self.assertNotIn('artifact_id',json.dumps(value))

    def test_case_view_preserves_all_rows_and_keeps_feedback_unverified(self):
        status,value=self.f.h.request(self.url('/runs/'+self.job));self.assertEqual(status,200,value)
        self.assertEqual(value['row_count'],5);self.assertEqual(len(value['cases']),5)
        self.assertEqual(value['snapshot_id'],self.snapshot);self.assertFalse(value['training_eligible'])
        self.assertEqual({c['record_id'] for c in value['cases']},{'T0','T1','T2','T3','T4'})
        for case in value['cases']:
            self.assertIsInstance(case['amount_vnd'],str);self.assertEqual(len(case['checks']),4)
            self.assertTrue(case['question']);self.assertTrue(case['why']);self.assertTrue(case['next_step'])
            self.assertTrue(all(e['simulated'] and not e['original_verified'] for e in case['evidence']))
        self.assertNotIn('artifact_id',json.dumps(value));self.assertNotIn('Mahalanobis',json.dumps(value))

    def test_feedback_and_download_reflect_server_save_and_request_replay(self):
        before=self.f.h.request(self.url('/runs/'+self.job))[1];case=before['cases'][0]
        prefix='jobs/'+self.job+'/reviews/'+case['case_id'];lease=self.f.request(prefix+'/start',body={})[1]['lease']
        body=dict(lease=lease,expected_revision=0,request_id='workspace-save-stable',feedback=dict(outcome='inconclusive',usefulness='not_assessed',explanation='=1+1',action='Request original invoice',missing_materials='Original invoice absent',evidence_ids=[],checks_completed=False))
        status,saved=self.f.request(prefix+'/save',body=body);self.assertEqual(status,200,saved)
        self.assertEqual(self.f.request(prefix+'/save',body=body)[1],saved)
        report=self.f.h.request(self.url('/runs/'+self.job+'/report'))[1]
        self.assertEqual(report['summary']['reviewed_cases'],1);self.assertEqual(report['cases'][0]['review']['revision'],1)
        self.assertIsNone(report['summary']['accuracy']);self.assertFalse(report['training_eligible'])
        status,raw=self.f.h.request(self.url('/runs/'+self.job+'/report.csv'));self.assertEqual(status,200)
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'));rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))));self.assertEqual(len(rows),6)
        self.assertEqual(rows[1][7],"'=1+1");self.assertEqual(rows[1][0],'C001')

    def test_missing_session_other_company_query_and_unlisted_export_are_rejected(self):
        self.assertEqual(self.f.h.request(self.url(),token=False)[0],401)
        self.assertEqual(self.f.h.request(self.url(company='OTHER'))[0],403)
        self.assertEqual(self.f.h.request(self.url('/runs/'+self.job,company='C002'))[0],404)
        self.assertEqual(self.f.h.request(self.url('?company=C002'))[0],404)
        self.assertEqual(self.f.h.request(self.url('/runs/'+self.job+'/reportXcsv'))[0],404)

    def test_pending_progress_has_source_and_counts_but_no_private_inputs(self):
        scope=self.f.h.authorizer.authorize('Bearer '+self.f.h.token,'C001');store=self.f.node.jobs.store
        job=store.create(scope,'workspace-progress-fixture',dict(snapshot_id=self.snapshot,as_of='2026-10-03T00:00:00+07:00',artifact_id=self.f.pair.env['artifacts']['C001']))
        _,data=store.get(scope,job);data['pending']=dict(tasks=[{'values':'PRIVATE_FEATURES'},{'values':'PRIVATE_FEATURES'}],cursor=1)
        store.save(scope,job,data,'ready')
        status,value=self.f.h.request(self.url('/runs/'+job));self.assertEqual(status,200,value)
        self.assertEqual(value['progress']['completed_tasks'],1);self.assertEqual(value['progress']['total_tasks'],2);self.assertEqual(value['snapshot_id'],self.snapshot)
        self.assertNotIn('PRIVATE_FEATURES',json.dumps(value));self.assertNotIn('cases',value)
        self.assertEqual(self.f.h.request(self.url('/runs/'+job+'/report.csv'))[0],409)


class BusinessProjection(unittest.TestCase):
    def test_graph_projection_uses_field_then_entity_axes(self):
        case={k:None for k in ('case_id','record_id','revision','amount_vnd','currency','event_at','as_of','question','next_step','review')}
        case.update(why='source',evidence=[])
        matrix=[[[0]*4 for _ in range(4)] for _ in range(4)]
        matrix[0][0][1]=matrix[0][1][0]=1
        matrix[2][0][1]=matrix[2][1][0]=1
        entities=[dict(table='vendors',record_id='V1',revision=1),dict(table='employees',record_id='E1',revision=1)]
        value=case_view(case,dict(branches=dict(graph=dict(entities=entities,links_by_field=matrix))))
        self.assertEqual(len(value['graph_links']),2)
        self.assertEqual([x['context_only'] for x in value['graph_links']],[False,True])
        self.assertTrue(all(x['source']=='V1' and x['target']=='E1' for x in value['graph_links']))

    def test_new_unknown_model_fields_never_reach_accountant_result(self):
        row=dict(record_id='T0',revision=1,score=1.,available=True,status='available',reason=None,private_feature_values=[1,2],branches={
            'ml':dict(available=True,status='available',model='Mahalanobis',secret_coefficients=[1,2],raw_score=1.),
            'statistics':dict(available=True,status='available',artifact_id='PRIVATE_MODEL',feature_contract='PRIVATE_FEATURES',score_kind='sum_clipped_robust_z',raw_score=2.),
            'rules':dict(available=True,status='partial',rule_id='PRIVATE_RULE',thresholds='PRIVATE_THRESHOLDS',invoice_checks=[dict(cumulative_paid_vnd='12000000',invoice_gross_vnd='10000000',matched=True,private_rule_config='SECRET')])})
        value=review_result(dict(version='he-four-branch-result/1.0.0',rows=[row],row_count=1,plan_sha256='PRIVATE_PLAN'))
        raw=json.dumps(value)
        for forbidden in ['Mahalanobis','PRIVATE_MODEL','PRIVATE_FEATURES','PRIVATE_RULE','PRIVATE_THRESHOLDS','SECRET','PRIVATE_PLAN','private_feature_values']:self.assertNotIn(forbidden,raw)
        self.assertTrue(value['rows'][0]['branches']['rules']['invoice_checks'][0]['matched'])

    def test_csv_keeps_negative_adjustment_and_escapes_user_text(self):
        report=dict(company_id='C001',run_id='run',snapshot_id='snapshot',cases=[dict(record_id='=DANGEROUS()',event_at='2026-10-05',amount_vnd='-12000000',evidence=[],review=dict(active_seconds=0,revision=1,feedback=dict(outcome='inconclusive',explanation=' @unsafe',action='+unsafe',missing_materials='-unsafe',evidence_ids=[])))])
        rows=list(csv.reader(io.StringIO(csv_report(report).decode('utf-8-sig'))));self.assertEqual(rows[1][5],'-12000000')
        self.assertTrue(all(rows[1][i].startswith("'") for i in (3,7,8,9)))


if __name__=='__main__':unittest.main()
