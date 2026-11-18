"""Actual MethodStore/validation/queue bridge on synthetic enterprise fixtures."""
from copy import deepcopy
from pathlib import Path
from dataclasses import replace
from contextlib import closing
import sqlite3
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from finance_input.json_io import loads
from sme_fraud.import_files import canonical,digest,ImportFailure
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.pipeline_release import ReleaseService,runtime_signature
from sme_fraud.release_shadow_plan import VERSION,compile_values
from sme_fraud.case_queue_policy import default_fixture_policy
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.rule_snapshot_features import feature_contract
from sme_fraud.validation_study import run_validation_study
import test_validation_study as validation_support


class ShadowPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validation_support.ValidationStudyTests.setUpClass();cls.fixture=validation_support.ValidationStudyTests
        cls.packages={}
        for company,ctx in cls.fixture.company_ctx.items():
            # Use only real unsupervised artifacts; the fixture's supervised scorer
            # is synthetic and must never enter the executable selected arm.
            plan=deepcopy(ctx['plan'])
            plan['candidates']=[a for a in plan['candidates'] if a['arm_id'] in ('rules_only','rules_plus_ecod')]
            if not any(b['method_id']=='ecod' for b in plan['versions']['model_bindings']):
                art=ctx['model_artifacts']['ecod']
                plan['versions']['model_bindings'].append(dict(method_id='ecod',kind='unsupervised',artifact_id=art['artifact_id'],
                    artifact_sha256=art['artifact_sha256'],model_version='1.0.0',company_id=company,training_split='history_train',training_mechanism='local_enterprise_fit'))
            study=run_validation_study(plan,snapshot_manifests=ctx['manifests'],model_artifacts=ctx['model_artifacts'],
                reference_artifacts=ctx['references'],split_bundles=ctx['bundles'],label_packets=ctx['label_packets'])
            selection=loads((cls.fixture.root/f'bindings-{company}.json').read_bytes())['bindings'][0]
            selection=dict(version='analysis-bindings/1.0.0',**selection)
            cls.packages[company]=dict(version=VERSION,scope=plan['scope'],feature_contract_fingerprint=feature_contract()['fingerprint'],
                model_selection=selection,evaluation_plan=plan,study=study,references=ctx['references'],source_runtime=runtime_signature(),
                case_policy=default_fixture_policy(budget_limit=3,min_case_score=1,rule_weight=1,ml_weight=1),
                ml_candidate_min_score=0.7,fallback_order=['fb_incompatible_contract_v1'],execution_location='enterprise_local_only')

    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=ReleaseStore(self.root/'releases.db',b's'*32)
        self.queue=CaseQueueStore(self.root/'cases.db')
        self.svc=ReleaseService(self.store,self.fixture.snapshots,AnalysisResources(self.fixture.models.path),self.queue)
        self.scope=self.fixture.company_ctx['C001']['scope'];self.package=deepcopy(self.packages['C001'])
        self.sid=self.fixture.company_ctx['C001']['manifests']['sealed_future_test']['snapshot_id']
        self.cutoff=self.package['evaluation_plan']['splits']['sealed_future_test']['as_of']

    def denied(self,code,fn):
        with self.assertRaises(ImportFailure) as error:fn()
        self.assertEqual(error.exception.code,code)

    def candidate(self,name='Linked candidate',package=None):
        p=self.svc.register_plan(self.scope,package or self.package,'register-'+name.replace(' ','-'))
        b=self.svc.prepare(self.scope,self.sid,name,'prepare-'+name.replace(' ','-'),plan_id=p['plan_id'])
        g=self.svc.qualify(self.scope,b['bundle_id'],'staging');self.assertTrue(g['technical_ready'],g)
        a=self.svc.approve(self.scope,b['bundle_id'],g['gate_id'],'staging','Synthetic linked shadow technical approval')
        return dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id'])

    def switch(self,c,revision=0,action='activate'):
        return self.svc.switch(self.scope,dict(c,lane='staging',expected_revision=revision,reason='Linked shadow synthetic '+action,action=action),'switch-linked-'+str(revision))

    def test_real_study_component_pins_and_queue_shadow_end_to_end(self):
        import jsonschema
        c=self.candidate();b=self.store.get(self.scope,c['bundle_id'])
        jsonschema.validate(b,loads((Path(__file__).resolve().parents[1]/'sme_fraud/pipeline_release.schema.json').read_bytes()))
        self.assertEqual(b['version'],'pipeline-release-bundle/1.1.0')
        for slot in compile_values(self.package):self.assertIn('artifact_id',b['components'][slot])
        self.switch(c);r=self.svc.run(self.scope,'linked-shadow-e2e','staging',self.sid,self.cutoff)
        p=r['result']['pipeline'];self.assertEqual(p['bundle_id'],c['bundle_id']);self.assertFalse(p['he_execution'])
        self.assertEqual(len(p['rows']),len(r['result']['rows']));self.assertEqual(p['queue']['mode_namespace'],'shadow')
        self.assertLessEqual(p['queue']['budget_status']['reserved_count'],3)
        self.assertGreater(p['queue']['counts']['total_cases'],0)
        self.assertEqual(len(self.queue.get_queue_state(self.scope,mode='active')['items']),0)
        self.assertIsNotNone(r['metrics']['queue_counts']);self.assertIsNotNone(r['metrics']['fallback_rate'])
        self.assertFalse(self.svc.qualify(self.scope,c['bundle_id'],'production')['production_ready'])

    def test_study_checksum_runtime_model_and_company_rejected(self):
        for kind,code in [('checksum','RELEASE_STUDY_INTEGRITY'),('runtime','RELEASE_STUDY_RUNTIME'),('model','RELEASE_STUDY_MODEL_MISMATCH'),('scope','RELEASE_SCOPE')]:
            p=deepcopy(self.package)
            if kind=='checksum':p['study']['plan_lock']['plan_sha256']='0'*64
            if kind=='runtime':p['source_runtime']['key_requirement']='different'
            if kind=='model':p['study']['detector_validation']['selected_arm']['branches']=['rules_35','lof']
            if kind=='scope':p['scope']['company_id']='C002'
            if kind=='model':
                # Model pin drift is checked against the exact evaluated method.
                p=deepcopy(self.package);p['evaluation_plan']['versions']['model_bindings']=[dict(x,artifact_id='mth_'+'0'*64) if x['method_id']=='ecod' else x for x in p['evaluation_plan']['versions']['model_bindings']]
                # Integrity failures precede model mismatch for a modified plan.
                code='RELEASE_STUDY_BINDING'
            self.denied(code,lambda:self.svc.register_plan(self.scope,p,'bad-'+kind))

    def test_foreign_registered_plan_not_visible_in_other_company(self):
        p=self.svc.register_plan(self.scope,self.package,'scope-plan-one')
        c2=self.fixture.company_ctx['C002'];self.denied('RELEASE_OBJECT_NOT_FOUND',lambda:self.svc.prepare(c2['scope'],c2['manifests']['sealed_future_test']['snapshot_id'],'Foreign','prepare-foreign-plan',plan_id=p['plan_id']))
        self.assertEqual(self.svc.overview(c2['scope'])['plans'],[])

    def test_gate_preview_does_not_reserve_budget_or_create_queue(self):
        self.candidate();self.assertEqual(self.queue.get_queue_state(self.scope,mode='shadow')['items'],[])

    def test_checkpoint_survives_failure_after_queue_commit_no_duplicate_budget(self):
        c=self.candidate();self.switch(c);put=self.store.put
        def fail_observation(conn,scope,kind,value):
            if kind=='observation':raise RuntimeError('Synthetic process loss after queue commit')
            return put(conn,scope,kind,value)
        with patch.object(self.store,'put',side_effect=fail_observation):
            with self.assertRaises(RuntimeError):self.svc.run(self.scope,'queue-commit-crash','staging',self.sid,self.cutoff)
        with closing(sqlite3.connect(self.queue.path)) as conn:
            count=conn.execute("SELECT sum(reserved_count) FROM budget_periods WHERE mode_namespace='shadow'").fetchone()[0]
        service=ReleaseService(ReleaseStore(self.store.path,b's'*32),self.fixture.snapshots,self.svc.resources,self.queue)
        with patch.object(service,'_execute',side_effect=AssertionError('Must reuse durable execution checkpoint')):
            result=service.run(self.scope,'queue-commit-crash','staging',self.sid,self.cutoff)
        self.assertEqual(result['result']['pipeline']['queue']['budget_status']['reserved_count'],count)
        self.assertEqual(len(self.store.list(self.scope,'execution')),1)
        self.assertEqual(len(self.store.list(self.scope,'observation')),1)

    def test_rollback_and_policy_version_change_keep_same_period_quota(self):
        a=self.candidate();self.switch(a)
        first=self.svc.run(self.scope,'before-rollback-run','staging',self.sid,self.cutoff)
        p=deepcopy(self.package);p['case_policy']['policy_version']='fixture-release-two'
        b=self.candidate('Linked second',p);self.switch(b,1)
        second=self.svc.run(self.scope,'different-policy-run','staging',self.sid,self.cutoff)
        self.switch(a,2,'rollback');last=self.svc.run(self.scope,'after-rollback-run','staging',self.sid,self.cutoff)
        reserved=first['result']['pipeline']['queue']['budget_status']['reserved_count']
        self.assertEqual(second['result']['pipeline']['queue']['budget_status']['reserved_count'],reserved)
        self.assertEqual(last['result']['pipeline']['queue']['budget_status']['reserved_count'],reserved)
        self.assertEqual(last['result']['pipeline']['period_key'],first['result']['pipeline']['period_key'])

    def test_explicit_rule_only_plan_never_uses_other_pinned_model(self):
        p=deepcopy(self.package);plan=p['evaluation_plan'];plan['candidates']=[a for a in plan['candidates'] if a['arm_id']=='rules_only']
        ctx=self.fixture.company_ctx['C001'];p['study']=run_validation_study(plan,snapshot_manifests=ctx['manifests'],model_artifacts=ctx['model_artifacts'],
            reference_artifacts=ctx['references'],split_bundles=ctx['bundles'],label_packets=ctx['label_packets'])
        c=self.candidate('Rules only',p);self.switch(c);r=self.svc.run(self.scope,'rules-only-shadow','staging',self.sid,self.cutoff)
        self.assertTrue(all(x['ml_normalized_score'] is None and x['ml_raw_score'] is None for x in r['result']['pipeline']['case_bundle']['records']))

    def test_hard_process_exit_after_queue_commit_recovers_exact_checkpoint(self):
        c=self.candidate();self.switch(c)
        info=dict(release=str(self.store.path),queue=str(self.queue.path),snapshots=str(self.fixture.snapshots.path),models=str(self.fixture.models.path),
                  sid=self.sid,as_of=self.cutoff,actor=self.scope.actor_id)
        path=self.root/'crash-request.json';path.write_bytes(canonical(info))
        script='''
import sys,os,json
from finance_input import AccessScope
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.case_queue_store import CaseQueueStore
class Crash(ReleaseStore):
 def put(self,c,s,k,v):
  if k=='observation':os._exit(77)
  return super().put(c,s,k,v)
i=json.load(open(sys.argv[1]));scope=AccessScope('demo',frozenset({'C001'}),i['actor'],frozenset({'data.import'}))
svc=ReleaseService(Crash(i['release'],b's'*32),SnapshotStore(i['snapshots']),AnalysisResources(i['models']),CaseQueueStore(i['queue']))
svc.run(scope,'hard-queue-process-crash','staging',i['sid'],i['as_of'])
'''
        result=subprocess.run([sys.executable,'-c',script,str(path)],capture_output=True,timeout=60,env=dict(os.environ,PYTHONPATH=os.pathsep.join(sys.path)))
        self.assertEqual(result.returncode,77,result.stderr.decode(errors='replace'))
        with closing(sqlite3.connect(self.queue.path)) as conn:
            before=conn.execute("SELECT sum(reserved_count) FROM budget_periods WHERE mode_namespace='shadow'").fetchone()[0]
        self.svc=ReleaseService(ReleaseStore(self.store.path,b's'*32),self.fixture.snapshots,self.svc.resources,self.queue)
        with patch.object(self.svc,'_execute',side_effect=AssertionError('Hard-crash resume must reuse committed execution')):
            result=self.svc.run(self.scope,'hard-queue-process-crash','staging',self.sid,self.cutoff)
        self.assertEqual(result['result']['pipeline']['queue']['budget_status']['reserved_count'],before)

    def test_reference_calibrator_and_gate_schema_checks(self):
        import jsonschema
        p=deepcopy(self.package);next(iter(p['references'].values()))['sorted_scores'][0]+=1
        self.denied('RELEASE_REFERENCE_INTEGRITY',lambda:self.svc.register_plan(self.scope,p,'reference-integrity'))
        p=deepcopy(self.package);p['study']['calibration_validation']['calibrator']['calibrator_sha256']='0'*64
        p['study']['study_result_sha256']=digest(canonical({k:v for k,v in p['study'].items() if k not in ('execution_costs','study_result_sha256')}))
        self.denied('RELEASE_CALIBRATOR_INTEGRITY',lambda:self.svc.register_plan(self.scope,p,'calibrator-integrity'))
        c=self.candidate();g=self.store.get(self.scope,c['gate_id'])
        jsonschema.validate(g,loads((Path(__file__).resolve().parents[1]/'sme_fraud/pipeline_release_gate.schema.json').read_bytes()))

    def test_runtime_model_missing_does_not_fit_or_silently_use_other_model(self):
        from sme_fraud.release_shadow_plan import score_and_coalesce
        from sme_fraud.snapshot_analysis import analyze_snapshot
        from sme_fraud.pipeline_release import FrozenResources
        analysis=analyze_snapshot(self.fixture.snapshots,self.scope,self.sid,self.cutoff,technical=True,
                                  resources=FrozenResources(self.fixture.models.path,self.package['model_selection']))
        for row in analysis['rows']:
            row['methods']['ecod'].update(available=False,raw_score=None,score=None,reason={'code':'artifact_missing'})
        data=loads(self.fixture.snapshots.get_snapshot(self.scope,self.sid,data=True))
        result=score_and_coalesce(self.scope,analysis,self.fixture.snapshots.get_snapshot(self.scope,self.sid),data,self.package,'rbun_'+'a'*64)
        self.assertTrue(all(r['fallback_id'] in (None,'fb_incompatible_contract_v1') for r in result['rows']))
        self.assertTrue(all(r['ml_raw_score'] is None and r['ml_normalized_score'] is None for r in result['case_bundle']['records']))
        self.assertTrue(all(not r['is_full_ensemble'] for r in result['rows']))

    def test_past_transactions_cannot_use_future_selection_or_calibration(self):
        from sme_fraud.release_shadow_plan import score_and_coalesce
        from sme_fraud.snapshot_analysis import analyze_snapshot
        from sme_fraud.pipeline_release import FrozenResources
        ctx=self.fixture.company_ctx['C001'];sid=ctx['manifests']['detector_validation']['snapshot_id']
        cutoff=self.package['evaluation_plan']['splits']['detector_validation']['as_of']
        a=analyze_snapshot(self.fixture.snapshots,self.scope,sid,cutoff,technical=True,resources=FrozenResources(self.fixture.models.path,self.package['model_selection']))
        r=score_and_coalesce(self.scope,a,self.fixture.snapshots.get_snapshot(self.scope,sid),loads(self.fixture.snapshots.get_snapshot(self.scope,sid,data=True)),self.package,'rbun_'+'a'*64)
        self.assertEqual(len(r['rows']),len(a['rows']))
        self.assertTrue(all(not x['available'] and x['priority_score'] is None and x['experimental_calibrated_probability'] is None and x['fallback_id'] is None for x in r['rows']))

    def test_changed_scores_do_not_resend_same_cases_under_new_release(self):
        a=self.candidate();self.switch(a);first=self.svc.run(self.scope,'score-change-before','staging',self.sid,self.cutoff)
        sent={d['case_id'] for d in first['result']['pipeline']['queue']['decisions'] if d['decision'] in ('selected','mandatory_route')}
        self.assertTrue(sent)
        p=deepcopy(self.package);p['case_policy']['policy_version']='fixture-score-change';p['case_policy']['scoring']['ml_weight']=4
        b=self.candidate('Different score weights',p);self.switch(b,1)
        second=self.svc.run(self.scope,'score-change-after','staging',self.sid,self.cutoff)
        decisions={d['case_id']:d['decision'] for d in second['result']['pipeline']['queue']['decisions']}
        self.assertTrue(all(decisions[c]=='already_notified' for c in sent),decisions)

    def test_budget_period_change_requires_separate_migration(self):
        a=self.candidate();self.switch(a)
        p=deepcopy(self.package);p['case_policy']['budget']['period_kind']='calendar_month_vn'
        b=self.candidate('Month would reset quota',p)
        self.denied('RELEASE_BUDGET_PERIOD_MIGRATION',lambda:self.switch(b,1))
        self.assertEqual(self.store.current(self.scope,'staging')['bundle_id'],a['bundle_id'])

    def test_owner_approved_pilot_active_policy_and_production_lane_gate(self):
        from sme_fraud.case_queue_policy import approved_pilot_policy
        from sme_fraud.release_shadow_plan import make_pilot_governance
        pol=approved_pilot_policy()
        self.assertEqual(pol['budget']['case_budget_limit'],5)
        self.assertEqual(pol['scoring']['min_case_score'],5.0)
        self.assertEqual(pol['scoring']['rule_weight'],1.0)
        self.assertEqual(pol['scoring']['ml_weight'],2.0)
        self.assertEqual(pol['scoring']['mandatory_rules'],['P1'])
        self.assertTrue(pol['fixture_declaration']['approved_for_production'])
        self.assertEqual(pol['fixture_declaration']['open_decision_gates'],[])

        # Without pilot_governance certificate, approved_for_production=True is rejected
        no_cert=deepcopy(self.package);no_cert['case_policy']=deepcopy(pol)
        self.denied('RELEASE_PRODUCTION_BLOCKED',lambda:self.svc.register_plan(self.scope,no_cert,'pilot-missing-cert'))

        # Tampered policy_sha256 in pilot_governance is rejected
        bad_cert=deepcopy(no_cert);bad_cert['pilot_governance']=make_pilot_governance(bad_cert['study'],pol)
        bad_cert['pilot_governance']['policy_sha256']='0'*64
        self.denied('RELEASE_PILOT_GOVERNANCE_INVALID',lambda:self.svc.register_plan(self.scope,bad_cert,'pilot-bad-cert'))

        # Strict unreachable D-09 criteria fails production gate and blocks approval
        strict_pkg=deepcopy(no_cert)
        strict_pkg['pilot_governance']=make_pilot_governance(strict_pkg['study'],pol,min_labeled_test_rows=99)
        strict_reg=self.svc.register_plan(self.scope,strict_pkg,'pilot-strict-d09')
        strict_bun=self.svc.prepare(self.scope,self.sid,'Pilot strict fail','prep-pilot-strict',plan_id=strict_reg['plan_id'])
        strict_gate=self.svc.qualify(self.scope,strict_bun['bundle_id'],'production')
        self.assertFalse(strict_gate['production_ready']);self.assertFalse(strict_gate['technical_ready'])
        self.denied('RELEASE_PRODUCTION_BLOCKED',lambda:self.svc.approve(self.scope,strict_bun['bundle_id'],strict_gate['gate_id'],'production','Should block when D-09 fails'))

        # Valid Owner-Approved Pilot Active package passes production gate, activates, and routes to active_queue with simulated warning
        pilot_pkg=deepcopy(no_cert)
        pilot_pkg['pilot_governance']=make_pilot_governance(pilot_pkg['study'],pol,min_labeled_test_rows=2,min_precision_resolved=0.5,max_false_alerts_per_period=3)
        reg=self.svc.register_plan(self.scope,pilot_pkg,'pilot-valid-d09')
        self.assertTrue(reg['production_ready'])
        bun=self.svc.prepare(self.scope,self.sid,'Pilot Active Release','prep-pilot-valid',plan_id=reg['plan_id'])
        gate=self.svc.qualify(self.scope,bun['bundle_id'],'production')
        self.assertTrue(gate['production_ready'],gate);self.assertTrue(gate['technical_ready'])
        by_name={g['name']:g for g in gate['gates']}
        self.assertEqual(by_name['quality']['status'],'pass')
        self.assertTrue(by_name['quality']['observed']['simulated_source_warning'])
        self.assertEqual(by_name['production_policy']['status'],'pass')
        self.assertEqual(by_name['production_policy']['observed']['closed_decisions'],['D-04','D-05','D-06','D-07'])
        app=self.svc.approve(self.scope,bun['bundle_id'],gate['gate_id'],'production','Owner approved Pilot Active release with simulated warning')
        self.assertEqual(app['scope'],'pilot_active_production')
        sw=self.svc.switch(self.scope,dict(bundle_id=bun['bundle_id'],gate_id=gate['gate_id'],approval_id=app['approval_id'],
                           lane='production',expected_revision=0,reason='Activate Pilot Active bundle',action='activate'),'switch-pilot-prod')
        self.assertEqual(sw['revision'],1);self.assertTrue(self.svc.overview(self.scope)['production_ready'])
        run_res=self.svc.run(self.scope,'pilot-active-run-1','production',self.sid,self.cutoff)
        pipe=run_res['result']['pipeline']
        self.assertEqual(pipe['queue_mode'],'active')
        self.assertEqual(pipe['queue']['mode_namespace'],'active')
        self.assertEqual(pipe['queue']['queue_target'],'active_queue')
        self.assertTrue(pipe['queue']['policy_summary']['approved_for_production'])
        self.assertEqual(pipe['queue']['budget_status']['budget_limit'],5)
        self.assertTrue(pipe.get('simulated_source_warning'))
        self.assertTrue(any(d['decision']=='mandatory_route' for d in pipe['queue']['decisions']))
        self.assertEqual(self.queue.get_queue_state(self.scope,mode='shadow')['items'],[])
        self.assertGreater(len(self.queue.get_queue_state(self.scope,mode='active')['items']),0)
        # Legacy unpinned active delivery endpoint remains blocked
        self.denied('RELEASE_PRODUCTION_BLOCKED',lambda:self.svc.require_new_delivery(self.scope))


if __name__=='__main__':unittest.main()
