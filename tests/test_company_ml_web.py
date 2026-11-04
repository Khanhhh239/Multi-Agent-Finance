import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_server import make_server
from company_ml_fixture import fixture, CHIEF, ACCOUNTANT


class CompanyMLWebTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,_,_=fixture(Path(self.temp.name))
        self.people={'chief':CHIEF,'accountant':ACCOUNTANT,
            'foreign':ReviewPrincipal('SIM_OTHER','SIM_P3','Mô phỏng','director',('C003',))}
        self.server=make_server(self.store,port=0,identity_provider=lambda r:self.people.get(r.headers.get('X-Test-Actor')))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.token=self.call('GET','/api/meta')[1]['csrf_token']

    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5)
    def call(self,method,path,body=None,actor='chief',token=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)
        connection.request(method,path,json.dumps(body) if body is not None else None,
            {'Content-Type':'application/json','X-CSRF-Token':token if token is not None else getattr(self,'token',''),'X-Test-Actor':actor})
        response=connection.getresponse();raw=response.read();content=response.getheader('Content-Type')
        result=json.loads(raw) if 'application/json' in content else raw.decode('utf-8')
        code=response.status;connection.close();return code,result
    def update(self):
        return self.call('POST','/api/company-ml/data-update',dict(scenario='003',company_id='C001',expected_revision=None))

    def test_web_page_assets_and_navigation_are_served_with_correct_mimes(self):
        for path in ('/company-ml','/company_ml.js','/company_ml.css'):
            self.assertEqual(self.call('GET',path)[0],200)
        self.assertIn('/company-ml',self.call('GET','/')[1])
        self.assertIn('Cập nhật dữ liệu',self.call('GET','/company-ml')[1])

    def test_anonymous_accountant_and_foreign_cannot_change_company_ml(self):
        for actor in ('','accountant','foreign'):
            self.assertEqual(self.call('POST','/api/company-ml/data-update',dict(company_id='C001',expected_revision=None),actor=actor)[0],403)
        self.assertEqual(self.call('GET','/api/company-ml',actor='')[1]['companies'],[])
        self.assertFalse(self.call('GET','/api/company-ml',actor='accountant')[1]['can_manage'])
        self.assertEqual(self.call('GET','/api/company-ml/status?company=C001&scenario=003',actor='foreign')[0],403)

    def test_csrf_input_validation_and_holdout_guard(self):
        body=dict(company_id='C001',expected_revision=None)
        self.assertEqual(self.call('POST','/api/company-ml/data-update',body,token='wrong')[0],403)
        self.assertEqual(self.call('POST','/api/company-ml/data-update',body|{'role':'director'})[0],400)
        self.assertEqual(self.call('POST','/api/company-ml/data-update',{'company_id':'C001'})[0],400)
        self.assertEqual(self.call('POST','/api/company-ml/data-update',body|{'scenario':'005'})[0],400)

    def test_http_complete_flow_and_stale_selection_never_activates_silently(self):
        code,data=self.update();self.assertEqual(code,200);self.assertIsNone(data['active_version'])
        base=dict(scenario='003',company_id='C001',expected_revision=data['data']['revision'])
        evaluate=base|dict(algorithm='ecod',train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00',alert_budget=.1)
        code,data=self.call('POST','/api/company-ml/evaluate',evaluate)
        self.assertEqual(code,200);self.assertIsNone(data['active_version'])
        version=data['versions'][0]['version_id']
        activate=base|dict(version_id=version,expected_active=None)
        self.assertEqual(self.call('POST','/api/company-ml/activate',activate)[0],200)
        self.assertEqual(self.call('POST','/api/company-ml/activate',activate)[0],409)
        code,result=self.call('POST','/api/company-ml/score',base|dict(expected_active=version))
        self.assertEqual(code,200);self.assertEqual(result['run']['version_id'],version)
        self.assertTrue(all(r['company_id']=='C001' for r in result['items']))
        self.assertEqual(self.call('POST','/api/company-ml/keep',base|dict(expected_active=version))[0],200)


if __name__=='__main__':unittest.main()
