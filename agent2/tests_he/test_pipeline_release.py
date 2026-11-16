"""Release metadata acceptance on synthetic data; never a production HE claim."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from training_snapshot_support import scope,native,canonical_source,commit
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.import_files import canonical,digest,ImportFailure
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.pipeline_release import ReleaseService,runtime_signature,SLOTS


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.scope=scope();self.key=b'synthetic-release-only-key-000000'[:32]
        self.clock=[datetime(2026,11,16,tzinfo=timezone.utc)]
        self.snapshots=SnapshotStore(self.root/'snapshots.db');self.data=native();self.sid=commit(self.snapshots,self.data,self.scope)
        self.store=ReleaseStore(self.root/'releases.db',self.key,lambda:self.clock[0]);self.service=ReleaseService(self.store,self.snapshots)

    def candidate(self,name='Candidate A'):
        b=self.service.prepare(self.scope,self.sid,name,'prepare-'+name.replace(' ','-'))
        g=self.service.qualify(self.scope,b['bundle_id'],'staging')
        a=self.service.approve(self.scope,b['bundle_id'],g['gate_id'],'staging','Synthetic staging technical review')
        return dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id'])

    def activate(self,candidate,revision=0,action='activate',key=None):
        return self.service.switch(self.scope,dict(candidate,lane='staging',expected_revision=revision,reason='Synthetic test switch with explicit reason',action=action),key or 'switch-'+str(revision),recheck=lambda:self.scope)

    def denied(self,code,call):
        with self.assertRaises(ImportFailure) as error:call()
        self.assertEqual(error.exception.code,code)

    def test_bundle_schema_all_slots_explicit_and_stable_prepare_receipt(self):
        import jsonschema
        b=self.service.prepare(self.scope,self.sid,'Stable','prepare-stable')
        schema=json.loads((Path(__file__).resolve().parents[1]/'sme_fraud/pipeline_release.schema.json').read_bytes())
        jsonschema.validate(b['bundle'],schema)
        self.assertEqual(set(b['bundle']['components']),set(SLOTS))
        self.clock[0]+=timedelta(seconds=1)
        self.assertEqual(self.service.prepare(self.scope,self.sid,'Stable','prepare-stable'),b)
        self.denied('RELEASE_IDEMPOTENCY_CONFLICT',lambda:self.service.prepare(self.scope,self.sid,'Other','prepare-stable'))
        self.assertTrue(b['bundle']['components']['budget']['unused'])
        self.assertNotIn('latest',canonical(b).decode())

    def test_object_scope_encryption_integrity_and_append_only(self):
        c=self.candidate();self.denied('RELEASE_OBJECT_NOT_FOUND',lambda:self.store.get(scope('C002'),c['bundle_id']))
        # Bytes at rest do not expose config/name/reasons. Tampering fails closed.
        self.assertNotIn(b'Candidate A',self.store.path.read_bytes())
        with closing(sqlite3.connect(self.store.path)) as conn:
            with self.assertRaises(sqlite3.DatabaseError):conn.execute("UPDATE objects SET payload=x'00'")
            conn.execute('DROP TRIGGER release_objects_update');conn.execute("UPDATE objects SET payload=x'00' WHERE id=?",(c['bundle_id'],));conn.commit()
        self.denied('RELEASE_STORAGE_INTEGRITY',lambda:self.store.get(self.scope,c['bundle_id']))

    def test_wrong_key_and_foreign_database_fail_without_reset(self):
        self.candidate();before=digest(self.store.path.read_bytes())
        self.denied('RELEASE_KEY_MISMATCH',lambda:ReleaseStore(self.store.path,b'z'*32))
        self.assertEqual(digest(self.store.path.read_bytes()),before)
        self.denied('RELEASE_STORAGE_VERSION',lambda:ReleaseStore(self.snapshots.path,self.key))

    def test_gates_synthetic_quality_unknown_and_production_blocked(self):
        c=self.candidate();gate=self.service.qualify(self.scope,c['bundle_id'],'production')
        by={r['name']:r for r in gate['gates']}
        self.assertEqual(by['quality']['status'],'blocked');self.assertIsNone(by['quality']['observed']['precision'])
        self.assertIn('D-09',by['production_policy']['observed']['open_decisions'])
        self.assertFalse(gate['production_ready']);self.assertFalse(gate['technical_ready'])
        self.denied('RELEASE_PRODUCTION_BLOCKED',lambda:self.service.approve(self.scope,c['bundle_id'],gate['gate_id'],'production','Synthetic production must stay blocked'))
        self.denied('RELEASE_PRODUCTION_BLOCKED',lambda:self.service.switch(self.scope,dict(c,lane='production',expected_revision=0,reason='Should not bypass gate',action='activate'),'block-production'))
        self.assertEqual(self.store.current(self.scope,'production')['revision'],0)

    def test_model_runtime_and_rule_code_change_blocks_activation_and_rollback(self):
        a=self.candidate();b=self.candidate('Candidate B');self.activate(a);self.activate(b,1)
        changed=runtime_signature();changed['key_requirement']='changed'
        with patch('sme_fraud.pipeline_release.runtime_signature',return_value=changed):
            self.denied('RELEASE_RUNTIME_CHANGED',lambda:self.activate(a,2,'rollback'))
            gate=self.service.qualify(self.scope,a['bundle_id'],'staging')
            self.assertEqual(gate['gates'][0]['status'],'fail')
        self.assertEqual(self.store.current(self.scope,'staging')['bundle_id'],b['bundle_id'])

    def test_expired_gate_and_approval_require_new_review(self):
        c=self.candidate();self.clock[0]+=timedelta(hours=25)
        self.denied('RELEASE_APPROVAL_EXPIRED',lambda:self.activate(c))
        self.denied('RELEASE_GATE_EXPIRED',lambda:self.service.approve(self.scope,c['bundle_id'],c['gate_id'],'staging','Reapproval with old gate'))
        self.assertIsNone(self.store.current(self.scope,'staging')['bundle_id'])

    def test_qualification_and_approval_retry_return_protected_original_receipt(self):
        b=self.service.prepare(self.scope,self.sid,'Retry approval','prepare-approval')
        g=self.service.qualify(self.scope,b['bundle_id'],'staging',key='qualify-retry')
        a=self.service.approve(self.scope,b['bundle_id'],g['gate_id'],'staging','Synthetic retry approval',key='approve-retry')
        self.clock[0]+=timedelta(seconds=10)
        with patch.object(self.service,'_execute',side_effect=AssertionError('must not rerun smoke')):
            self.assertEqual(g,self.service.qualify(self.scope,b['bundle_id'],'staging',key='qualify-retry'))
        self.assertEqual(a,self.service.approve(self.scope,b['bundle_id'],g['gate_id'],'staging','Synthetic retry approval',key='approve-retry'))
        self.assertEqual(len(self.store.list(self.scope,'approval')),1)

    def test_revocation_prevents_old_approval_and_target_activation(self):
        c=self.candidate();self.store.revoke(self.scope,c['approval_id'],'Approval revoked for test')
        self.denied('RELEASE_REVOKED',lambda:self.activate(c))
        self.store.revoke(self.scope,c['bundle_id'],'Bundle revoked for test')
        self.assertEqual(len(self.store.list(self.scope,'revocation')),2)
        self.denied('RELEASE_REVOKED',lambda:self.service.approve(self.scope,c['bundle_id'],c['gate_id'],'staging','Try revoked bundle'))

    def test_gate_approval_cannot_be_reused_for_another_bundle_or_lane(self):
        a=self.candidate();b=self.candidate('Candidate B');b['approval_id']=a['approval_id']
        self.denied('RELEASE_APPROVAL_MISMATCH',lambda:self.activate(b))

    def test_compare_and_swap_two_connections_one_winner_one_conflict(self):
        a=self.candidate();b=self.candidate('Candidate B');barrier=threading.Barrier(2)
        def worker(c,key):
            svc=ReleaseService(ReleaseStore(self.store.path,self.key,lambda:self.clock[0]),self.snapshots)
            barrier.wait()
            try:return svc.switch(self.scope,dict(c,lane='staging',expected_revision=0,reason='Concurrent activation synthetic',action='activate'),key)['revision']
            except ImportFailure as error:return error.code
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda pair:worker(*pair),[(a,'concurrent-one'),(b,'concurrent-two')]))
        self.assertCountEqual(results,[1,'RELEASE_REVISION_CONFLICT'])
        self.assertEqual(len(self.store.list(self.scope,'activation')),1)

    def test_restart_lost_response_retry_and_idempotency_conflict(self):
        a=self.candidate();first=self.activate(a,key='response-lost')
        self.store=ReleaseStore(self.store.path,self.key,lambda:self.clock[0]);self.service=ReleaseService(self.store,self.snapshots)
        self.assertEqual(first,self.activate(a,key='response-lost'))
        self.denied('RELEASE_IDEMPOTENCY_CONFLICT',lambda:self.activate(a,1,key='response-lost'))
        self.assertEqual(self.store.current(self.scope,'staging')['revision'],1)

    def test_hard_process_crash_after_event_insert_rolls_back_whole_switch(self):
        c=self.candidate();request=self.root/'request.json';request.write_bytes(canonical(c))
        script='''
import json,os,sys
from training_snapshot_support import scope
from sme_fraud.pipeline_release_store import ReleaseStore
class CrashStore(ReleaseStore):
 def put(self,c,s,k,v):
  oid=super().put(c,s,k,v)
  if k=='activation':os._exit(73)
  return oid
s=CrashStore(sys.argv[1],b'synthetic-release-only-key-000000'[:32]);v=json.load(open(sys.argv[2]))
s.switch(scope(),'staging',v['bundle_id'],v['approval_id'],v['gate_id'],0,'Hard crash transaction test','hard-crash-request','activate',lambda c:None)
'''
        p=subprocess.run([sys.executable,'-c',script,str(self.store.path),str(request)],capture_output=True,timeout=30,
                         env=dict(os.environ,PYTHONPATH=os.pathsep.join(sys.path)))
        self.assertEqual(p.returncode,73,p.stderr.decode(errors='replace'))
        reopened=ReleaseStore(self.store.path,self.key,lambda:self.clock[0]);self.assertEqual(reopened.current(self.scope,'staging')['revision'],0)
        self.assertEqual(reopened.list(self.scope,'activation'),[])
        self.assertEqual(self.activate(c,key='hard-crash-request')['revision'],1)

    def test_run_pin_survives_switch_restart_and_source_retry_conflict(self):
        a=self.candidate();b=self.candidate('Candidate B');self.activate(a)
        pin=self.store.pin(self.scope,'run-before-crash','staging',dict(snapshot_id=self.sid,as_of=self.data['source']['as_of']))
        self.activate(b,1)
        self.service=ReleaseService(ReleaseStore(self.store.path,self.key,lambda:self.clock[0]),self.snapshots)
        result=self.service.run(self.scope,'run-before-crash','staging',self.sid,self.data['source']['as_of'])
        self.assertEqual(result['bundle_id'],a['bundle_id']);self.assertEqual(result['pin_id'],pin['pin_id'])
        with patch.object(self.service,'_execute',side_effect=AssertionError('must return saved result')):
            self.assertEqual(result,self.service.run(self.scope,'run-before-crash','staging',self.sid,self.data['source']['as_of']))
        self.denied('RELEASE_RUN_CONFLICT',lambda:self.service.run(self.scope,'run-before-crash','staging',self.sid,'2025-08-14T00:00:00+07:00'))

    def test_pointer_switch_during_compute_does_not_change_captured_bundle(self):
        a=self.candidate();b=self.candidate('Candidate B');self.activate(a);execute=self.service._execute
        def switch_and_score(*args,**kwargs):
            self.activate(b,1);return execute(*args,**kwargs)
        with patch.object(self.service,'_execute',side_effect=switch_and_score):
            r=self.service.run(self.scope,'switch-mid-compute','staging',self.sid,self.data['source']['as_of'])
        self.assertEqual(r['bundle_id'],a['bundle_id']);self.assertEqual(self.store.current(self.scope,'staging')['bundle_id'],b['bundle_id'])

    def test_rollback_only_previously_used_bundle_preserves_old_runs(self):
        a=self.candidate();b=self.candidate('Candidate B');c=self.candidate('Never used');self.activate(a);self.activate(b,1)
        self.denied('RELEASE_ROLLBACK_TARGET',lambda:self.activate(c,2,'rollback'))
        back=self.activate(a,2,'rollback');self.assertEqual(back['previous_bundle_id'],b['bundle_id']);self.assertEqual(back['revision'],3)
        self.assertEqual(len(self.store.list(self.scope,'activation')),3)

    def test_source_contract_mismatch_rejected_and_failed_run_pin_kept(self):
        a=self.candidate();self.activate(a);data=canonical_source();sid=commit(self.snapshots,data,self.scope,'canonical-different')
        self.denied('RELEASE_SOURCE_CONFIG_MISMATCH',lambda:self.service.run(self.scope,'different-contract','staging',sid,'2026-10-02T00:00:00+07:00'))
        self.assertEqual(len(self.store.list(self.scope,'pin')),1)

    def test_monitoring_is_per_bundle_null_unknowns_no_auto_training(self):
        c=self.candidate();self.activate(c)
        r=self.service.run(self.scope,'monitoring-run','staging',self.sid,self.data['source']['as_of'])
        self.assertEqual(len(r['result']['rows']),4);m=r['metrics'];self.assertTrue(m['investigation_required'])
        self.assertEqual(m['branches']['ml']['availability_rate'],0);self.assertIsNone(m['verified_precision']);self.assertIsNone(m['fallback_rate'])
        empty=self.service.metrics(dict(rows=[]),0);self.assertIsNone(empty['branches']['ml']['availability_rate'])
        self.assertIsNone(empty['drift']);self.assertFalse((self.root/'models.db').exists())

    def test_current_auth_rechecked_before_commit_and_before_cached_result(self):
        a=self.candidate();other=replace(self.scope,actor_id='different')
        self.denied('AUTH_CONTEXT_CHANGED',lambda:self.service.switch(self.scope,dict(a,lane='staging',expected_revision=0,reason='Revoked actor test',action='activate'),'revoked-scope',recheck=lambda:other))
        self.assertEqual(self.store.current(self.scope,'staging')['revision'],0)

    def test_real_model_preprocess_reference_pinned_and_binding_change_ignored(self):
        from batch_training_support import native_batches
        from sme_fraud.method_store import MethodStore
        from sme_fraud.method_jobs import run_fit_job
        from sme_fraud.analysis_resources import AnalysisResources,VERSION
        data,_=native_batches(tenant='demo');sid=commit(self.snapshots,data,self.scope,'model-source')
        models=MethodStore(self.root/'models.db');auth=SimpleNamespace(authorize=lambda *_:self.scope)
        config=dict(version='company-fit-config/1.0.0',snapshot_id=sid,method_id='ecod',missing_policy='strict',minimum_history=5,
                    profile_id='release-acceptance',evaluation_mode='backtest',selected_columns=['round_million','creator_equals_approver'],
                    history_start='2025-08-11T09:00:00+07:00',history_end='2025-08-11T14:00:00+07:00',reference_start='2025-08-11T14:00:00+07:00',
                    reference_end='2025-08-12T00:00:00+07:00',evaluation_start='2025-08-12T00:00:00+07:00')
        fit=run_fit_job(self.snapshots,models,auth,'synthetic','C001',config,'release-fit-model')
        self.assertEqual(fit['job']['status'],'succeeded',fit)
        identity=fit['job']['artifact_id'];bindings=self.root/'bindings.json'
        doc=dict(version=VERSION,bindings=[dict(tenant_id='demo',company_id='C001',statistics_artifact_id=None,ml_artifacts={'ecod':identity})])
        bindings.write_bytes(canonical(doc));svc=ReleaseService(self.store,self.snapshots,AnalysisResources(models.path,bindings))
        b=svc.prepare(self.scope,sid,'Real pinned model','real-model-prepare');g=svc.qualify(self.scope,b['bundle_id'],'staging')
        self.assertTrue(g['technical_ready'],g)
        a=svc.approve(self.scope,b['bundle_id'],g['gate_id'],'staging','Real adapter synthetic review')
        svc.switch(self.scope,dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id'],lane='staging',expected_revision=0,reason='Pinned model synthetic test',action='activate'),'real-model-activate')
        doc['bindings'][0]['ml_artifacts']={};bindings.write_bytes(canonical(doc))
        result=svc.run(self.scope,'pinned-real-model-run','staging',sid,data['source']['as_of'])
        self.assertGreater(result['metrics']['branches']['ml']['available'],0)
        self.assertEqual(result['result']['bridge_provenance']['model_pins']['ecod'],identity)
        with closing(sqlite3.connect(models.path)) as conn:
            conn.execute('DROP TRIGGER IF EXISTS immutable_method_artifacts_update')
            triggers=conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='method_artifacts'").fetchall()
            for row in triggers:conn.execute('DROP TRIGGER "'+row[0]+'"')
            conn.execute("UPDATE method_artifacts SET payload=x'00'");conn.commit()
        self.denied('MODEL_ARTIFACT_INTEGRITY',lambda:svc.run(self.scope,'tampered-real-model-run','staging',sid,data['source']['as_of']))

    def test_rollback_keeps_real_queue_budget_outbox_task_and_labels(self):
        from test_case_queue import _make_record
        from sme_fraud.case_coalescing import build_case_bundle_from_records
        from sme_fraud.case_queue_policy import default_fixture_policy
        from sme_fraud.case_queue_store import CaseQueueStore
        from sme_fraud.remediation_store import RemediationStore
        from sme_fraud.label_packets import LabelStore
        cq=CaseQueueStore(self.root/'queue.db');rem=RemediationStore(self.root/'tasks.db');labels=LabelStore(self.root/'labels.db',b'l'*32)
        bundle=build_case_bundle_from_records(tenant_id='demo',company_id='C001',snapshot_binding=dict(snapshot_id=self.sid,analysis_id='ana_synthetic',run_id='run_synthetic'),records=[_make_record('T105',invoice_number='HD78',points=9)])
        q=cq.evaluate_and_enqueue(self.scope,bundle,policy=default_fixture_policy(budget_limit=3,min_case_score=7),mode='active',period_key='2026-W45',idempotency_key='existing-queue')
        case=q['decisions'][0]['case_id']
        rem.create_task(self.scope,case_id=case,task_type='request_documents',issue_type='missing_document',title='Synthetic task',what_to_do='Check original source',reason='Source is missing',assignee_kind='department_role',assignee_key='ke_toan_cong_no',idempotency_key='existing-task')
        # Hash logical rows (not WAL headers); no release method gets these stores.
        def state():
            out={}
            for path in (cq.path,rem.path,labels.path,self.snapshots.path):
                with closing(sqlite3.connect(path)) as conn:out[path.name]=digest('\n'.join(conn.iterdump()).encode())
            return out
        before=state();a=self.candidate();b=self.candidate('Candidate B');self.activate(a);self.activate(b,1);self.activate(a,2,'rollback')
        self.assertEqual(state(),before)
        cq.recover_outbox(self.scope,mode='active')
        after=cq.get_queue_state(self.scope,mode='active',redaction='technical')
        self.assertEqual(len(after['items']),1)


class ReleasePortalTests(unittest.TestCase):
    def setUp(self):
        from test_portal_auth import PortalHarness
        from sme_fraud.review_server import make_server
        self.h=PortalHarness().__enter__();self.addCleanup(self.h.__exit__)
        self.h.agent.shutdown();self.h.agent.server_close()
        self.store=ReleaseStore(self.h.root/'release.db',b'p'*32);self.service=ReleaseService(self.store,self.h.store,self.h.resources)
        self.h.agent=make_server(0,self.h.authorizer,self.h.store,self.h.resources,release_service=self.service)
        from portal import server as portal
        portal.CFG['agents']['agent2']['port']=self.h.agent.server_port
        t=threading.Thread(target=self.h.agent.serve_forever,daemon=True);t.start();self.h.threads.append(t)

    def req(self,action='',body=None,company='C002',key='portal-release-request'):
        return self.h.request(self.h.url('pipeline-releases'+('/'+action if action else ''),company),body,headers={'Idempotency-Key':key+'-'+action.replace('/','-')[:20]})

    def test_portal_director_roundtrip_and_production_block(self):
        s=scope('C002');s=replace(s,actor_id='portal-reviewer');data=native('C002');sid=commit(self.h.store,data,s)
        status,b=self.req('prepare',dict(snapshot_id=sid,name='Portal synthetic release'));self.assertEqual(status,200,b)
        status,g=self.req('qualify',dict(bundle_id=b['bundle_id'],lane='staging'));self.assertEqual(status,200,g)
        status,a=self.req('approve',dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],lane='staging',reason='Portal staging synthetic approval'));self.assertEqual(status,200,a)
        body=dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id'],lane='staging',expected_revision=0,reason='Portal staging activate',action='activate')
        status,v=self.req('switch',body);self.assertEqual(status,200,v);self.assertEqual(v['revision'],1)
        status,r=self.req('runs',dict(run_id='portal-release-run',lane='staging',snapshot_id=sid,as_of=data['source']['as_of']));self.assertEqual(status,200,r);self.assertEqual(r['result']['row_count'],4)
        status,state=self.req();self.assertEqual(status,200);self.assertEqual(len(state['runs']),1);self.assertFalse(state['production_ready'])
        self.assertEqual(self.req('approve',dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],lane='production',reason='Production must be blocked'))[0],409)

    def test_accountant_cross_company_no_session_and_extra_pass_flags_denied(self):
        self.assertEqual(self.req(company='C001')[0],403)
        self.assertEqual(self.req(company='OTHER')[0],403)
        self.assertEqual(self.h.request(self.h.url('pipeline-releases','C002'),token=False)[0],401)
        status,r=self.req('qualify',dict(bundle_id='rbun_'+'0'*64,lane='production',passed=True))
        self.assertEqual(status,400);self.assertEqual(r['errors'][0]['code'],'RELEASE_FIELDS')
        self.assertEqual(self.req('objects/rbun_'+'0'*64)[0],404)

    def test_bridge_exact_allowlist_static_page_and_technical_assets(self):
        from portal.agent2_bridge import allowed_path
        for path in ('/pipeline-releases','/assets/pipeline-releases.js','/assets/pipeline-releases.css'):
            self.assertTrue(allowed_path(path));self.assertEqual(self.h.request('/agent2'+path)[0],200)
        for path in ('/pipeline-releases/../keys','/api/v1/companies/C002/pipeline-releases/artifacts','/api/v1/companies/C002/pipeline-releases/objects/rart_'+'0'*64):
            self.assertFalse(allowed_path(path))

    def test_active_queue_cannot_bypass_release_via_legacy_endpoint(self):
        for action,body in [('evaluate',dict(mode='active',period_key='synthetic-period')),('reevaluate-backlog',dict(mode='active',target_period_key='synthetic-period'))]:
            status,v=self.h.request(self.h.url('case-queue/'+action,'C002'),body,headers={'Idempotency-Key':'guard-active-'+action})
            self.assertEqual(status,409,v);self.assertEqual(v['errors'][0]['code'],'RELEASE_PRODUCTION_BLOCKED')
        status,_=self.h.request(self.h.url('case-queue/active','C002'));self.assertEqual(status,200)


if __name__=='__main__':unittest.main()
