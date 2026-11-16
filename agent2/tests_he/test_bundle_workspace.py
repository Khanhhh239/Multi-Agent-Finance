"""End-to-end immutable bundle -> case queue -> company review -> business report."""
from copy import deepcopy
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import base64
import csv
import io
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch

from sme_fraud.import_files import canonical,digest,ImportFailure
from sme_fraud.bundle_reviews import CompanyReviewStore,csv_report
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.snapshot_features import utc
from sme_fraud.remediation_store import RemediationStore
import test_release_shadow_plan as support


class BundleWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):support.ShadowPlanTests.setUpClass()
    @classmethod
    def tearDownClass(cls):support.ShadowPlanTests.tearDownClass()

    def setUp(self):
        self.h=support.ShadowPlanTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.scope=self.h.scope;self.svc=self.h.svc;self.work=self.svc.workspace
        self.clock=[100.0]
        self.work._reviews=CompanyReviewStore(self.h.store.path.with_name(self.h.store.path.stem+'-reviews.sqlite3'),self.h.store.review_key,lambda:self.clock[0])
        c=self.h.candidate();self.h.switch(c)
        self.run_id='bundle-review-test-run';self.result=self.svc.run(self.scope,self.run_id,'staging',self.h.sid,self.h.cutoff)
        self.report=self.work.report(self.scope,self.run_id);self.case=self.report['cases'][0]

    def denied(self,code,call):
        with self.assertRaises(ImportFailure) as error:call()
        self.assertEqual(error.exception.code,code)

    def feedback(self,outcome='inconclusive'):
        return dict(outcome=outcome,usefulness='not_assessed',explanation='Synthetic review of source records only',action='Request original records',missing_materials='Original invoice not available',evidence_ids=[],checks_completed=False)

    def save(self,feedback=None,request='review-save-one',scope=None,expected=0):
        scope=scope or self.scope
        lease=self.work.action(scope,self.run_id,self.case['review_id'],'start',{})['lease'];self.clock[0]+=5
        body=dict(expected_revision=expected,lease=lease,request_id=request,feedback=feedback or self.feedback())
        return self.work.action(scope,self.run_id,self.case['review_id'],'save',body),body

    def test_complete_run_has_packet_and_business_trace_no_algorithm_dto(self):
        result=self.result['result'];packet_id=result['pipeline']['review_packet_id']
        self.assertTrue(packet_id.startswith('rpkt_'));self.assertEqual(len(self.report['cases']),3)
        self.assertEqual(self.report['summary']['pending_cases'],3)
        for key in ('snapshot_id','run_id','bundle_id'):self.assertEqual(self.report[key],self.result[key])
        self.assertFalse(self.report['training_eligible']);self.assertIsNone(self.report['summary']['verified_fraud_precision'])
        text=json.dumps(self.report)
        for private in ('ecod','selected_arm','rule_weight','model_selection','rule_coverage','calibrated_fraud_probability'):
            self.assertNotIn(private,text)
        self.assertTrue(all(e['original_verified'] is False and e['source_kind']=='simulated' for c in self.report['cases'] for e in c['evidence']))
        for c in self.report['cases']:
            self.assertFalse(set(c['candidate_ids'])&set(c['evidence_transaction_ids']))
            for e in c['evidence']:
                r=e['record']
                for clock in ('observed_at','recorded_at','posted_at','effective_at'):
                    if r.get(clock):self.assertLessEqual(utc(r[clock]),utc(self.report['as_of']))

    def test_review_saved_with_server_time_and_does_not_generate_fraud_label(self):
        before=digest(self.h.fixture.snapshots.get_snapshot(self.scope,self.h.sid,data=True))
        labels_before=self.h.fixture.labels_store.list(self.scope)
        value,_=self.save();self.assertEqual(value['revision'],1);self.assertEqual(value['active_seconds'],5)
        report=self.work.report(self.scope,self.run_id)
        self.assertEqual(report['summary']['reviewed_cases'],1);self.assertEqual(report['summary']['outcomes']['inconclusive'],1)
        self.assertIsNone(report['summary']['declared_issue_fraction']);self.assertFalse(report['training_eligible'])
        self.assertEqual(before,digest(self.h.fixture.snapshots.get_snapshot(self.scope,self.h.sid,data=True)))
        self.assertEqual(self.h.fixture.labels_store.list(self.scope),labels_before)

    def task_body(self,request='task-request-one'):
        return dict(task_type='request_documents',title='Bổ sung hóa đơn',what_to_do='Đối chiếu và tải hóa đơn gốc',
            reason='Chưa đủ căn cứ',assignee_key='ke_toan_cong_no',due_at='2026-12-10T17:00:00+07:00',request_id=request)

    def test_task_binding_idempotency_restart_report_and_existing_lifecycle(self):
        rem=RemediationStore(self.h.store.path.with_name('remediation.db'));self.work.remediation=rem
        body=self.task_body();before=self.h.fixture.labels_store.list(self.scope)
        created=self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=body)
        task=created['task'];binding=task['source_binding'];self.assertTrue(created['created'])
        for k in ('snapshot_id','run_id','bundle_id'):self.assertEqual(binding[k],self.result[k])
        self.assertEqual(binding['case_id'],self.case['case_id']);self.assertEqual(task['case_id'],self.case['review_id'])
        same=self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=body)
        self.assertTrue(same['idempotent_replay']);self.assertEqual(same['task']['task_id'],task['task_id'])
        duplicate=self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=self.task_body('another-tab-request'))
        self.assertTrue(duplicate['deduplicated_existing'])
        assigned=rem.assign_task(self.scope,task_id=task['task_id'],expected_revision=1,
            assignee_kind='department_role',assignee_key='kiem_soat_noi_bo',due_at=task['due_at'],reason='Chuyển đúng bộ phận')
        self.assertEqual(assigned['source_binding'],binding)
        self.work.remediation=RemediationStore(rem.path)
        report=self.work.report(self.scope,self.run_id)
        self.assertEqual(report['baseline']['catalogue_size'],35)
        self.assertEqual(report['cases'][0]['tasks'][0]['revision'],2)
        self.assertEqual(report['task_counts']['waiting_external'],1)
        self.assertEqual(self.h.fixture.labels_store.list(self.scope),before)
        self.assertEqual(report['summary']['reviewed_cases'],0)

    def test_task_cannot_forge_binding_cross_run_or_replay_changed_body(self):
        self.work.remediation=RemediationStore(self.h.store.path.with_name('remediation.db'))
        body=self.task_body();self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=body)
        self.denied('PIPELINE_TASK_FIELDS',lambda:self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=dict(body,bundle_id='fake')))
        self.denied('IDEMPOTENCY_PAYLOAD_MISMATCH',lambda:self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=dict(body,title='Changed title')))
        self.denied('PIPELINE_TASK_ASSIGNEE',lambda:self.work.tasks(self.scope,self.run_id,self.case['review_id'],body=dict(body,assignee_key='fake_person')))
        other=self.h.fixture.company_ctx['C002']['scope']
        self.denied('PIPELINE_RUN_NOT_FOUND',lambda:self.work.tasks(other,self.run_id,self.case['review_id']))
        self.denied('PIPELINE_REVIEW_NOT_FOUND',lambda:self.work.tasks(self.scope,self.run_id,'rvw_'+'a'*64,body=body))

    def test_task_current_auth_recheck_rolls_back_before_commit(self):
        rem=RemediationStore(self.h.store.path.with_name('remediation.db'));self.work.remediation=rem
        real=rem._save_receipt
        permission=[self.scope]
        def revoke(*args,**kwargs):
            result=real(*args,**kwargs);permission[0]=replace(self.scope,permissions=frozenset());return result
        with patch.object(rem,'_save_receipt',side_effect=revoke):
            self.denied('AUTH_CONTEXT_CHANGED',lambda:self.work.tasks(self.scope,self.run_id,self.case['review_id'],recheck=lambda:permission[0],body=self.task_body()))
        self.assertEqual(rem.get_case_remediation(self.scope,self.case['review_id'])['tasks'],[])

    def test_retry_after_restart_returns_same_review_and_preserves_packet(self):
        value,body=self.save();packet=self.result['result']['pipeline']['review_packet_id']
        reopened=ReleaseService(ReleaseStore(self.h.store.path,b's'*32),self.h.fixture.snapshots,self.svc.resources,self.h.queue)
        again=reopened.workspace.action(self.scope,self.run_id,self.case['review_id'],'save',body)
        self.assertEqual(again,value);self.assertEqual(again['revision'],1)
        self.assertEqual(reopened.workspace.report(self.scope,self.run_id)['cases'][0]['review']['revision'],1)
        self.assertEqual(reopened.workspace.observation(self.scope,self.run_id)['result']['pipeline']['review_packet_id'],packet)

    def test_company_feedback_visible_to_other_authorized_actor_without_overwrite(self):
        other=replace(self.scope,actor_id='second-company-reviewer')
        self.save();report=self.work.report(other,self.run_id)
        self.assertEqual(report['cases'][0]['review']['revision'],1)
        self.assertEqual(report['cases'][0]['review']['history'][0]['actor_id'],self.scope.actor_id)
        self.denied('REVIEW_CONFLICT',lambda:self.save(scope=other,request='second-save-stale',expected=0))

    def test_other_company_or_run_cannot_reuse_review_id_or_evidence(self):
        other=replace(self.scope,company_ids=frozenset({'C002'}))
        self.denied('PIPELINE_RUN_NOT_FOUND',lambda:self.work.report(other,self.run_id))
        self.denied('PIPELINE_REVIEW_NOT_FOUND',lambda:self.work.case(self.scope,self.run_id,'rvw_'+'0'*64))
        fb=self.feedback('legitimate');fb.update(evidence_ids=['pev_'+'a'*64],checks_completed=True)
        self.denied('REVIEW_FOREIGN_EVIDENCE',lambda:self.save(fb))

    def test_conclusive_result_requires_checked_source_and_not_just_alert(self):
        fb=self.feedback('confirmed_risk')
        self.denied('REVIEW_CHECKS',lambda:self.save(fb))
        self.assertEqual(self.work.reviews.get(self.scope,self.case['review_id'])['revision'],0)

    def test_attachment_is_scoped_unverified_and_does_not_change_features(self):
        before=self.h.fixture.snapshots.get_snapshot(self.scope,self.h.sid,data=True)
        content=base64.b64encode(b'%PDF-1.4 synthetic evidence only').decode()
        value=self.work.action(self.scope,self.run_id,self.case['review_id'],'attachments',dict(name='late.pdf',content=content))
        report=self.work.report(self.scope,self.run_id);a=report['cases'][0]['review']['attachments'][0]
        self.assertFalse(a['original_verified']);self.assertTrue(a['known_after_analysis'])
        self.assertEqual(self.work.reviews.attachment(self.scope,self.case['review_id'],value['attachment_id'])['content'],content)
        another=report['cases'][1]['review_id']
        self.denied('ATTACHMENT_NOT_FOUND',lambda:self.work.reviews.attachment(self.scope,another,value['attachment_id']))
        self.assertEqual(before,self.h.fixture.snapshots.get_snapshot(self.scope,self.h.sid,data=True))

    def test_report_hash_changes_only_after_feedback_and_csv_is_safe(self):
        first=self.work.report(self.scope,self.run_id);self.assertEqual(first,self.work.report(self.scope,self.run_id))
        f=self.feedback();f['explanation']='=HYPERLINK("https://invalid.example")';self.save(f)
        after=self.work.report(self.scope,self.run_id);self.assertNotEqual(first['report_sha256'],after['report_sha256'])
        after['cases'][0]['financial_summary']['related_amount_vnd']='-9007199254740993'
        rows=list(csv.DictReader(io.StringIO(csv_report(after).decode('utf-8-sig'))))
        self.assertTrue(rows[0]['explanation'].startswith("'="));self.assertEqual(rows[0]['related_amount_vnd'],'-9007199254740993')
        self.assertEqual(rows[0]['confirmed_loss_vnd'],'')

    def test_revocation_during_save_rolls_back_review_revision(self):
        lease=self.work.action(self.scope,self.run_id,self.case['review_id'],'start',{})['lease'];n=[0]
        def recheck():
            n[0]+=1;return self.scope if n[0]==1 else replace(self.scope,actor_id='revoked')
        self.denied('AUTH_CONTEXT_CHANGED',lambda:self.work.reviews.save(self.scope,self.case['review_id'],0,self.feedback(),[],lease,'revoke-during-save',recheck=recheck))
        self.assertEqual(self.work.reviews.get(self.scope,self.case['review_id'])['revision'],0)

    def test_crash_after_queue_before_packet_commit_recovers_one_packet(self):
        with patch('sme_fraud.bundle_reviews.build_packet',side_effect=RuntimeError('Synthetic packet boundary crash')):
            with self.assertRaises(RuntimeError):self.svc.run(self.scope,'packet-boundary-run','staging',self.h.sid,self.h.cutoff)
        count=len(self.h.store.list(self.scope,'review_packet'))
        recovered=self.svc.run(self.scope,'packet-boundary-run','staging',self.h.sid,self.h.cutoff)
        again=self.svc.run(self.scope,'packet-boundary-run','staging',self.h.sid,self.h.cutoff)
        self.assertEqual(recovered,again);self.assertEqual(len(self.h.store.list(self.scope,'review_packet')),count+1)
        self.assertEqual(recovered['result']['pipeline']['queue']['budget_status']['reserved_count'],3)
        # Existing cases were already notified; the recovered run creates no duplicate reviews.
        self.assertEqual(self.work.report(self.scope,'packet-boundary-run')['cases'],[])

    def test_cloud_request_never_calls_plaintext_executor(self):
        with patch.object(self.svc,'_execute',side_effect=AssertionError('No local fallback for cloud request')):
            self.denied('PIPELINE_HE_UNAVAILABLE',lambda:self.svc.run(self.scope,'cloud-must-not-clear','staging',self.h.sid,self.h.cutoff,execution_mode='cloud_ciphertext_only'))
        self.assertTrue(all(p['value']['run_id']!='cloud-must-not-clear' for p in self.h.store.list(self.scope,'pin')))
        self.assertFalse(self.result['result']['execution']['cloud_he']['available'])

    def test_future_non_candidate_payment_not_counted_as_case_history(self):
        from training_snapshot_support import commit
        data=json.loads(self.h.fixture.snapshots.get_snapshot(self.scope,self.h.sid,data=True))
        invoice=next(c for c in self.result['result']['pipeline']['cases'] if c['problem_family']=='payment_invoice')
        tid=invoice['candidate_ids'][0]
        future=deepcopy(next(t for t in data['source']['tables']['transactions'] if t['transaction_id']==tid))
        future['transaction_id']='FUTURE_HISTORY_MUST_STAY_OUT'
        for field in ('posted_at','created_at','observed_at','approved_at'):future[field]='2026-12-20T10:00:00+07:00'
        future['amount_vnd']=900_000_000
        data['source']['tables']['transactions'].append(future)
        rows=data['source']['tables']['transactions']
        data['source']['coverage']['transactions'].update(record_count=len(rows),records_sha256=digest(canonical(rows)))
        sid=commit(self.h.fixture.snapshots,data,self.scope,'future-noncandidate-source')
        new_result=self.svc.run(self.scope,'future-noncandidate-run','staging',sid,self.h.cutoff)
        new_cases={c['case_id']:c for c in new_result['result']['pipeline']['cases']}
        self.assertEqual(invoice['financial_summary'],new_cases[invoice['case_id']]['financial_summary'])
        self.assertTrue(all(future['transaction_id'] not in c['evidence_tx_ids'] for c in new_cases.values()))

    def test_http_accountant_report_save_export_and_cross_company_guards(self):
        from test_portal_auth import PortalHarness,portal
        from sme_fraud.review_server import make_server
        from portal.agent2_bridge import allowed_path
        with PortalHarness() as h:
            h.agent.shutdown();h.agent.server_close();h.agent=make_server(0,h.authorizer,self.h.fixture.snapshots,self.svc.resources,case_queue_store=self.h.queue,release_service=self.svc)
            portal.CFG['agents']['agent2']['port']=h.agent.server_port;t=threading.Thread(target=h.agent.serve_forever,daemon=True);t.start();h.threads.append(t)
            root=h.url('pipeline-workspace');path=root+'/runs/'+self.run_id;review=path+'/reviews/'+self.case['review_id']
            status,report=h.request(path);self.assertEqual(status,200,report)
            self.assertEqual(report['bundle_id'],self.result['bundle_id']);self.assertNotIn('ecod',json.dumps(report))
            status,start=h.request(review+'/start',{});self.assertEqual(status,200,start)
            body=dict(expected_revision=0,feedback=self.feedback(),lease=start['lease'],request_id='http-review-save')
            status,saved=h.request(review+'/save',body);self.assertEqual(status,200,saved)
            for k in ('run_id','snapshot_id','bundle_id'):self.assertEqual(saved[k],self.result[k])
            self.assertEqual(h.request(review+'/save',body)[1]['revision'],1)
            self.assertEqual(h.request(path+'/report.csv')[0],200)
            self.assertEqual(h.request(path,token=False)[0],401)
            self.assertEqual(h.request(h.url('pipeline-workspace/runs/'+self.run_id,'C002'))[0],404)
            self.assertEqual(h.request(h.url('pipeline-releases'))[0],403)
            self.assertEqual(h.request(review+'/save',dict(body,model='ecod'))[0],400)
            status,listing=h.request(root);self.assertEqual(status,200);self.assertTrue(listing['can_run'])
            self.assertFalse(listing['can_manage'])
            self.assertNotIn('ecod',json.dumps(listing))
            status,entry=h.request('/agent2/');self.assertEqual(status,200);self.assertIn(b'bw-analyze',entry)
            status,settings=h.request('/agent2/api/v1/ui/settings');self.assertEqual(settings['workspace_mode'],'bundle_shadow')
            status,task=h.request(review+'/tasks',self.task_body('http-task-create'))
            self.assertEqual(status,200,task)
            for k in ('snapshot_id','run_id','bundle_id'):self.assertEqual(task['task']['source_binding'][k],self.result[k])
            self.assertEqual(h.request(review+'/tasks',self.task_body('http-task-create'))[1]['task']['task_id'],task['task']['task_id'])
            self.assertEqual(len(h.request(review+'/tasks')[1]['tasks']),1)
            self.assertEqual(h.request(review+'/tasks',dict(self.task_body(),snapshot_id='fake'))[0],400)
            self.assertEqual(h.request(h.url('pipeline-workspace/runs/'+self.run_id+'/reviews/'+self.case['review_id']+'/tasks','C002'))[0],404)
            request=dict(run_id='accountant-business-run',snapshot_id=self.h.sid)
            status,new_report=h.request(root+'/runs',request);self.assertEqual(status,200,new_report)
            self.assertEqual(new_report['run_id'],request['run_id']);self.assertEqual(new_report['cases'],[])
            self.assertEqual(h.request(root+'/runs',dict(request,raw_scores=[1,2,3]))[0],400)
            self.assertEqual(h.request(root+'/runs',dict(request,run_id='cloud-no-clear-request',execution_mode='cloud_ciphertext_only'))[0],409)
            for p in ('/pipeline-workspace','/assets/bundle-workspace.js'):
                self.assertTrue(allowed_path(p));self.assertEqual(h.request('/agent2'+p)[0],200)
            self.assertFalse(allowed_path('/api/v1/companies/C001/pipeline-workspace/runs/../private'))


if __name__=='__main__':unittest.main()
