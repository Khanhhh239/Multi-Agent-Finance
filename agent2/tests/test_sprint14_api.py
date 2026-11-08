"""HTTP integration of quick decisions, daily recommendations and notification preview."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime

from test_review import make_fixture
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_server import make_server
from sme_fraud.notifications import Notifications


class Sprint14ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.store = ReviewStore(self.root/'data',self.root/'reports',self.root/'cache.sqlite3',
            clock=lambda:datetime.fromisoformat('2026-10-13T09:00:00+07:00'))
        self.store.prepare()
        self.server = make_server(self.store,port=0,qa=True)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.token = self.request('GET','/api/meta')[1]['csrf_token']

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()

    def request(self,method,path,body=None,csrf=True):
        connection = http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        headers={'Content-Type':'application/json'}
        if csrf and hasattr(self,'token'): headers['X-CSRF-Token']=self.token
        connection.request(method,path,json.dumps(body) if body is not None else None,headers)
        response=connection.getresponse()
        content=response.read()
        result=json.loads(content) if response.getheader('Content-Type','').startswith('application/json') else content
        status=response.status
        connection.close()
        return status,result

    def test_asset_routes_csp_and_daily_priority_filter(self):
        for path in ('/','/case_graph.js','/vendor/cytoscape.min.js'):
            self.assertEqual(self.request('GET',path)[0],200)
        self.assertEqual(self.request('GET','/vendor/manifest.json')[0],404)
        _,result=self.request('GET','/api/cases?scenario=003&company=C001&daily=1')
        self.assertEqual(len(result['items']),5)
        self.assertEqual(result['items'][0]['case_id'],'RC_6')
        self.assertTrue(result['daily_selection'])

    def test_quick_decision_requires_reason_and_retains_optimistic_audit(self):
        body=dict(scenario='003',case_id='RC_6',decision='confirmed_suspicion',reviewer='QA',reason='',expected_hash='')
        self.assertEqual(self.request('POST','/api/feedback',body)[0],400)
        body['reason']='Đã đối chiếu, chuyển kiểm tra sâu'
        status,event=self.request('POST','/api/feedback',body)
        self.assertEqual(status,200)
        self.assertEqual(event['decision'],'confirmed_suspicion')
        self.assertEqual(self.request('POST','/api/feedback',body)[0],409)
        _,detail=self.request('GET','/api/case?scenario=003&id=RC_6')
        self.assertEqual(detail['case']['status'],'closed')
        self.assertEqual(len(detail['feedback_history']),1)

    def test_missing_case_is_vietnamese_404_without_repr_quotes_and_recovers(self):
        message = 'Không tìm thấy hồ sơ trong bộ dữ liệu này. Kiểm tra mã hồ sơ hoặc chọn hồ sơ khác trong hàng đợi.'
        with self.store.connection() as db:
            before = db.execute('SELECT COUNT(*) FROM admissions').fetchone()[0]
        for method, path, body in (
            ('GET', '/api/case?scenario=003&id=MISSING_CASE', None),
            ('GET', '/api/case?scenario=003&id=', None),
            ('POST', '/api/admit', dict(scenario='003', case_id='MISSING_CASE')),
        ):
            with self.subTest(method=method, path=path):
                status, result = self.request(method, path, body)
                self.assertEqual(status, 404)
                self.assertEqual(result, dict(error=message))
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], before)
        status, detail = self.request('GET', '/api/case?scenario=003&id=RC_6')
        self.assertEqual(status, 200)
        self.assertEqual(detail['case']['case_id'], 'RC_6')
        self.assertEqual(self.request('GET', '/api/unknown')[1], dict(error='Không tìm thấy nội dung yêu cầu.'))

    def test_preview_csrf_and_company_scoped_metadata_does_not_expose_recipient_or_secrets(self):
        self.assertEqual(self.request('POST','/api/notifications/preview',{},csrf=False)[0],403)
        code,result=self.request('POST','/api/notifications/preview',{'scenario':'003'})
        self.assertEqual(code,200)
        self.assertEqual(result['mode'],'dry_run')
        self.assertEqual(result['used_by_company']['C001'],5)
        self.assertGreater(result['counts']['simulated'],0)
        for job in result['items']:
            self.assertIn(f'http://127.0.0.1:{self.port}/#scenario=003&case=', job['body'])
            self.assertEqual(job['body'], job['preview_body'])
            for link in job['case_links']:
                self.assertEqual(link['url'], f'http://127.0.0.1:{self.port}/#scenario=003&case='+link['case_id'])
        self.assertNotIn('recipient',json.dumps(result))
        self.assertNotIn('access_token',json.dumps(result))
        self.assertEqual(self.request('POST','/api/webhooks/zalo',{})[0],403)

    def test_live_service_never_sends_from_browser_preview(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        service=Notifications(self.store,dict(dry_run=False,recipients={'C001':{'zalo':['GROUP']}}))
        self.server=make_server(self.store,port=0,qa=True,notifications=service)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port
        self.token=self.request('GET','/api/meta')[1]['csrf_token']
        self.assertEqual(self.request('POST','/api/notifications/preview',{})[0],403)
        self.assertEqual(self.request('GET','/api/notifications')[1]['counts'],{})
