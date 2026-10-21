"""Real SQLite state, outbox workers and mocked external transports; no messages sent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from test_review import make_fixture
from sme_fraud.review_store import ReviewStore
from sme_fraud.notifications import Notifications, notification_config
from sme_fraud.notification_channels import DeliveryError, smtp_send, zalo_send, zalo_request


class NotificationsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data, self.report = make_fixture(self.root)
        self.when = [datetime.fromisoformat('2026-10-13T09:00:00+07:00')]
        self.store = ReviewStore(self.root/'data', self.root/'reports', self.root/'cache.sqlite3', clock=lambda:self.when[0])
        self.store.prepare()
        self.config = dict(dry_run=True, replay_existing=True, daily_budget=5)
        self.service = Notifications(self.store, self.config)

    def tearDown(self):
        self.temporary.cleanup()

    def test_ranked_daily_selection_keeps_backlog_and_is_not_changed_by_search(self):
        result = self.store.list_cases('003', company='C001', daily=True)
        self.assertEqual([r['case_id'] for r in result['items']], ['RC_6','RC_5','RC_4','RC_3','RC_2'])
        self.assertEqual(self.store.list_cases('003',company='C001',query='RC_1',daily=True)['total'],0)
        self.assertEqual(self.store.list_cases('003',company='C001')['total'],8)
        self.store.admit('003','RC_6')
        self.store.save_feedback('003','RC_6','confirmed_suspicion','Reviewer','Chứng từ cần điều tra sâu','')
        daily = self.store.list_cases('003',company='C001',daily=True)
        self.assertEqual(len(daily['items']),4)
        self.assertNotIn('RC_1',[r['case_id'] for r in daily['items']])
        self.assertEqual(self.store.detail('003','RC_6')['case']['feedback']['decision'],'confirmed_suspicion')

    def test_high_priority_and_digest_share_company_case_budget_across_channels(self):
        self.service.plan('003')
        saved = self.service.status('003')
        self.assertEqual(saved['used_by_company'],{'C001':5,'C002':1})
        high = [r for r in saved['items'] if r['kind']=='high_priority' and r['company_id']=='C001']
        self.assertEqual(len(high),10)
        refs = {r['case_refs'][0]['case_id'] for r in high}
        self.assertEqual(refs,{'RC_2','RC_3','RC_4','RC_5','RC_6'})
        digest_jobs = [r for r in saved['items'] if r['kind']=='weekly' and r['company_id']=='C001']
        self.assertEqual({r['case_id'] for r in digest_jobs[0]['case_refs']},refs)
        self.assertEqual(digest_jobs[0]['total_open'],8)

    def test_fake_mode_never_calls_network_and_restarts_do_not_repeat_jobs(self):
        self.service.plan('003')
        with patch('smtplib.SMTP',side_effect=AssertionError('network')), patch('sme_fraud.notification_channels.build_opener',side_effect=AssertionError('network')):
            self.service.dispatch()
        count = self.service.status('003')['counts']['simulated']
        restarted = Notifications(self.store,self.config)
        restarted.plan('003')
        self.assertEqual(restarted.dispatch()['processed'],0)
        self.assertEqual(restarted.status('003')['counts']['simulated'],count)

    def test_explicit_dry_run_company_scope_does_not_add_other_mock_recipients(self):
        scoped=Notifications(self.store,dict(dry_run=True,recipients={'C001':{'email':['simulation@example.invalid']}}))
        scoped.plan('003');scoped.dispatch()
        self.assertEqual(set(scoped.status('003')['used_by_company']),{'C001'})
        self.assertEqual({j['company_id'] for j in scoped.status('003')['items']},{'C001'})

    def test_current_preview_rebases_links_without_rewriting_simulated_history(self):
        self.service.plan('003'); self.service.dispatch()
        with self.store.connection() as db:
            before = [tuple(row) for row in db.execute('SELECT * FROM notification_outbox ORDER BY job_id')]
        changed = Notifications(self.store, self.config | dict(case_url='http://127.0.0.1:8771/'))
        result = changed.status('003')
        self.assertEqual({j['channel'] for j in result['items']}, {'email', 'zalo'})
        for job in result['items']:
            self.assertIn('http://127.0.0.1:8765/', job['body'])
            self.assertNotIn('http://127.0.0.1:8765/', job['preview_body'])
            for ref in job['case_refs']:
                link = f'http://127.0.0.1:8771/#scenario=003&case='+ref['case_id']
                self.assertIn(link, job['preview_body'])
                self.assertIn(dict(case_id=ref['case_id'], url=link), job['case_links'])
        with self.store.connection() as db:
            after = [tuple(row) for row in db.execute('SELECT * FROM notification_outbox ORDER BY job_id')]
        self.assertEqual(before, after)
        self.assertEqual(changed.dispatch()['processed'], 0)

    def test_preview_only_rebases_referenced_cases_and_keeps_live_history_unchanged(self):
        job = dict(body='http://old/#scenario=003&case=RC_6 http://old/#scenario=001&case=RC_6 http://old/#scenario=003&case=OTHER',
                   case_refs=[dict(case_id='RC_6', scope_hash='scope')])
        self.service.preview_links('003', job)
        self.assertEqual(job['preview_body'], 'http://127.0.0.1:8765/#scenario=003&case=RC_6 http://old/#scenario=001&case=RC_6 http://old/#scenario=003&case=OTHER')
        live = Notifications(self.store, dict(dry_run=False, case_url='https://review.example/',
            recipients={'C001': {'zalo': ['GROUP']}}))
        original = {k:v for k,v in job.items() if k in {'body','case_refs'}}
        live.preview_links('003', original)
        self.assertEqual(set(original), {'body','case_refs'})

    def test_new_payload_uses_explicit_case_url_for_both_channels(self):
        service = Notifications(self.store, self.config | dict(case_url='http://127.0.0.1:8779/'))
        service.plan('003'); service.dispatch()
        jobs = service.status('003')['items']
        self.assertEqual({j['channel'] for j in jobs}, {'email','zalo'})
        self.assertTrue(all('http://127.0.0.1:8779/#scenario=003&case=' in j['body'] for j in jobs))

    def test_pending_delivery_is_cancelled_after_recipient_removed_from_configuration(self):
        self.service.plan('003')
        changed=Notifications(self.store,dict(dry_run=True,recipients={'C001':{'email':['simulation@example.invalid']}}))
        changed.dispatch()
        with self.store.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT company_id,channel,status,error_code FROM notification_outbox')]
        self.assertTrue(all(r['status']=='cancelled' and r['error_code']=='recipient_removed' for r in rows if r['company_id']!='C001' or r['channel']=='zalo'))
        self.assertTrue(any(r['status']=='simulated' for r in rows))

    def test_concurrent_planners_and_dispatchers_respect_quota_and_claim_jobs_once(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _: self.service.plan('003'),range(3)))
        self.assertEqual(self.service.status('003')['used_by_company']['C001'],5)
        with ThreadPoolExecutor(max_workers=3) as pool:
            processed = list(pool.map(lambda _: self.service.dispatch()['processed'],range(3)))
        self.assertEqual(sum(processed),self.service.status('003')['counts']['simulated'])

    def test_next_day_consumes_remaining_high_priority_without_repeating_previous_ones(self):
        self.service.plan('003'); self.service.dispatch()
        self.when[0] += timedelta(days=1)
        self.service.plan('003')
        status = self.service.status('003')
        self.assertEqual(status['used_by_company'],{'C001':1})
        jobs = [r for r in status['items'] if r['status']=='pending']
        self.assertEqual({r['case_refs'][0]['case_id'] for r in jobs},{'RC_1'})

    def test_closure_or_evidence_change_cancels_pending_delivery(self):
        self.service.plan('003')
        self.store.save_feedback('003','RC_6','false_positive','Reviewer','Đã đối chiếu đầy đủ','')
        self.service.dispatch()
        saved = self.service.status('003')
        self.assertGreaterEqual(saved['counts']['cancelled'],2)
        self.assertFalse(any(j['status']=='simulated' and any(r['case_id']=='RC_6' for r in j['case_refs']) for j in saved['items']))
        self.assertTrue(any(j['kind']=='weekly' and j['status']=='simulated' for j in saved['items']))

    def live_service(self, transport):
        cfg = dict(dry_run=False,replay_existing=False,daily_budget=5,
            recipients={'C001':{'zalo':['GROUP1']}})
        return Notifications(self.store,cfg,transports={'zalo':transport})

    def test_live_requires_explicit_worker_and_dry_jobs_are_never_promoted(self):
        self.service.plan('003'); self.service.dispatch()
        transport = MagicMock(return_value='PROVIDER')
        live = self.live_service(transport)
        live.plan('003')
        with self.assertRaises(PermissionError): live.dispatch()
        live.dispatch(allow_live=True)
        # Existing cases are baselined, but the scheduled weekly summary is allowed.
        self.assertEqual(transport.call_count,1)
        self.assertEqual(live.status('003')['counts'],{'sent':1})
        self.assertTrue(all(j['kind']=='weekly' for j in live.status('003')['items']))

    def test_retry_backoff_and_unknown_delivery_are_distinct(self):
        transport = MagicMock(side_effect=[DeliveryError('rate_limit',retryable=True,retry_after=120),'PROVIDER'])
        live = self.live_service(transport)
        live.plan('003'); live.dispatch(allow_live=True)
        self.assertEqual(live.status('003')['counts'],{'pending':1})
        self.assertEqual(live.dispatch(allow_live=True)['processed'],0)
        self.when[0] += timedelta(seconds=121)
        live.dispatch(allow_live=True)
        self.assertEqual(live.status('003')['counts'],{'sent':1})
        self.when[0] += timedelta(days=7)
        transport.side_effect = DeliveryError('timeout',uncertain=True)
        live.plan('003'); live.dispatch(allow_live=True)
        self.assertEqual(live.status('003')['counts']['uncertain'],1)
        self.when[0] += timedelta(hours=1)
        live.dispatch(allow_live=True)
        self.assertEqual(transport.call_count,3)

    def test_permanent_failure_exhausted_retries_and_interrupted_worker_do_not_loop(self):
        live = self.live_service(MagicMock(side_effect=DeliveryError('denied')))
        live.plan('003'); live.dispatch(allow_live=True)
        self.assertEqual(live.status('003')['counts'],{'failed':1})
        self.when[0] += timedelta(days=7)
        live.plan('003')
        with self.store.connection() as db:
            db.execute("UPDATE notification_outbox SET status='sending',claimed_at=? WHERE mode='live' AND status='pending'",((self.when[0]-timedelta(minutes=6)).isoformat(),))
        live.dispatch(allow_live=True)
        self.assertEqual(live.status('003')['counts']['uncertain'],1)

    def test_new_high_scope_after_live_baseline_is_not_mistaken_for_backfill(self):
        live = self.live_service(MagicMock(return_value='PROVIDER'))
        live.plan('003'); live.dispatch(allow_live=True)
        self.when[0] += timedelta(days=1)
        with self.store.connection() as db:
            record = db.execute("SELECT data FROM cases WHERE scenario='003' AND case_id='RC_6'").fetchone()
            changed = json.loads(record[0]); changed['evidence_digest']='new_evidence'
            db.execute("UPDATE cases SET data=? WHERE scenario='003' AND case_id='RC_6'",(json.dumps(changed),))
        live.plan('003')
        self.assertTrue(any(j['kind']=='high_priority' for j in live.status('003')['items']))

    def test_signed_receipts_reject_tampering_expiry_and_replay_and_cannot_close_case(self):
        live = self.live_service(MagicMock(return_value='PROVIDER'))
        live.config['zalo']={'app_id':'APP','webhook_secret_env':'SPRINT14_WEBHOOK_SECRET'}
        live.plan('003');live.dispatch(allow_live=True)
        content=json.dumps(dict(app_id='APP',timestamp=str(int(self.when[0].timestamp()*1000)),
            event_name='user_received_message',message={'msg_ids':['PROVIDER','UNKNOWN']})).encode()
        signature='mac='+hashlib.sha256(b'APP'+content+str(int(self.when[0].timestamp()*1000)).encode()+b'SECRET').hexdigest()
        with patch.dict(os.environ,{'SPRINT14_WEBHOOK_SECRET':'SECRET'}):
            with self.assertRaises(PermissionError): live.receive_zalo(content,'mac=wrong')
            self.assertEqual(live.receive_zalo(content,signature)['matched'],1)
            self.assertEqual(live.receive_zalo(content,signature)['matched'],0)
            self.assertEqual(live.status('003')['receipt_counts'],{'user_received_message':1})
            self.when[0] += timedelta(minutes=6)
            with self.assertRaises(PermissionError): live.receive_zalo(content,signature)
        self.assertEqual(self.store.feedback_state('003')[0],{})


class ChannelTest(unittest.TestCase):
    def test_configuration_disallows_unscoped_recipients_insecure_smtp_and_live_replay(self):
        for raw in ({'dry_run':False},{'daily_budget':7},{'dry_run':'false'},
            {'recipients':{'C001':{'email':['a@b\r\nBcc:bad']}}},
            {'dry_run':False,'replay_existing':True,'recipients':{'C001':{'zalo':['G']}}}):
            with self.subTest(raw=raw),self.assertRaises(ValueError): notification_config(raw)

    def test_zalo_request_contract_and_error_does_not_expose_token(self):
        job=dict(recipient='GROUP',subject='Sổ Soát',body='C001',job_id='job')
        request=zalo_request(job,'PRIVATE_TOKEN')
        self.assertEqual(request.full_url,'https://openapi.zalo.me/v3.0/oa/group/message')
        self.assertEqual(json.loads(request.data)['recipient'],{'group_id':'GROUP'})
        with patch.dict(os.environ,{'SME_ZALO_OA_TOKEN':'PRIVATE_TOKEN'}),patch('sme_fraud.notification_channels.build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=b'{"error":-216,"message":"PRIVATE_TOKEN"}'
            with self.assertRaises(DeliveryError) as failed: zalo_send(job,{},None)
            self.assertEqual(str(failed.exception),'zalo_api_-216')

    def test_smtp_starttls_and_stable_message_id(self):
        from datetime import datetime, timezone
        job=dict(recipient='review@example.invalid',subject='Thử',body='C001',job_id='fixed')
        config={'smtp':{'host':'smtp.example.invalid','from_address':'sender@example.invalid','username':'user'}}
        with patch.dict(os.environ,{'SME_SMTP_PASSWORD':'PRIVATE'}),patch('smtplib.SMTP') as smtp:
            smtp.return_value.send_message.return_value={}
            provider=smtp_send(job,config,datetime.now(timezone.utc))
            self.assertEqual(provider,'<fixed@sosoat.local>')
            smtp.return_value.starttls.assert_called_once()
            smtp.return_value.login.assert_called_once_with('user','PRIVATE')
            smtp.return_value.close.assert_called_once()
