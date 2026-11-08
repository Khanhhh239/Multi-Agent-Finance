import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from sme_fraud.review_server import make_server
from sme_fraud.review_roles import ReviewPrincipal
from company_ml_fixture import CHIEF,ACCOUNTANT
from test_data_import import import_fixture
import test_ml_review_web as fixtures
import test_company_ml_web as helpers


class MLReviewAPITest(unittest.TestCase):
    call=helpers.CompanyMLWebTest.call
    close=helpers.CompanyMLWebTest.close
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.shared.cleanup)
        cls.packet=fixtures.packet_fixture(Path(cls.shared.name))
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        store,_=import_fixture(Path(self.temp.name));store.prepare()
        people={'chief':CHIEF,'accountant':ACCOUNTANT,'foreign':ReviewPrincipal('OTHER','P3','other','director',('C999',))}
        self.server=make_server(store,port=0,qa=True,identity_provider=lambda r:people.get(r.headers.get('X-Test-Actor')),ml_review_roots=[self.packet])
        self.now=[datetime.now(timezone.utc)+timedelta(seconds=5)];self.server.ml_reviews.clock=lambda:self.now[0]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
        self.token=self.call('GET','/api/meta')[1]['csrf_token']
        self.pid=self.call('GET','/api/ml-reviews')[1]['packets'][0]['packet_id']
        self.rid=self.call('GET','/api/ml-reviews/units?'+urlencode(dict(packet=self.pid,company='C001')))[1]['items'][0]['review_id']
    def body(self,**kw):return dict(packet_id=self.pid,review_id=self.rid,**kw)

    def test_assets_blinded_payloads_and_scoped_queues(self):
        for path in ('/ml-reviews','/ml_reviews.js','/ml_reviews.css'):self.assertEqual(self.call('GET',path)[0],200)
        code,data=self.call('GET','/api/ml-reviews',actor='accountant');self.assertEqual(code,200);self.assertEqual(data['packets'][0]['companies'],['C001'])
        path='/api/ml-reviews/detail?'+urlencode(dict(packet=self.pid,review=self.rid))
        code,data=self.call('GET',path,actor='accountant');self.assertEqual(code,200)
        for key in ('algorithm','score','rank','token_hash'):self.assertNotIn('"'+key+'"',json.dumps(data))
        self.assertEqual(self.call('GET','/api/ml-reviews',actor='')[0],403)
        self.assertEqual(self.call('GET',path,actor='foreign')[0],403)
        self.assertEqual(self.call('GET','/api/ml-reviews/summary?packet='+self.pid,actor='accountant')[0],403)

    def test_timer_draft_submit_reload_export_and_summary_no_implicit_model_activation(self):
        before=self.call('GET','/api/company-ml/status?company=C001')[1]
        code,started=self.call('POST','/api/ml-reviews/timer',self.body(expected_revision=0,action='start'));self.assertEqual(code,200)
        self.now[0]+=timedelta(seconds=4)
        code,paused=self.call('POST','/api/ml-reviews/timer',self.body(expected_revision=1,action='pause',timer_token=started['timer_token']))
        self.assertEqual(code,200);self.assertEqual(paused['work']['timer']['confirmed_ms'],4000)
        body=self.body(expected_revision=2,form=fixtures.FORM,submit=True,acknowledge=True)
        code,saved=self.call('POST','/api/ml-reviews/save',body);self.assertEqual(code,200,saved)
        self.assertEqual(saved['work']['status'],'reviewed');self.assertEqual(saved['work']['owner']['user_id'],CHIEF.user_id)
        self.assertEqual(self.call('POST','/api/ml-reviews/save',body)[0],409)
        code,summary=self.call('GET','/api/ml-reviews/summary?packet='+self.pid);self.assertEqual(code,200);self.assertEqual(summary['metrics'],[])
        self.assertEqual(summary['reviewed'],1);self.assertFalse(summary['complete'])
        code,text=self.call('GET','/api/ml-reviews/export?packet='+self.pid);self.assertEqual(code,200);self.assertIn('SIM_CHIEF',text)
        self.assertEqual(self.call('GET','/api/company-ml/status?company=C001')[1]['active_version'],before['active_version'])

    def test_csrf_unknown_fields_other_company_and_ownership_are_rejected(self):
        body=self.body(expected_revision=0,action='start')
        self.assertEqual(self.call('POST','/api/ml-reviews/timer',body,token='wrong')[0],403)
        self.assertEqual(self.call('POST','/api/ml-reviews/timer',body|dict(reviewer_id='FAKE'))[0],400)
        self.assertEqual(self.call('POST','/api/ml-reviews/timer',body,actor='accountant')[0],200)
        self.assertEqual(self.call('POST','/api/ml-reviews/timer',self.body(expected_revision=1,action='recover'))[0],403)
        c2=self.call('GET','/api/ml-reviews/units?'+urlencode(dict(packet=self.pid,company='C002')))[1]['items'][0]['review_id']
        self.assertEqual(self.call('POST','/api/ml-reviews/timer',body|dict(review_id=c2),actor='accountant')[0],403)


if __name__=='__main__':unittest.main()
