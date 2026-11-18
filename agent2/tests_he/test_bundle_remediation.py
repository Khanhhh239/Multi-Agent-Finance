"""Real immutable bundle cases, existing R4 store, and Portal lifecycle boundary."""
import base64
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

from sme_fraud import bundle_remediation as adapter
from sme_fraud.import_files import ImportFailure,canonical,digest
from sme_fraud.remediation_store import RemediationStore
import test_bundle_workspace as support


class BundleRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):support.BundleWorkspaceTests.setUpClass()
    @classmethod
    def tearDownClass(cls):support.BundleWorkspaceTests.tearDownClass()

    def setUp(self):
        h=self.h=support.BundleWorkspaceTests();h.setUp();self.addCleanup(h.doCleanups)
        self.work=h.work;self.scope=h.scope;self.rid=h.run_id;self.cid=h.case['review_id']
        self.op=replace(self.scope,permissions=frozenset({'data.import'}))
        self.ver=replace(self.scope,permissions=frozenset({'data.import','evidence.verify'}))
        self.rem=self.work.remediation=RemediationStore(h.h.store.path.with_name('bound-remediation.db'))
        self.n=0

    def read(self,scope=None,cid=None):return adapter.read(self.work,scope or self.op,self.rid,cid or self.cid)
    def cmd(self,action,payload,scope=None,cid=None,request=None,recheck=None):
        self.n+=1
        return adapter.command(self.work,scope or self.op,self.rid,cid or self.cid,
            dict(action=action,payload=payload,request_id=request or 'bound-request-'+str(self.n)),recheck)
    def task(self):return self.work.tasks(self.op,self.rid,self.cid,body=self.h.task_body())['task']
    def upload(self,**kw):
        p=dict(document_type='invoice',filename='invoice.pdf',content_base64=base64.b64encode(b'%PDF-1.4 synthetic invoice').decode(),note='Synthetic evidence, not an original')
        p.update(kw);return self.cmd('upload_document',p)['document']
    def denied(self,code,call):self.h.denied(code,call)
    def submit(self,t,doc):return self.cmd('submit_task',dict(task_id=t['task_id'],expected_revision=t['revision'],result_summary='Checked synthetic records; original evidence still requires business review',document_ids=[doc['document_id']],waiting_external=False))['task']
    def decide(self,t,decision,**kw):return self.cmd('decide_task',dict(task_id=t['task_id'],expected_revision=t['revision'],decision=decision,note='Business reviewer decision for synthetic acceptance'),scope=self.ver,**kw)['task']
    def verify(self,doc,version=1,**kw):return self.cmd('verify_document',dict(document_id=doc['document_id'],version=version,decision='present',note='Compared synthetic record with supplied PDF'),scope=self.ver,**kw)

    def test_lifecycle_complete_reopen_requires_new_submission_no_label_or_snapshot_mutation(self):
        before=self.h.h.fixture.snapshots.get_snapshot(self.scope,self.h.h.sid,data=True)
        labels=self.h.h.fixture.labels_store.list(self.scope)
        t=self.task();d=self.upload();self.assertEqual(d['verification_status'],'pending_verification')
        self.assertFalse(self.read()['tasks'][0]['actions']['can_complete'])
        t=self.submit(t,d)
        self.denied('VERIFIED_EVIDENCE_REQUIRED',lambda:self.decide(t,'confirm_complete'))
        self.verify(d);self.assertTrue(self.read(self.ver)['tasks'][0]['actions']['can_complete'])
        t=self.decide(t,'confirm_complete');self.assertEqual(t['status'],'completed')
        t=self.decide(t,'reopen');self.assertEqual(t['status'],'open')
        self.denied('NEW_SUBMISSION_REQUIRED_AFTER_REWORK',lambda:self.decide(t,'confirm_complete'))
        t=self.submit(t,d);t=self.decide(t,'confirm_complete');self.assertEqual(t['status'],'completed')
        self.assertEqual(before,self.h.h.fixture.snapshots.get_snapshot(self.scope,self.h.h.sid,data=True))
        self.assertEqual(labels,self.h.h.fixture.labels_store.list(self.scope))
        self.assertEqual(self.work.reviews.get(self.scope,self.cid)['revision'],0)
        report=self.work.report(self.scope,self.rid)
        self.assertEqual(report['task_counts']['completed'],1);self.assertEqual(report['document_counts']['present'],1)
        self.assertFalse(report['training_eligible']);self.assertFalse(self.read()['identity_verified'])

    def test_version_replacement_does_not_inherit_verification_and_review_pins_old_version(self):
        d=self.upload();self.verify(d)
        p=dict(document_id=d['document_id'],content_base64=base64.b64encode(b'%PDF-1.4 replacement invoice').decode())
        new=self.upload(**p);self.assertEqual(new['current_version'],2);self.assertEqual(new['verification_status'],'pending_verification')
        self.verify(d,1);self.assertEqual(self.read()['documents'][0]['verification_status'],'pending_verification')
        old=adapter.content(self.work,self.op,self.rid,self.cid,d['document_id'],1)
        self.assertEqual(old['sha256'],d['versions'][0]['sha256'])
        fb=self.h.feedback();fb['evidence_ids']=[d['document_id']+':v1'];saved,_=self.h.save(fb)
        self.assertEqual(saved['feedback']['evidence_ids'],fb['evidence_ids'])
        self.denied('DOCUMENT_VERSION_NOT_FOUND',lambda:adapter.content(self.work,self.op,self.rid,self.cid,d['document_id'],99))

    def test_retry_restart_dedup_and_changed_payload_rejected(self):
        t=self.task();d=self.upload();p=dict(task_id=t['task_id'],expected_revision=t['revision'],result_summary='Submission survives response loss',document_ids=[d['document_id']],waiting_external=True)
        first=self.cmd('submit_task',p,request='durable-submit-request')
        self.work.remediation=RemediationStore(self.rem.path)
        again=self.cmd('submit_task',p,request='durable-submit-request')
        self.assertTrue(again['idempotent_replay']);self.assertEqual(again['task'],first['task'])
        self.assertEqual(self.read()['tasks'][0]['revision'],2)
        self.denied('IDEMPOTENCY_PAYLOAD_MISMATCH',lambda:self.cmd('submit_task',dict(p,result_summary='Changed'),request='durable-submit-request'))
        duplicate=self.upload();self.assertEqual(duplicate['document_id'],d['document_id']);self.assertEqual(len(self.read()['documents']),1)

    def test_permission_checks_before_receipt_and_current_auth_rollback(self):
        d=self.upload();self.assertFalse(self.read()['permissions']['can_verify'])
        self.verify(d,request='verified-first-request')
        p=dict(document_id=d['document_id'],version=1,decision='present',note='Compared synthetic record with supplied PDF')
        self.denied('VERIFIER_PERMISSION_REQUIRED',lambda:self.cmd('verify_document',p,request='verified-first-request'))
        t=self.task();state=[self.op];real=self.rem._save_receipt
        def revoke(*args,**kw):
            result=real(*args,**kw);state[0]=replace(self.op,permissions=frozenset());return result
        payload=dict(task_id=t['task_id'],expected_revision=1,result_summary='Must roll back on revocation',document_ids=[],waiting_external=True)
        with patch.object(self.rem,'_save_receipt',side_effect=revoke):
            self.denied('AUTH_CONTEXT_CHANGED',lambda:self.cmd('submit_task',payload,request='rollback-submit-request',recheck=lambda:state[0]))
        self.assertIsNone(getattr(self.rem._command_tx,'connection',None))
        self.assertEqual(self.read()['tasks'][0]['revision'],1)
        self.assertEqual(self.cmd('submit_task',payload,request='rollback-submit-request')['task']['revision'],2)

    def test_no_cross_case_company_run_or_arbitrary_source(self):
        t=self.task();d=self.upload();other=self.h.report['cases'][1]['review_id']
        self.denied('PIPELINE_REMEDIATION_NOT_FOUND',lambda:self.cmd('verify_document',dict(document_id=d['document_id'],version=1,decision='present',note='No'),scope=self.ver,cid=other))
        self.denied('PIPELINE_REMEDIATION_NOT_FOUND',lambda:self.cmd('submit_task',dict(task_id=t['task_id'],expected_revision=1,result_summary='No',document_ids=[],waiting_external=False),cid=other))
        self.denied('PIPELINE_REMEDIATION_NOT_FOUND',lambda:adapter.content(self.work,self.op,self.rid,other,d['document_id'],1))
        self.denied('PIPELINE_RUN_NOT_FOUND',lambda:self.read(replace(self.op,company_ids=frozenset({'C002'}))))
        fb=self.h.feedback();fb['evidence_ids']=[d['document_id']+':v1']
        lease=self.work.action(self.op,self.rid,other,'start',{})['lease']
        self.denied('REVIEW_FOREIGN_EVIDENCE',lambda:self.work.action(self.op,self.rid,other,'save',dict(expected_revision=0,lease=lease,request_id='foreign-doc-review',feedback=fb)))
        self.denied('PIPELINE_REMEDIATION_FIELDS',lambda:self.cmd('verify_document',dict(document_id=d['document_id'],version=1,decision='present',note='No',company_id='C002'),scope=self.ver))

    def test_legacy_attachment_import_signature_validation_and_explicit_type(self):
        raw=base64.b64encode(b'%PDF-1.4 legacy attachment').decode()
        old=self.work.action(self.op,self.rid,self.cid,'attachments',dict(name='legacy.pdf',content=raw))
        self.assertEqual(self.read()['documents'],[])
        imported=self.cmd('import_attachment',dict(attachment_id=old['attachment_id'],document_type='invoice',note='Moved legacy file into versioned evidence'))
        self.assertEqual(imported['document']['verification_status'],'pending_verification')
        self.denied('PIPELINE_DOCUMENT_TYPE',lambda:self.upload(content_base64=base64.b64encode(b'<script>bad</script>').decode()))
        self.denied('PIPELINE_DOCUMENT_TYPE',lambda:self.upload(document_type='unknown_document_type'))
        self.denied('PIPELINE_DOCUMENT_NAME',lambda:self.upload(filename='../outside.pdf'))

    def test_assignment_rework_and_cas(self):
        t=self.task();d=self.upload();p=dict(task_id=t['task_id'],expected_revision=1,assignee_key='kiem_soat_noi_bo',due_at='2026-12-12T17:00:00+07:00',reason='Reassign to controller')
        t=self.cmd('assign_task',p)['task'];self.assertEqual(t['assignee']['assignee_key'],'kiem_soat_noi_bo')
        self.denied('REVISION_CONFLICT',lambda:self.cmd('assign_task',p))
        t=self.submit(t,d);t=self.decide(t,'request_rework')
        self.verify(d);self.assertFalse(self.read(self.ver)['tasks'][0]['actions']['can_complete'])
        self.denied('NEW_SUBMISSION_REQUIRED_AFTER_REWORK',lambda:self.decide(t,'confirm_complete'))

    def test_portal_http_static_read_upload_verify_content_and_report(self):
        from test_portal_auth import PortalHarness,portal
        from sme_fraud.review_server import make_server
        from portal.agent2_bridge import allowed_path
        with PortalHarness() as h:
            h.agent.shutdown();h.agent.server_close();h.agent=make_server(0,h.authorizer,self.h.h.fixture.snapshots,self.h.svc.resources,case_queue_store=self.h.h.queue,release_service=self.h.svc,remediation_store=self.rem)
            portal.CFG['agents']['agent2']['port']=h.agent.server_port
            thread=threading.Thread(target=h.agent.serve_forever,daemon=True);thread.start();h.threads.append(thread)
            url=h.url('pipeline-workspace/runs/'+self.rid+'/reviews/'+self.cid+'/remediation')
            self.assertTrue(allowed_path(url.removeprefix('/agent2')))
            for asset in ('bundle-remediation.js','bundle-remediation.css'):
                self.assertEqual(h.request('/agent2/assets/'+asset)[0],200)
            status,view=h.request(url);self.assertEqual(status,200,view);self.assertFalse(view['permissions']['can_verify'])
            d=self.upload();get=url+'/documents/'+d['document_id']+'/versions/1'
            self.assertEqual(h.request(get)[1]['sha256'],d['versions'][0]['sha256'])
            p=dict(action='verify_document',request_id='http-verify-request',payload=dict(document_id=d['document_id'],version=1,decision='present',note='Checked supplied invoice'))
            self.assertEqual(h.request(url,p)[0],403)
            h.policy['memberships'][0]['permissions'].append('evidence.verify');h.write_policy()
            status,value=h.request(url,p);self.assertEqual(status,200,value)
            self.assertEqual(value['document']['verification_status'],'present')
            self.assertEqual(value['run_id'],self.rid)
            self.assertEqual(h.request(get,token=False)[0],401)
            self.assertEqual(h.request(url.replace('/C001/','/C002/'))[0],404)
            status,report=h.request(h.url('pipeline-workspace/runs/'+self.rid+'/report'))
            self.assertEqual(status,200,report);self.assertEqual(report['document_counts']['present'],1)
            sha=report.pop('report_sha256');self.assertEqual(sha,digest(canonical(report)))


if __name__=='__main__':unittest.main()
