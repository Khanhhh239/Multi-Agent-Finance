import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_server import make_server
from company_ml_fixture import fixture, CHIEF, ACCOUNTANT, label_text


class CompanyMLWebTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,_,self.records=fixture(Path(self.temp.name))
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

    def test_incremental_label_api_preview_merge_conflicts_and_explicit_correction(self):
        import csv
        import io
        from test_company_ml_labels import csv_text
        code,state=self.update();self.assertEqual(code,200)
        rows=list(csv.DictReader(io.StringIO(label_text(self.records))))
        base=dict(scenario='003',company_id='C001',expected_revision=state['data']['revision'],labels_text=csv_text(rows[:15]))
        code,state=self.call('POST','/api/company-ml/labels-update',base)
        self.assertEqual(code,200);self.assertEqual(state['data']['labels_count'],15)
        conflict=dict(rows[0],label='1' if rows[0]['label']=='0' else '0')
        base.update(expected_revision=state['data']['revision'],labels_text=csv_text([conflict,rows[15]]))
        code,error=self.call('POST','/api/company-ml/labels-update',base)
        self.assertEqual(code,400);self.assertIn('Chưa lưu',error['error'])
        code,preview=self.call('POST','/api/company-ml/labels-preview',base)
        self.assertEqual(code,200);self.assertEqual(preview['counts']['conflicts'],1)
        code,state=self.call('POST','/api/company-ml/labels-update',base|dict(
            conflict_policy='keep_existing',preview_hash=preview['preview_hash']))
        self.assertEqual(code,200);self.assertEqual(state['data']['labels_count'],16)
        self.assertEqual(state['label_update']['skipped'],1)
        # A preview from before the merge is stale, even when the CSV is identical.
        self.assertEqual(self.call('POST','/api/company-ml/labels-update',base|dict(
            conflict_policy='replace_conflicts',preview_hash=preview['preview_hash'],acknowledge=True,reason='SIM correction'))[0],409)
        base.update(expected_revision=state['data']['revision'])
        code,preview=self.call('POST','/api/company-ml/labels-preview',base);self.assertEqual(code,200)
        correction=base|dict(conflict_policy='replace_conflicts',preview_hash=preview['preview_hash'])
        self.assertEqual(self.call('POST','/api/company-ml/labels-update',correction)[0],400)
        code,state=self.call('POST','/api/company-ml/labels-update',correction|dict(acknowledge=True,reason='SIM verified correction'))
        self.assertEqual(code,200);self.assertEqual(state['data']['labels_count'],16)
        self.assertEqual(state['label_update']['updated'],1)

    def test_label_endpoints_enforce_role_scope_csrf_and_request_fields(self):
        from test_company_ml_labels import csv_text
        import csv
        import io
        _,state=self.update();rows=list(csv.DictReader(io.StringIO(label_text(self.records))))
        base=dict(company_id='C001',expected_revision=state['data']['revision'],labels_text=csv_text(rows[:1]))
        for action in ('labels-preview','labels-update'):
            path='/api/company-ml/'+action
            for actor in ('accountant','foreign','unknown'):
                self.assertEqual(self.call('POST',path,base,actor=actor)[0],403)
            self.assertEqual(self.call('POST',path,base,token='WRONG')[0],403)
            self.assertEqual(self.call('POST',path,base|dict(role='director'))[0],400)
            self.assertEqual(self.call('POST',path,base|dict(expected_revision='STALE'))[0],409)
            self.assertEqual(self.call('POST',path,base|dict(scenario='005'))[0],400)

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

    def test_readiness_endpoint_is_scoped_readonly_and_bound_to_form_snapshot(self):
        code,data=self.update();self.assertEqual(code,200)
        query=dict(scenario='003',company='C001',train_end='2024-01-20T00:00:00+07:00',
                   calibration_end='2024-01-25T00:00:00+07:00',expected_revision=data['data']['revision'],expected_active='')
        path='/api/company-ml/readiness?'+urlencode(query)
        code,result=self.call('GET',path);self.assertEqual(code,200)
        self.assertTrue(result['evaluation']['eligible']);self.assertFalse(result['catboost']['eligible']);self.assertFalse(result['model']['can_score'])
        self.assertEqual(result['data_revision'],data['data']['revision'])
        self.assertEqual(self.call('GET',path,actor='accountant')[0],200)
        for actor in ('','foreign'):self.assertEqual(self.call('GET',path,actor=actor)[0],403)
        self.assertEqual(self.call('GET','/api/company-ml/readiness?'+urlencode(query|dict(expected_revision='STALE')))[0],409)
        self.assertEqual(self.call('GET','/api/company-ml/readiness?'+urlencode(query|dict(scenario='005')))[0],400)


if __name__=='__main__':unittest.main()
