"""Bundle/HE integration contracts with synthetic transport; native FHE has a separate receipt."""
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from sme_fraud.bundle_he import BundleHE,adapt,MODE
from sme_fraud.import_files import canonical,ImportFailure
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from experiments.he4.coordinator import FourJobs,Settings
from experiments.he_inference.enterprise_server import EnterpriseNode
import test_release_shadow_plan as release_support
import test_he4_rule_snapshot_coordinator as he_support


class TestBridge(he_support._SyntheticBridge):
    """Only test code uses clear circuit transport. Never configured in production."""
    def public_context(self,scope,bundle):
        from experiments.he_inference.protocol import HEUnavailable
        import hashlib,json
        from pathlib import Path
        m=json.loads((Path(bundle)/'manifest.json').read_bytes());profile=m['profile']
        if profile in self.missing_profiles:raise HEUnavailable('he4_key_not_provisioned')
        binding=dict(tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),profile=profile,
                     circuit_sha256=m['files']['server.zip'],specs_sha256=m['files']['client.specs.json'])
        return dict(binding=binding,key_epoch='key_'+hashlib.sha256((profile+binding['company_id']).encode()).hexdigest(),
                    evaluation_keys_sha256=he_support.sha((Path(bundle)/'client.specs.json').read_bytes()))


class Fixture:
    def __init__(self,owner,*,workers=0,bridge=None):
        self.h=release_support.ShadowPlanTests();self.h.setUp();owner.addCleanup(self.h.doCleanups)
        self.he=he_support.RuleSnapshotCoordinatorTests();self.he.setUp();owner.addCleanup(self.he.doCleanups)
        self.scope=self.he.auth.authorize('Bearer '+self.he.director_tok,'C001');self.h.scope=self.scope
        self.svc=self.h.svc;self.store=self.h.store;self.header='Bearer '+self.he.director_tok
        self.bridge=bridge or TestBridge();self.settings=Settings(self.he.config_v1_1)
        self.node=EnterpriseNode(self.he.auth,self.svc.resources.model_db,self.h.fixture.snapshots.path,
            self.settings.config['worker_url'],self.he.worker_hex,self.he.prov_key)
        self.node.enable_jobs(self.he.root/'legacy',self.he.state_key,required_provider='windows-dpapi-current-user')
        self.node.jobs=FourJobs(self.node,self.settings,workers=workers,bridge=self.bridge)
        owner.addCleanup(lambda:self.node.jobs.close())
        self.backend=SimpleNamespace(node=self.node,settings=self.settings)
        self.svc.he_executor=BundleHE(self.backend)
        self.sids={};self.data={}
        for company in ('C001','C002'):
            scope=self.he.auth.authorize(self.header,company)
            # New synthetic acceptance period, strictly after the fixture's frozen validation.
            data=he_support.json.loads(he_support.json.dumps(he_support._multi_company_snapshot(company,company=='C001')).replace('2025-','2028-'))
            he_support.tp._rehash(data['source'])
            self.data[company]=data
            self.sids[company]=he_support.tp._commit(self.h.fixture.snapshots,scope,data,'bundle-he-'+company+'-'+uuid.uuid4().hex)
        self.sid=self.sids['C001'];self.at=self.data['C001']['source']['as_of']

    def activate(self,company='C001',he=True):
        scope=self.he.auth.authorize(self.header,company);self.h.scope=scope
        reg=self.svc.register_plan(scope,release_support.ShadowPlanTests.packages[company],'register-he-plan-'+company)
        b=self.svc.prepare(scope,self.sids[company],'HE native shadow '+company,'prepare-he-'+company,plan_id=reg['plan_id'],
                           execution_mode=MODE if he else 'enterprise_local_only')
        gate=self.svc.qualify(scope,b['bundle_id'],'staging')
        if not gate['technical_ready']:raise AssertionError(gate)
        app=self.svc.approve(scope,b['bundle_id'],gate['gate_id'],'staging','Synthetic staging only; no production or HE quality claim')
        self.svc.switch(scope,dict(bundle_id=b['bundle_id'],gate_id=gate['gate_id'],approval_id=app['approval_id'],lane='staging',
                                  expected_revision=0,reason='Synthetic HE integration acceptance',action='activate'),'activate-he-'+company)
        return b

    def run(self,run='bundle-he-test',company='C001',**kwargs):
        scope=self.he.auth.authorize(self.header,company)
        return self.svc.run(scope,run,'staging',self.sids[company],self.data[company]['source']['as_of'],lambda:scope,
                            execution_mode=MODE,he_header=self.header,**kwargs)

    def jobs(self):
        with self.node.jobs.store.transaction() as c:return [r[0] for r in c.execute('SELECT id FROM jobs ORDER BY created,id')]


class BundleHETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):release_support.ShadowPlanTests.setUpClass()
    @classmethod
    def tearDownClass(cls):release_support.ShadowPlanTests.tearDownClass()
    def setUp(self):
        self.f=Fixture(self);self.stack=ExitStack();self.addCleanup(self.stack.close)
        up,down,post=self.f.he._mock_worker_handlers()
        for name,fn in [('upload',up),('download',down),('post',post)]:self.stack.enter_context(patch('experiments.he4.coordinator.'+name,side_effect=fn))
    def denied(self,code,fn):
        with self.assertRaises(ImportFailure) as cm:fn()
        self.assertEqual(cm.exception.code,code)
    def finish(self):
        job=self.f.jobs()[0];self.assertFalse(self.f.node.jobs._process(self.f.scope,job));return job

    def test_cloud_dispatch_to_common_queue_review_and_replay_no_clear_executor(self):
        f=self.f;b=f.activate()
        with patch.object(f.svc,'_execute',side_effect=AssertionError('Clear scoring forbidden for HE run')):
            self.denied('PIPELINE_RUN_PENDING',f.run);self.assertEqual(len(f.jobs()),1)
            job=self.finish();result=f.run();again=f.run();self.assertEqual(result,again)
        r=result['result'];self.assertTrue(r['he_execution']);self.assertEqual(r['row_count'],3)
        self.assertEqual(r['execution']['cloud_he']['job_id'],job);self.assertFalse(r['execution']['plaintext_cloud_upload'])
        p=r['pipeline'];self.assertTrue(p['he_execution']);self.assertEqual(p['execution_location'],MODE)
        self.assertTrue(p['review_packet_id']);self.assertEqual(p['queue']['mode_namespace'],'shadow')
        self.assertEqual(len(f.store.list(f.scope,'execution')),1);self.assertEqual(len(f.store.list(f.scope,'observation')),1)
        for row in r['rows']:
            self.assertEqual(len(row['rule_coverage']['rules']),35)
            for name in ('statistics','ml'):self.assertFalse(row['branches'][name]['available'])
            self.assertGreaterEqual(row['rule_coverage']['summary']['unavailable'],23)
        self.assertEqual(len(r['scope_results']),7)
        self.assertTrue(all(not item['available'] for item in r['scope_results']))
        target=next(x for x in r['rows'] if x['transaction_id']=='AUDIT_0000')
        self.assertEqual(next(x for x in target['rule_coverage']['rules'] if x['rule_id']=='P1')['score'],20)
        packet=f.svc.workspace.report(f.scope,'bundle-he-test')
        self.assertEqual(packet['bundle_id'],b['bundle_id']);self.assertTrue(packet['he_execution']);self.assertFalse(packet['training_eligible'])
        self.assertFalse(any(row['is_full_ensemble'] or row['is_selected_arm_complete'] for row in p['rows']))
        self.assertEqual(f.h.queue.get_queue_state(f.scope,mode='active')['items'],[])
        self.denied('RELEASE_RUN_CONFLICT',lambda:f.svc.run(f.scope,'bundle-he-test','staging',f.sid,f.at))

    def test_local_bundle_and_missing_credentials_cannot_start_cloud_or_fallback(self):
        f=self.f;f.activate(he=False)
        self.denied('PIPELINE_HE_UNAVAILABLE',f.run);self.assertEqual(f.jobs(),[])

    def test_bundle_key_or_settings_drift_blocks_before_submission(self):
        f=self.f;f.activate();f.bridge.missing_profiles.add('graph')
        self.denied('PIPELINE_HE_CONTEXT_CHANGED',f.run);self.assertEqual(f.jobs(),[])

    def test_missing_profile_keys_keep_only_supported_parts_available(self):
        f=self.f;f.bridge.missing_profiles.update({'graph','c3'});f.activate()
        self.denied('PIPELINE_RUN_PENDING',f.run);self.finish();r=f.run()['result']
        row=next(x for x in r['rows'] if x['transaction_id']=='AUDIT_0000')
        entries={x['rule_id']:x for x in row['rule_coverage']['rules']}
        self.assertEqual(entries['P1']['status'],'evaluated_hit')
        self.assertEqual(entries['C3']['status'],'unavailable');self.assertEqual(entries['B1']['status'],'unavailable')

    def test_restart_before_dispatch_link_and_after_queue_commit_reuses_same_job(self):
        f=self.f;f.activate();original=f.store.put
        def crash(c,s,k,v):
            if k=='he_job':raise RuntimeError('DN crash after HE child creation')
            return original(c,s,k,v)
        with patch.object(f.store,'put',side_effect=crash):
            with self.assertRaises(RuntimeError):f.run()
        job=f.jobs()[0]
        self.denied('PIPELINE_RUN_PENDING',f.run);self.assertEqual(f.jobs(),[job]);self.finish()
        def crash_after_queue(c,s,k,v):
            if k=='observation':raise RuntimeError('DN crash after queue commit')
            return original(c,s,k,v)
        with patch.object(f.store,'put',side_effect=crash_after_queue):
            with self.assertRaises(RuntimeError):f.run()
        restarted=ReleaseService(ReleaseStore(f.store.path,b's'*32),f.svc.snapshots,f.svc.resources,f.svc.case_queue)
        restarted.he_executor=BundleHE(f.backend);f.svc=restarted
        with patch.object(restarted.he_executor,'execute',side_effect=AssertionError('Must reuse complete execution checkpoint')):
            result=f.run()
        self.assertTrue(result['result']['pipeline']['review_packet_id']);self.assertEqual(f.jobs(),[job])

    def test_result_source_tamper_does_not_reach_case_budget(self):
        f=self.f;f.activate();self.denied('PIPELINE_RUN_PENDING',f.run);job=self.finish()
        row,saved=f.node.jobs.store.get(f.scope,job);saved['result']['data_checksum']='0'*64
        f.node.jobs.store.save(f.scope,job,saved,'completed')
        self.denied('PIPELINE_HE_RESULT_BINDING',f.run)
        self.assertEqual(f.h.queue.get_queue_state(f.scope,mode='shadow')['items'],[])

    def test_simultaneous_payment_keeps_native_mandatory_trigger(self):
        from datetime import datetime,timedelta,timezone
        from sme_fraud.rule_snapshot import analyze
        f=self.f;c=he_support.tp.Case();c.at=datetime(2025,8,12,11,tzinfo=timezone(timedelta(hours=7)))
        c.tables['employees']=[c.director,c.maker,c.worker];c.tables['vendors']=[c.vendor]
        c.pay(c.at-timedelta(days=1),4_000_000,invoice_number='SIM_GROUP',invoice_gross_vnd=10_000_000)
        a=c.pay(c.at,4_000_000,invoice_number='SIM_GROUP',invoice_gross_vnd=10_000_000)
        b=c.pay(c.at,4_000_000,invoice_number='SIM_GROUP',invoice_gross_vnd=10_000_000)
        he_support.tp.authorities(c);source=he_support.tp.finish(c,'C001');source['tenant_id']='demo'
        data=he_support.tp._wrap(source,[a['transaction_id'],b['transaction_id']])
        data=he_support.json.loads(he_support.json.dumps(data).replace('2025-','2028-'));he_support.tp._rehash(data['source'])
        f.sid=f.sids['C001']=he_support.tp._commit(f.h.fixture.snapshots,f.scope,data,'he-group-'+uuid.uuid4().hex)
        f.data['C001']=data;f.at=data['source']['as_of'];f.activate()
        native=analyze(f.svc.snapshots,f.scope,f.sid,f.at,technical=True)
        reference=next(e for r in native['catalogue_results'] if r['rule_id']=='P1' for e in r.get('groups',[]) if e.get('signal'))
        self.assertTrue(reference['hard_trigger'])
        self.denied('PIPELINE_RUN_PENDING',f.run);self.finish();result=f.run()['result']
        for record in result['pipeline']['case_bundle']['records']:
            hit=next(h for h in record['actionable_hits'] if h['rule_id']=='P1')
            self.assertEqual(hit['points'],reference['points']);self.assertEqual(hit['hard_trigger'],bool(reference['hard_trigger']))

    def test_durable_fourjobs_restart_keeps_envelope_epoch_and_binding(self):
        f=self.f;f.activate();self.denied('PIPELINE_RUN_PENDING',f.run);job=f.jobs()[0]
        f.he.lose_reply=True;self.assertTrue(f.node.jobs._process(f.scope,job))
        _,before=f.node.jobs.store.get(f.scope,job)
        packet=next(t['packet'] for t in before['pending']['tasks'] if t['packet'] is not None)
        f.node.jobs.close()
        f.node.enable_jobs(f.he.root/'legacy',f.he.state_key,required_provider='windows-dpapi-current-user')
        f.node.jobs=FourJobs(f.node,f.settings,workers=0,bridge=f.bridge)
        f.svc.he_executor=BundleHE(f.backend);f.he.lose_reply=False
        self.denied('PIPELINE_RUN_PENDING',f.run);self.finish();result=f.run()
        self.assertEqual(f.jobs(),[job]);self.assertTrue(result['result']['he_execution'])
        self.assertIn(('results',packet['payload']['session_id']),f.he.worker_log)

    def test_portal_http_workspace_admits_pending_then_resumes_same_he_job(self):
        import threading
        from test_portal_auth import PortalHarness,portal
        from sme_fraud.review_server import make_server
        f=self.f;f.activate()
        with PortalHarness() as h:
            f.node.auth=h.authorizer
            h.agent.shutdown();h.agent.server_close()
            h.agent=make_server(0,h.authorizer,f.svc.snapshots,f.svc.resources,he_backend=f.backend,
                                case_queue_store=f.svc.case_queue,release_service=f.svc)
            portal.CFG['agents']['agent2']['port']=h.agent.server_port
            t=threading.Thread(target=h.agent.serve_forever,daemon=True);t.start();h.threads.append(t)
            root=h.url('pipeline-workspace');body=dict(run_id='portal-he-common-run',snapshot_id=f.sid,execution_mode=MODE)
            status,view=h.request(root);self.assertEqual(status,200,view);self.assertIn(MODE,view['execution_modes'])
            status,pending=h.request(root+'/runs',body);self.assertEqual(status,409,pending)
            self.assertEqual(pending['errors'][0]['code'],'PIPELINE_RUN_PENDING')
            scope=h.authorizer.authorize('Bearer '+h.token,'C001');job=f.jobs()[0]
            f.node.jobs._process(scope,job)
            status,report=h.request(root+'/runs',body);self.assertEqual(status,200,report)
            self.assertTrue(report['he_execution']);self.assertEqual(report['execution_location'],MODE)
            self.assertEqual(report['run_id'],body['run_id']);self.assertEqual(f.jobs(),[job])
            self.assertEqual(h.request(root+'/runs',body,token=False)[0],401)
            self.assertEqual(h.request(root.replace('/C001/','/C002/')+'/runs/'+body['run_id'])[0],404)

    def test_second_company_and_transient_auth_are_isolated(self):
        f=self.f;f.activate();self.denied('PIPELINE_RUN_PENDING',f.run)
        scope=f.he.auth.authorize(f.header,'C002')
        self.denied('RELEASE_NO_ACTIVE_BUNDLE',lambda:f.run(company='C002'))
        f.activate('C002');self.denied('PIPELINE_RUN_PENDING',lambda:f.run(company='C002'))
        self.assertEqual(len(f.jobs()),2)
        for job in f.jobs():
            try:row,saved=f.node.jobs.store.get(scope,job)
            except Exception:continue
            self.assertEqual(saved['request']['bundle_binding']['company_id'],'C002')
            self.assertNotIn(f.header,canonical(saved).decode())

    def test_extended_he_covers_a6_c2_and_2col_robust_z_statistics(self):
        from datetime import datetime,timedelta
        from sme_fraud.bundle_release_acceptance import TZ,_build_split_snapshot,commit_snapshot
        from sme_fraud.method_jobs import run_fit_job
        from sme_fraud.method_store import MethodStore
        from sme_fraud.rule_snapshot import analyze as analyze_rule_snapshot
        from sme_fraud.pipeline_release import FrozenResources
        f=self.f;scope=f.scope
        # 1. Fit a 2-column RobustZ artifact matching rule-snapshot-point-in-time/1.0.0 so build-statistics-v1 runs in FHE
        fit_end=datetime(2026,8,24,23,59,59,tzinfo=TZ)
        fit_raw,_=_build_split_snapshot('C001','HE4_STAT_FIT',datetime(2026,7,2,10,0,tzinfo=TZ),fit_end,[])
        fit_man=commit_snapshot(f.svc.snapshots,scope,fit_raw,'he4-stat-fit-c001')
        rz_cfg=dict(version='company-fit-config/1.0.0',snapshot_id=fit_man['snapshot_id'],method_id='robust_z',
            missing_policy='strict',minimum_history=10,profile_id='he4-stat-2col',evaluation_mode='backtest',
            selected_columns=['log_abs_amount','round_million'],history_start='2026-07-01T00:00:00+07:00',
            history_end='2026-08-15T23:59:59+07:00',reference_start='2026-08-16T00:00:00+07:00',
            reference_end=fit_end.isoformat(),evaluation_start='2026-08-25T00:00:00+07:00')
        mstore=MethodStore(f.svc.resources.model_db)
        rz_job=run_fit_job(f.svc.snapshots,mstore,f.he.auth,f.header,'C001',rz_cfg,'he4-fit-rz2col')
        self.assertEqual(rz_job['job']['status'],'succeeded',rz_job)
        pkg=deepcopy(release_support.ShadowPlanTests.packages['C001'])
        pkg['model_selection']['statistics_artifact_id']=rz_job['job']['artifact_id']

        # 2. Build evaluation snapshot with A6 hit, A6 non-rounded no-hit, C2 hit, C2 permitted (suppressed), and C3 fast-approval hit
        ev_start=datetime(2028,9,2,9,0,tzinfo=TZ);ev_end=datetime(2028,9,10,23,59,59,tzinfo=TZ)
        specs=[
            dict(id='HE_A6_HIT',pattern='a6_rounded',day_offset=1,hour_offset=9),
            dict(id='HE_A6_NOHIT',pattern='clean',day_offset=1,hour_offset=11,amount=7_500_125),
            dict(id='HE_C2_HIT',pattern='c2_self',day_offset=2,hour_offset=10,amount=16_000_000),
            dict(id='HE_C2_PERM',pattern='c2_self',day_offset=3,hour_offset=10,amount=500_000),
            dict(id='HE_C3_HIT',pattern='clean',day_offset=4,hour_offset=10,amount=55_000_000),
        ]
        ev_raw,_=_build_split_snapshot('C001','HE4_EXT_EVAL',ev_start,ev_end,specs)
        for cov_rec in ev_raw['source']['tables'].get('approval_authority_coverage',[]):
            cov_rec['covered_through']='2029-12-31'
        for auth_rec in ev_raw['source']['tables'].get('approval_authorities',[]):
            auth_rec['effective_to']='2029-12-31'
        director_id=next(e['employee_id'] for e in ev_raw['source']['tables']['employees'] if e.get('role')=='director')
        for tx in ev_raw['source']['tables']['transactions']:
            if tx['transaction_id']=='HE_A6_NOHIT':
                tx['invoice_gross_vnd']=7_489_123
            elif tx['transaction_id']=='HE_C3_HIT':
                tx['approver_id']=director_id
                tx['created_at']='2028-09-06T10:10:00+07:00'
                tx['approved_at']='2028-09-06T10:10:15+07:00'
        for doc in ev_raw['source']['tables']['transaction_documents']:
            if doc['transaction_id']=='HE_A6_NOHIT':
                doc['invoice_gross_vnd']=7_489_123
        he_support.tp._rehash(ev_raw['source'])
        ev_man=commit_snapshot(f.svc.snapshots,scope,ev_raw,'he4-ext-eval-c001')

        reg=f.svc.register_plan(scope,pkg,'reg-he-ext-2col')
        b=f.svc.prepare(scope,ev_man['snapshot_id'],'HE extended 7-rule + stats','prep-he-ext-2col',plan_id=reg['plan_id'],execution_mode=MODE)
        gate=f.svc.qualify(scope,b['bundle_id'],'staging');self.assertTrue(gate['technical_ready'],gate)
        app=f.svc.approve(scope,b['bundle_id'],gate['gate_id'],'staging','Extended HE 7-rule + 2col RobustZ staging approval')
        f.svc.switch(scope,dict(bundle_id=b['bundle_id'],gate_id=gate['gate_id'],approval_id=app['approval_id'],lane='staging',
                                expected_revision=0,reason='Activate extended HE bundle',action='activate'),'act-he-ext-2col')

        with patch.object(f.svc,'_execute',side_effect=AssertionError('Clear scoring forbidden for HE run')):
            self.denied('PIPELINE_RUN_PENDING',lambda:f.svc.run(scope,'he-ext-run-1','staging',ev_man['snapshot_id'],ev_end.isoformat(),
                        lambda:scope,execution_mode=MODE,he_header=f.header))
            job_id=f.jobs()[-1];self.assertFalse(f.node.jobs._process(scope,job_id))
            he_obs=f.svc.run(scope,'he-ext-run-1','staging',ev_man['snapshot_id'],ev_end.isoformat(),
                             lambda:scope,execution_mode=MODE,he_header=f.header)

        clear_res=analyze_rule_snapshot(f.svc.snapshots,scope,ev_man['snapshot_id'],ev_end.isoformat(),technical=True,
            resources=FrozenResources(f.svc.resources.model_db,pkg['model_selection']))
        clear_by_id={r['transaction_id']:r for r in clear_res['rows']}
        he_res=he_obs['result']
        self.assertTrue(he_res['execution']['cloud_branches']['statistics']['available'])
        he_by_id={r['transaction_id']:r for r in he_res['rows']}

        # Verify all 7 covered rules (P1, A6, C2, C3, B1, B5, E4) + 2-col RobustZ statistics exact parity with clear 35-rule engine
        for tid in ('HE_A6_HIT','HE_A6_NOHIT','HE_C2_HIT','HE_C2_PERM','HE_C3_HIT'):
            hr=he_by_id[tid];cr=clear_by_id[tid]
            if tid!='HE_C3_HIT':
                self.assertTrue(hr['branches']['statistics']['available'],hr['branches']['statistics'])
                self.assertTrue(hr['methods']['robust_z']['available'],hr['methods']['robust_z'])
                self.assertAlmostEqual(hr['methods']['robust_z']['score'],cr['methods']['robust_z']['score'],places=3)
                self.assertAlmostEqual(hr['methods']['robust_z']['raw_score'],cr['methods']['robust_z']['raw_score'],places=2)
            else:
                # 55M on tight 1.05M-1.55M history exceeds 15-bit quantized |z|*1024 <= 16383 -> fails closed cleanly
                self.assertFalse(hr['branches']['statistics']['available'])
                self.assertEqual(hr['branches']['statistics']['reason']['code'],'he_statistics_out_of_domain')
            h_rules={x['rule_id']:x for x in hr['rule_coverage']['rules']}
            c_rules={x['rule_id']:x for x in cr['rule_coverage']['rules']}
            for rid in ('P1','A6','C2','C3','B1','B5','E4'):
                self.assertEqual(h_rules[rid]['status'],c_rules[rid]['status'],(tid,rid,h_rules[rid],c_rules[rid]))
                self.assertEqual(h_rules[rid]['matched'],c_rules[rid]['matched'],(tid,rid))
                self.assertEqual(h_rules[rid]['score'],c_rules[rid]['score'],(tid,rid))
        self.assertEqual(next(x for x in he_by_id['HE_A6_HIT']['rule_coverage']['rules'] if x['rule_id']=='A6')['status'],'evaluated_hit')
        self.assertEqual(next(x for x in he_by_id['HE_A6_NOHIT']['rule_coverage']['rules'] if x['rule_id']=='A6')['status'],'evaluated_no_hit')
        self.assertEqual(next(x for x in he_by_id['HE_C2_HIT']['rule_coverage']['rules'] if x['rule_id']=='C2')['status'],'evaluated_hit')
        self.assertEqual(next(x for x in he_by_id['HE_C2_HIT']['rule_coverage']['rules'] if x['rule_id']=='C2')['score'],20)
        self.assertEqual(next(x for x in he_by_id['HE_C2_PERM']['rule_coverage']['rules'] if x['rule_id']=='C2')['status'],'evaluated_no_hit')
        self.assertEqual(next(x for x in he_by_id['HE_C3_HIT']['rule_coverage']['rules'] if x['rule_id']=='C3')['status'],'evaluated_hit')


if __name__=='__main__':unittest.main()
