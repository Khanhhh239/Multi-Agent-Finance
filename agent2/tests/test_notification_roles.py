"""Synthetic role routing, reminders and delivery history; all transports mocked."""
import copy,http.client,json,sqlite3,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import MagicMock,patch
from test_review import make_fixture
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_workflow import TwoStageReview
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.notifications import Notifications,notification_config
from sme_fraud.notification_audit import history
from sme_fraud.notification_channels import DeliveryError
from sme_fraud.review_server import make_server


def role_config():
    def person(user,person_id,role):return dict(user_id=user,person_id=person_id,role=role,
        display_name='MÔ PHỎNG '+user,channels={'email':[user.lower()+'@example.invalid'],'zalo':['SIM_'+user]})
    return dict(dry_run=True,replay_existing=True,daily_budget=10,case_url='http://127.0.0.1:8795/',
        role_recipients={'C001':[person('ACC','P1','accountant'),person('CHIEF','P2','chief_accountant'),person('DIR','P3','director')],
                         'C002':[person('ACC2','P4','accountant'),person('CHIEF2','P5','chief_accountant')]})


class RoleNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.data,self.report=make_fixture(self.root)
        self.now=datetime.fromisoformat('2026-10-27T10:00:00+07:00')
        self.store=ReviewStore(self.root/'data',self.root/'reports',self.root/'review.sqlite3',clock=lambda:self.now)
        self.store.prepare();self.store.set_budget(10);self.workflow=TwoStageReview(self.store)
        self.acc=ReviewPrincipal('ACC','P1','MÔ PHỎNG ACC','accountant',('C001',))
        self.chief=ReviewPrincipal('CHIEF','P2','MÔ PHỎNG CHIEF','chief_accountant',('C001',))
        self.director=ReviewPrincipal('DIR','P3','MÔ PHỎNG DIR','director',('C001',))
        self.config=role_config();self.service=Notifications(self.store,self.config)

    def body(self,case='RC_1',**extra):
        state=self.workflow.state('003',case)
        return dict(decision='false_positive',reason='MÔ PHỎNG: đã đối chiếu',missing_evidence='',active_minutes=1,
            timing_method='measured_stopwatch',expected_event_hash=state['latest_event_hash'],expected_scope_hash=state['case_scope_hash'])|extra

    def submit(self,case='RC_1'):return self.workflow.submit('003',case,self.acc,self.body(case))
    def plan(self):self.service.plan('003');return self.jobs()
    def jobs(self,kind=None,case=None):
        with self.store.connection() as db:rows=[dict(r) for r in db.execute('SELECT * FROM notification_outbox')]
        for row in rows:row.update(json.loads(row.pop('payload')))
        return [r for r in rows if (kind is None or r['kind']==kind) and (case is None or any(ref['case_id']==case for ref in r['case_refs']))]
    def current_sources(self):
        with self.store.connection() as db:return self.service.business.describe('003',self.now,db)
    def request_document(self):
        return self.store.update_information_request('003','RC_1',dict(action='create',
            case_scope_hash=self.store.detail('003','RC_1')['case']['review_scope_hash'],expected_hash='',
            actor='MÔ PHỎNG ACC',owner='Tên bộ phận, không phải địa chỉ gửi',reason='MÔ PHỎNG cần sao kê',
            due_at=(self.now+timedelta(hours=24)).isoformat(),requested_documents='MÔ PHỎNG sao kê T1'))
    def update_document(self,request,action,**extra):
        return self.store.update_information_request('003','RC_1',dict(action=action,request_id=request['request_id'],expected_hash=request['event_hash'],
            case_scope_hash=self.store.detail('003','RC_1')['case']['review_scope_hash'],actor='MÔ PHỎNG ACC',reason='MÔ PHỎNG cập nhật tài liệu')|extra)
    def test_submission_routes_only_company_chief_and_not_director_or_accountant(self):
        self.submit();self.plan();jobs=self.jobs('review_submitted','RC_1')
        self.assertEqual({j['recipient'] for j in jobs},{'chief@example.invalid','SIM_CHIEF'})
        self.assertTrue(all(j['company_id']=='C001' for j in jobs))
        self.assertTrue(all('case=RC_1' in j['body'] for j in jobs))

    def test_high_priority_routes_to_accountants_and_weekly_to_chief(self):
        with self.store.connection() as db:
            for saved in db.execute('SELECT case_id,data FROM cases').fetchall():
                row=json.loads(saved['data']);row['sla_due_at']=(self.now+timedelta(days=1)).isoformat()
                db.execute('UPDATE cases SET data=? WHERE case_id=?',(json.dumps(row),saved['case_id']))
        self.plan()
        self.assertEqual({j['recipient'] for j in self.jobs('high_priority') if j['company_id']=='C001'},{'acc@example.invalid','SIM_ACC'})
        self.assertEqual({j['recipient'] for j in self.jobs('weekly') if j['company_id']=='C001'},{'chief@example.invalid','SIM_CHIEF'})

    def test_falls_back_to_director_when_no_independent_chief(self):
        cfg=role_config();cfg['role_recipients']['C001'][1]['person_id']='p1'
        self.service=Notifications(self.store,cfg);self.submit();self.plan()
        self.assertEqual({r['recipient'] for r in self.jobs('review_submitted')},{'dir@example.invalid','SIM_DIR'})

    def test_return_notifies_original_accountant_not_other_accountants(self):
        cfg=role_config();other=copy.deepcopy(cfg['role_recipients']['C002'][0]);cfg['role_recipients']['C001'].append(other)
        self.service=Notifications(self.store,cfg);self.submit()
        self.workflow.final_action('003','RC_1',self.chief,self.body(),action='return');self.plan()
        self.assertEqual({r['recipient'] for r in self.jobs('review_returned')},{'acc@example.invalid','SIM_ACC'})

    def test_pending_old_submission_cancelled_after_return_or_resubmit(self):
        self.submit();self.plan();self.workflow.final_action('003','RC_1',self.chief,self.body(),action='return')
        self.service.dispatch();self.assertTrue(all(j['status']=='cancelled' for j in self.jobs('review_submitted')))
        self.submit();self.plan();self.service.dispatch()
        self.assertEqual(len([j for j in self.jobs('review_submitted') if j['status']=='simulated']),2)

    def test_closed_final_result_is_delivered_to_original_reviewer(self):
        self.submit();self.workflow.final_action('003','RC_1',self.chief,self.body());self.plan();self.service.dispatch()
        jobs=self.jobs('review_finalized');self.assertEqual(len(jobs),2)
        self.assertEqual({j['recipient'] for j in jobs},{'acc@example.invalid','SIM_ACC'})
        self.assertTrue(all(j['status']=='simulated' for j in jobs))

    def test_control_violation_also_notifies_director_excluding_approver(self):
        self.submit();self.workflow.final_action('003','RC_1',self.chief,self.body(decision='non_compliance'));self.plan()
        self.assertEqual({j['recipient'] for j in self.jobs('review_finalized')},{'acc@example.invalid','SIM_ACC','dir@example.invalid','SIM_DIR'})

    def test_same_director_who_finalized_is_not_re_notified(self):
        self.submit();self.workflow.final_action('003','RC_1',self.director,self.body(decision='confirmed_suspicion'));self.plan()
        self.assertEqual({j['recipient'] for j in self.jobs('review_finalized')},{'acc@example.invalid','SIM_ACC'})

    def test_reminder_cutoff_interval_and_escalation(self):
        self.submit();start=self.now;self.plan()
        self.now=start+timedelta(hours=48);self.plan();self.assertEqual(self.jobs('review_overdue'),[])
        self.now+=timedelta(seconds=1);self.plan();self.assertEqual(len(self.jobs('review_overdue')),2)
        self.service.dispatch();self.plan();self.assertEqual(len(self.jobs('review_overdue')),2)
        self.now=start+timedelta(hours=96,seconds=1);self.plan()
        escalated=[j for j in self.jobs('review_overdue') if j['escalated']]
        self.assertEqual({j['recipient'] for j in escalated},{'chief@example.invalid','SIM_CHIEF','dir@example.invalid','SIM_DIR'})

    def test_returned_review_has_own_rework_deadline(self):
        self.submit();self.workflow.final_action('003','RC_1',self.chief,self.body(),action='return');start=self.now
        self.plan();self.assertEqual(self.jobs('rework_overdue'),[])
        self.now+=timedelta(hours=48,seconds=1);self.plan()
        self.assertEqual({j['recipient'] for j in self.jobs('rework_overdue')},{'acc@example.invalid','SIM_ACC'})
        self.assertTrue(all(j['due_at']==(start+timedelta(hours=48)).isoformat() for j in self.jobs('rework_overdue')))

    def test_case_sla_reminder_uses_sla_due_at_and_stops_after_closure(self):
        self.plan();self.assertTrue(self.jobs('case_overdue','RC_1'))
        self.submit();self.workflow.final_action('003','RC_1',self.chief,self.body());self.service.dispatch()
        self.assertTrue(all(j['status']=='cancelled' for j in self.jobs('case_overdue','RC_1')))

    def test_document_reminder_uses_operational_deadline_not_historical_case_sla(self):
        request=self.request_document();self.plan();self.assertEqual(self.jobs('case_overdue','RC_1'),[]);self.assertEqual(self.jobs('documents_overdue'),[])
        self.now+=timedelta(hours=24);self.plan();self.assertEqual(self.jobs('documents_overdue'),[])
        self.now+=timedelta(seconds=1);self.plan();jobs=self.jobs('documents_overdue')
        self.assertEqual({j['recipient'] for j in jobs},{'acc@example.invalid','SIM_ACC'})
        self.assertTrue(all(j['due_at']==request['due_at'] for j in jobs))

    def test_received_document_notifies_accountant_and_review_cancels_pending_reminders(self):
        request=self.request_document();received=self.update_document(request,'receive',evidence_refs=['SIM_BANK_T1'])
        self.plan();self.assertEqual({j['recipient'] for j in self.jobs('documents_received')},{'acc@example.invalid','SIM_ACC'})
        self.now+=timedelta(hours=24,seconds=1);self.plan();self.assertTrue(self.jobs('documents_overdue'))
        self.update_document(received,'review');self.service.dispatch()
        self.assertTrue(all(j['status']=='cancelled' for j in self.jobs('documents_received')+self.jobs('documents_overdue')))

    def test_reassigning_document_due_time_invalidates_old_reminder(self):
        request=self.request_document();self.now+=timedelta(hours=25);self.plan();self.assertTrue(self.jobs('documents_overdue'))
        self.update_document(request,'assign',owner='MÔ PHỎNG bộ phận mới',due_at=(self.now+timedelta(days=2)).isoformat())
        self.service.dispatch();self.assertTrue(all(j['status']=='cancelled' for j in self.jobs('documents_overdue')))

    def test_future_case_is_not_notified(self):
        self.now=datetime.fromisoformat('2024-01-01T10:00:00+07:00');self.plan();self.assertEqual(self.jobs(),[])

    def test_legacy_outbox_without_audit_is_labeled_incomplete(self):
        self.submit();self.plan()
        with self.store.connection() as db:
            db.execute('DELETE FROM notification_delivery_events');db.execute("DELETE FROM settings WHERE key='notification_delivery_head'")
        self.assertTrue(all(not j['history_complete'] for j in self.service.status('003')['items']))

    def test_information_gap_stays_open_and_uses_new_rework_deadline(self):
        self.submit();self.workflow.final_action('003','RC_1',self.chief,self.body(decision='information_gap',missing_evidence='MÔ PHỎNG: sao kê'))
        self.plan();self.assertEqual(self.jobs('case_overdue','RC_1'),[]);self.assertEqual(self.jobs('rework_overdue','RC_1'),[])
        self.now+=timedelta(hours=48,seconds=1);self.plan();self.assertTrue(self.jobs('rework_overdue','RC_1'))

    def test_no_real_accounts_means_explicit_gap_without_mock_fallback(self):
        self.service=Notifications(self.store);self.submit();self.plan()
        self.assertEqual(self.jobs(),[])
        gaps=self.service.status('003')['routing_gaps'];self.assertTrue(any(g['kind']=='review_submitted' and g['reason']=='recipient_unassigned' for g in gaps))

    def test_high_priority_and_weekly_missing_roles_are_visible_even_before_sla_due(self):
        with self.store.connection() as db:
            for saved in db.execute('SELECT case_id,data FROM cases').fetchall():
                row=json.loads(saved['data']);row['sla_due_at']=(self.now+timedelta(days=1)).isoformat()
                db.execute('UPDATE cases SET data=? WHERE case_id=?',(json.dumps(row),saved['case_id']))
        self.service=Notifications(self.store,dict(role_recipients={}));self.plan()
        self.assertEqual(self.jobs(),[])
        kinds={g['kind'] for g in self.service.status('003')['routing_gaps']};self.assertEqual(kinds,{'high_priority','weekly'})

    def test_role_policy_activated_after_service_creation_has_no_legacy_fallback(self):
        from sme_fraud.review_roles import SETTING
        with self.store.connection() as db:db.execute('DELETE FROM settings WHERE key=?',(SETTING,))
        service=Notifications(self.store);self.assertFalse(service.business.enabled)
        TwoStageReview(self.store);service.plan('003')
        self.assertTrue(service.business.enabled);self.assertEqual(service.status('003')['items'],[])

    def test_live_legacy_company_recipient_format_is_rejected_for_two_stage_review(self):
        with self.assertRaisesRegex(ValueError,'role_recipients'):
            Notifications(self.store,dict(dry_run=False,recipients={'C001':{'zalo':['SIM_UNSCOPED_ROLE']}}))

    def test_recipient_added_later_routes_current_unsent_event(self):
        self.service=Notifications(self.store,dict(role_recipients={}));self.submit();self.plan()
        self.service=Notifications(self.store,role_config());self.plan()
        self.assertEqual(len(self.jobs('review_submitted')),2)
        self.assertFalse(any(g['kind']=='review_submitted' for g in self.service.status('003')['routing_gaps']))

    def test_recipient_removed_or_role_changed_before_dispatch_cancels_job(self):
        self.submit();self.plan();cfg=role_config();cfg['role_recipients']['C001'][1]['role']='accountant'
        self.service=Notifications(self.store,cfg);self.service.dispatch()
        self.assertTrue(all(j['status']=='cancelled' for j in self.jobs('review_submitted')))
        self.plan();self.assertTrue(any(j['recipient']=='SIM_DIR' for j in self.jobs('review_submitted')))

    def test_duplicate_destinations_across_user_aliases_are_one_job_per_channel(self):
        cfg=role_config();alias=copy.deepcopy(cfg['role_recipients']['C001'][1]);alias['user_id']='CHIEF_ALIAS'
        alias['channels']['email']=['CHIEF@example.invalid'];cfg['role_recipients']['C001'].append(alias)
        self.service=Notifications(self.store,cfg);self.submit();self.plan()
        self.assertEqual(len(self.jobs('review_submitted')),2)

    def test_concurrent_plan_dispatch_and_restart_do_not_duplicate(self):
        self.submit()
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda _:self.service.plan('003'),range(3)))
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda _:self.service.dispatch(),range(3)))
        before=len(self.jobs());self.service=Notifications(self.store,role_config());self.plan();self.service.dispatch()
        self.assertEqual(len(self.jobs()),before);self.assertTrue(all(j['attempts']==1 for j in self.jobs('review_submitted')))
        with self.store.connection() as db:self.assertTrue(history(db))

    def test_company_preview_does_not_plan_dispatch_or_expose_other_company(self):
        self.submit();self.service.plan('003',company_ids=('C001',));self.service.dispatch(company_ids=('C001',))
        self.assertEqual({j['company_id'] for j in self.jobs()},{'C001'})
        self.assertEqual(self.service.status('003',company_ids=('C002',))['items'],[])
        self.assertEqual(self.service.status('003',company_ids=())['counts'],{})

    def test_daily_distinct_case_budget_shared_across_events_channels_and_digest(self):
        self.service=Notifications(self.store,role_config()|dict(daily_budget=5))
        for case in ('RC_1','RC_2','RC_3','RC_4','RC_5','RC_6'):self.submit(case)
        self.plan();status=self.service.status('003')
        self.assertEqual(status['used_by_company']['C001'],5)
        self.assertEqual(len({ref['case_id'] for j in self.jobs() if j['company_id']=='C001' for ref in j['case_refs']}),5)
        self.assertTrue(any(g['reason']=='daily_budget' and g['kind']=='review_submitted' for g in status['routing_gaps']))
        self.now+=timedelta(days=1);self.plan()
        self.assertEqual(len({j['case_refs'][0]['case_id'] for j in self.jobs('review_submitted')}),6)

    def test_history_paging_retains_company_scope_and_total(self):
        self.plan();first=self.service.status('003',company_ids=('C001',),limit=2)
        second=self.service.status('003',company_ids=('C001',),offset=2,limit=2)
        self.assertEqual(first['total'],second['total']);self.assertGreater(first['total'],2)
        self.assertFalse({j['job_id'] for j in first['items']} & {j['job_id'] for j in second['items']})
        self.assertTrue(all(j['company_id']=='C001' for j in first['items']+second['items']))
        with self.assertRaises(ValueError):self.service.status('003',offset=-1)

    def test_backup_restore_keeps_delivery_history_and_dry_run_mode(self):
        from sme_fraud.review_backup import create_backup,restore_backup,restored_store
        self.submit();self.plan();self.service.dispatch()
        before=self.service.status('003')['counts']
        create_backup(self.store.database,self.root/'data',self.root/'reports',self.root/'backup')
        restore_backup(self.root/'backup',self.root/'restored');store=restored_store(self.root/'restored');store.clock=lambda:self.now
        service=Notifications(store,role_config());self.assertEqual(service.status('003')['counts'],before)
        self.assertTrue(service.status('003')['delivery_history_verified']);self.assertEqual(service.dispatch()['processed'],0)

    def test_new_scope_invalidates_queued_workflow_notification(self):
        self.submit();self.plan()
        with self.store.connection() as db:
            row=json.loads(db.execute("SELECT data FROM cases WHERE case_id='RC_1'").fetchone()[0]);row['evidence_digest']='changed'
            db.execute("UPDATE cases SET data=? WHERE case_id='RC_1'",(json.dumps(row),))
        self.service.dispatch();self.assertTrue(all(j['status']=='cancelled' for j in self.jobs('review_submitted')))

    def test_live_baseline_skips_old_transition_but_catches_first_new_one_after_empty_start(self):
        cfg=role_config()|dict(dry_run=False,replay_existing=False,smtp=dict(host='smtp.example.invalid',from_address='sender@example.invalid'))
        transport=MagicMock(side_effect=lambda job,*_:job['job_id'])
        self.service=Notifications(self.store,cfg,transports={'email':transport,'zalo':transport})
        self.plan();self.assertEqual(self.jobs('review_submitted'),[])
        self.submit();self.plan();self.assertEqual(len(self.jobs('review_submitted')),2)
        with self.assertRaises(PermissionError):self.service.dispatch()
        self.service.dispatch(allow_live=True);self.assertTrue(all(j['status']=='sent' for j in self.jobs('review_submitted')))

    def test_live_initialization_does_not_backfill_prior_primary_event(self):
        self.submit();cfg=role_config()|dict(dry_run=False,replay_existing=False,smtp=dict(host='smtp.example.invalid',from_address='sender@example.invalid'))
        self.service=Notifications(self.store,cfg,transports={});self.plan();self.assertEqual(self.jobs('review_submitted'),[])

    def test_retry_history_and_unknown_result_are_preserved_without_resending(self):
        cfg=role_config()|dict(dry_run=False,replay_existing=False,smtp=dict(host='smtp.example.invalid',from_address='sender@example.invalid'))
        mock=MagicMock(side_effect=DeliveryError('rate_limit',retryable=True,retry_after=120))
        self.service=Notifications(self.store,cfg,transports={'email':mock,'zalo':mock});self.plan();self.submit();self.plan()
        self.service.dispatch(allow_live=True);self.assertTrue(all(j['attempts']==1 for j in self.jobs('review_submitted')))
        self.now+=timedelta(seconds=121);mock.side_effect=DeliveryError('unknown',uncertain=True)
        self.service.dispatch(allow_live=True);before=mock.call_count;self.now+=timedelta(hours=1);self.service.dispatch(allow_live=True)
        self.assertEqual(mock.call_count,before)
        job=next(j for j in self.service.status('003')['items'] if j['kind']=='review_submitted')
        self.assertEqual([e['kind'] for e in job['history']],['queued','attempt_started','retry_scheduled','attempt_started','uncertain'])
        self.assertFalse(self.service.status('003')['live_delivery_verified'])

    def test_delivery_history_tampering_blocks_status_and_dispatch(self):
        self.submit();self.plan()
        with self.store.connection() as db:db.execute("UPDATE notification_delivery_events SET kind='fake' WHERE sequence=1")
        with self.assertRaisesRegex(ValueError,'Nhật ký gửi'):self.service.status('003')
        with self.assertRaisesRegex(ValueError,'Nhật ký gửi'):self.service.dispatch()

    def test_deleting_delivery_history_tail_or_whole_log_is_detected(self):
        self.submit();self.plan()
        with self.store.connection() as db:db.execute('DELETE FROM notification_delivery_events')
        with self.assertRaisesRegex(ValueError,'Nhật ký gửi'):self.service.status('003')

    def test_dry_run_never_calls_either_transport(self):
        self.submit();self.plan()
        with patch('smtplib.SMTP',side_effect=AssertionError('network')),patch('sme_fraud.notification_channels.build_opener',side_effect=AssertionError('network')):self.service.dispatch()
        self.assertTrue(self.service.status('003')['counts'].get('simulated'))

    def test_http_scopes_read_and_preview_to_principal_and_denies_accountant_preview(self):
        actors={'A':self.acc,'B':self.chief}
        server=make_server(self.store,port=0,notifications=self.service,review_workflow=self.workflow,identity_provider=lambda request:actors.get(request.headers.get('X-Sim')))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def call(method,path,actor='',body=None,token=''):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            connection.request(method,path,json.dumps(body) if body else None,{'Content-Type':'application/json','X-CSRF-Token':token,'X-Sim':actor})
            response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result
        try:
            token=call('GET','/api/meta')[1]['csrf_token'];self.submit()
            self.assertEqual(call('GET','/api/notifications')[0],403)
            self.assertEqual(call('POST','/api/notifications/preview','A',{'scenario':'003'},token)[0],403)
            code,result=call('POST','/api/notifications/preview','B',{'scenario':'003'},token)
            self.assertEqual(code,200);self.assertEqual({j['company_id'] for j in result['items']},{'C001'})
            code,result=call('GET','/api/notifications?scenario=003','A');self.assertEqual(code,200);self.assertFalse(result['can_preview'])
        finally:server.shutdown();server.server_close();thread.join(5)


class RoleConfigTest(unittest.TestCase):
    def test_reject_unknown_role_missing_identity_wildcard_bad_timing_and_mixed_formats(self):
        bad=[]
        for field,value in [('role','admin'),('user_id',''),('person_id','')]:
            cfg=role_config();cfg['role_recipients']['C001'][0][field]=value;bad.append(cfg)
        cfg=role_config();cfg['role_recipients']['*']=cfg['role_recipients'].pop('C001');bad.append(cfg)
        bad.extend([role_config()|dict(reminders={'repeat_hours':0}),role_config()|dict(reminders={'review_due_hours':True}),role_config()|dict(recipients={'C001':{'zalo':['X']}})])
        for cfg in bad:
            with self.subTest(cfg=cfg),self.assertRaises(ValueError):notification_config(cfg)


if __name__=='__main__':unittest.main()
