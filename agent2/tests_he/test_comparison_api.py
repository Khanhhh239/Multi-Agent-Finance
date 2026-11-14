"""Comparison uses real scoped Portal/snapshot/review stores, archived HE outputs."""
import json,unittest
from copy import deepcopy
from web_support import WebHarness
from comparison_support import seed_run
from sme_fraud.selection_comparison import POLICY


class ComparisonAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=WebHarness().__enter__();cls.runs={c:seed_run(cls.f,c,'selection-api-'+c) for c in ('C001','C002')}

    @classmethod
    def tearDownClass(cls):cls.f.__exit__()

    def url(self,company='C001',run=None):return '/agent2/api/v1/companies/'+company+'/workspace/runs/'+(run or self.runs[company])+'/comparison'
    def create(self,company='C001',run=None):return self.f.h.request(self.url(company,run),body=dict(policy=POLICY,budget=5))

    def test_01_same_company_period_budget_missingness_and_no_private_model_metadata(self):
        for company in ('C001','C002'):
            status,r=self.create(company);self.assertEqual(status,200,r)
            self.assertEqual([x['record_id'] for x in r['baseline']['transactions']],['P1_T03','P1_T06','P1_T07'])
            self.assertEqual([x['record_id'] for x in r['added']],['P1_T04','P1_T02']);self.assertEqual(r['removed'],[])
            self.assertEqual(r['baseline']['metrics']['selected'],3);self.assertEqual(r['combined']['metrics']['selected'],5)
            self.assertEqual(r['plan']['budget'],5);self.assertEqual(r['plan']['company_id'],company);self.assertEqual(r['coverage']['ml_available'],7);self.assertEqual(r['coverage']['p1_unavailable'],1)
            self.assertEqual(r['common_coverage']['cohort_size'],5);self.assertEqual(r['added'][0]['rule_state'],'not_applicable')
            self.assertIsNone(r['delta']['declared_useful_transactions']);self.assertIsNone(r['combined']['metrics']['accuracy'])
            self.assertNotIn('artifact_id',json.dumps(r));self.assertNotIn('raw_score',json.dumps(r));self.assertNotIn('Mahalanobis',json.dumps(r))
            again=self.create(company)[1];self.assertEqual(r['plan_sha256'],again['plan_sha256']);self.assertEqual(r['plan_id'],again['plan_id'])

    def test_02_feedback_updates_metrics_but_selection_and_plan_hash_stay_locked(self):
        before=self.create()[1];case=before['added'][0];prefix='jobs/'+self.runs['C001']+'/reviews/'+case['case_id']
        lease=self.f.request(prefix+'/start',body={})[1]['lease'];packet=self.f.request('jobs/'+self.runs['C001']+'/reviews')[1]
        target=next(c for c in packet['cases'] if c['case_id']==case['case_id'])
        status,saved=self.f.request(prefix+'/save',body=dict(lease=lease,expected_revision=0,request_id='comparison-review-save',feedback=dict(outcome='confirmed_risk',usefulness='yes',explanation='Fixture: correction requires follow-up, not verified fraud.',action='Request accounting correction.',missing_materials='',evidence_ids=[target['evidence'][0]['evidence_id']],checks_completed=True)))
        self.assertEqual(status,200,saved)
        after=self.f.h.request(self.url())[1];self.assertEqual(before['plan_sha256'],after['plan_sha256']);self.assertEqual(before['plan_id'],after['plan_id']);self.assertEqual([x['record_id'] for x in before['added']],[x['record_id'] for x in after['added']])
        self.assertEqual(after['combined']['metrics']['reviewed'],1);self.assertEqual(after['combined']['metrics']['declared_problem_transactions'],1)
        self.assertIsNone(after['combined']['metrics']['declared_precision_at_selected']);self.assertIsNone(after['delta']['declared_useful_transactions']);self.assertIsNone(after['combined']['metrics']['confirmed_fraud_cases'])
        self.assertEqual(after['status'],'technical_only');self.assertNotEqual(before['report_sha256'],after['report_sha256'])

    def test_03_no_session_cross_company_query_and_unknown_route_are_denied(self):
        self.assertEqual(self.f.h.request(self.url(),token=False)[0],401)
        self.assertEqual(self.f.h.request(self.url('C002',self.runs['C001']))[0],404)
        self.assertEqual(self.f.h.request(self.url('OTHER','herun_'+'0'*32))[0],403)
        self.assertEqual(self.f.h.request(self.url()+'?budget=50')[0],404)
        self.assertEqual(self.f.h.request(self.url()+'/reset',body={})[0],404)
        self.assertEqual(self.f.h.request(self.url().replace('/comparison','/comparisonX'))[0],404)

    def test_04_client_cannot_change_policy_budget_weights_or_send_outcomes(self):
        for body in [dict(policy=POLICY,budget=True),dict(policy=POLICY,budget=6),dict(policy='weighted',budget=5),dict(policy=POLICY,budget=5,weight=.9),dict(policy=POLICY,budget=5,confirmed=True)]:
            self.assertEqual(self.f.h.request(self.url(),body=body)[0],400)

    def test_05_revoke_permission_blocks_existing_plan_and_exports(self):
        old=deepcopy(self.f.h.policy)
        try:
            self.create();self.f.h.policy['memberships'][0]['status']='revoked';self.f.h.write_policy()
            self.assertEqual(self.f.h.request(self.url())[0],403)
        finally:self.f.h.policy=old;self.f.h.write_policy()

    def test_06_get_does_not_create_plan_and_unfinished_job_is_rejected(self):
        run=seed_run(self.f,'C001','selection-api-unplanned')
        status,value=self.f.h.request(self.url(run=run));self.assertEqual(status,404,value)
        scope=self.f.h.authorizer.authorize('Bearer '+self.f.h.token,'C001');row,data=self.f.node.jobs.store.get(scope,run);self.f.node.jobs.store.save(scope,run,data,'ready')
        self.assertEqual(self.create(run=run)[0],409)

    def test_07_changed_result_cannot_silently_reselect(self):
        run=seed_run(self.f,'C001','selection-api-tamper');self.assertEqual(self.create(run=run)[0],200)
        scope=self.f.h.authorizer.authorize('Bearer '+self.f.h.token,'C001');row,data=self.f.node.jobs.store.get(scope,run);data['result']['rows'][1]['branches']['ml']['raw_score']+=1;self.f.node.jobs.store.save(scope,run,data,'completed')
        self.assertEqual(self.f.h.request(self.url(run=run))[0],409)


if __name__=='__main__':unittest.main()
