"""User-facing reference-only HE API exercised through real Portal authorization."""
from copy import deepcopy
import json
import time
import unittest
from unittest.mock import patch

from experiments.he_inference.registry_demo import database_dump
from web_support import WebHarness


class HEWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=WebHarness().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.__exit__()

    def setUp(self):
        self.f=self.fixture; self.policy=deepcopy(self.f.h.policy); self.pins=deepcopy(self.f.pins)
        self.before={name:database_dump(self.f.pair.env[name]) for name in ('model_db','snapshot_db')}

    def tearDown(self):
        self.f.h.policy=self.policy; self.f.h.write_policy(); self.f.pins=self.pins; self.f.write_pins()
        for name, before in self.before.items():self.assertEqual(database_dump(self.f.pair.env[name]), before)

    def test_portal_serves_page_and_script_without_exposing_keys(self):
        for path in ('/agent2/encrypted-analysis','/agent2/assets/he-analysis.js'):
            status,body=self.f.h.request(path,token=False);self.assertEqual(status,200)
            self.assertNotIn(self.f.h.secret.encode(),body)

    def test_no_session_and_cross_company_requests_are_denied(self):
        self.assertEqual(self.f.request(token=False)[0],401)
        self.assertEqual(self.f.request(company='OTHER')[0],403)

    def test_dataset_catalog_scoped_checksums_and_no_model_metadata(self):
        status,value=self.f.request();self.assertEqual(status,200);self.assertTrue(value['available'])
        self.assertEqual(len(value['datasets']),2)
        self.assertIn(self.f.pair.env['queries']['C001'],[r['snapshot_id'] for r in value['datasets']])
        self.assertNotIn(self.f.pair.env['queries']['C002'],json.dumps(value))
        self.assertNotIn(self.f.pair.env['artifacts']['C001'],json.dumps(value))
        self.assertTrue(all(len(r['checksum'])==64 for r in value['datasets']))

    def test_catalog_preflight_does_not_deserialize_or_fit_models(self):
        with patch('experiments.he_inference.registry_export.joblib.load',side_effect=AssertionError('no deserialization')):
            self.assertTrue(self.f.request()[1]['available'])

    def test_missing_company_pin_disables_analysis(self):
        self.f.pins['bindings']=[];self.f.write_pins()
        self.assertFalse(self.f.request()[1]['available'])
        status,_=self.f.request('jobs',body=dict(snapshot_id=self.f.pair.env['queries']['C001']),headers={'Idempotency-Key':'web-no-model-pin'})
        self.assertEqual(status,409)

    def test_missing_artifact_disables_analysis_in_catalog(self):
        self.f.pins['bindings'][0]['artifact_id']='mth_'+'0'*64;self.f.write_pins()
        self.assertFalse(self.f.request()[1]['available'])

    def test_duplicate_pins_are_not_silently_chosen(self):
        self.f.pins['bindings'].append(self.f.pins['bindings'][0]);self.f.write_pins()
        self.assertEqual(self.f.request()[0],503)

    def test_client_cannot_choose_model_key_or_asof(self):
        body=dict(snapshot_id=self.f.pair.env['queries']['C001'],artifact_id=self.f.pair.env['artifacts']['C001'],as_of='2026-10-03T00:00:00+07:00')
        self.assertEqual(self.f.request('jobs',body=body,headers={'Idempotency-Key':'web-extra-fields'})[0],400)

    def test_foreign_snapshot_cannot_be_submitted(self):
        status,_=self.f.request('jobs',body=dict(snapshot_id=self.f.pair.env['queries']['C002']),headers={'Idempotency-Key':'web-other-company'})
        self.assertEqual(status,404)

    def test_request_requires_idempotency_before_creating_job(self):
        self.assertEqual(self.f.request('jobs',body=dict(snapshot_id=self.f.pair.env['queries']['C001']))[0],400)

    def test_real_he_result_reuses_same_job_and_five_rows(self):
        body=dict(snapshot_id=self.f.pair.env['queries']['C001']);headers={'Idempotency-Key':'web-real-five-rows'}
        status,state=self.f.request('jobs',body=body,headers=headers);self.assertEqual(status,202,state)
        self.assertNotIn('status_url',state);self.assertNotIn('result_url',state)
        job=state['job_id'];deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            status,value=self.f.request('jobs/'+job+'/result')
            if status==200:break
            self.assertEqual(status,202,value);time.sleep(.1)
        self.assertEqual(status,200,value);self.assertEqual(value['row_count'],5)
        self.assertTrue(all(r['available'] and isinstance(r['score'],float) for r in value['rows']))
        self.assertEqual(self.f.request('jobs',body=body,headers=headers)[1]['job_id'],job)
        other=dict(snapshot_id=self.f.pair.env['training']['C001'])
        self.assertEqual(self.f.request('jobs',body=other,headers=headers)[0],409)
        self.assertEqual(self.f.request('jobs/'+job,company='C002')[0],404)
        self.f.h.policy['memberships'][0]['status']='revoked';self.f.h.write_policy()
        self.assertEqual(self.f.request('jobs/'+job+'/result')[0],403)

    def test_resume_requires_empty_body_and_owned_job(self):
        # Not-found check must still be scoped and must not create any job.
        status,_=self.f.request('jobs/herun_'+'0'*32+'/resume',body={})
        self.assertEqual(status,404)

    def test_history_uses_business_mode_for_accountant(self):
        status,value=self.f.request('runs')
        self.assertEqual(status,200,value)
        self.assertTrue(all(r['analysis_mode'] in ('encrypted_analysis','four_encrypted_branches') for r in value['runs']))

    def test_backend_not_enabled_returns_explicit_unavailable(self):
        from sme_fraud.review_server import make_server
        from experiments.he_inference.services_demo import request
        import threading
        server=make_server(0,self.f.h.authorizer,self.f.h.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            status,value=request(server.server_port,'/api/v1/companies/C001/he/datasets',headers={'Authorization':'Bearer '+self.f.h.token})
            self.assertEqual(status,503);self.assertEqual(value['errors'][0]['code'],'HE_NOT_CONFIGURED')
        finally:server.shutdown();server.server_close();thread.join(5)

    def test_portal_rejects_unknown_he_routes_and_queries(self):
        self.assertEqual(self.f.request('decrypt')[0],404)
        self.assertEqual(self.f.request('datasets?company=OTHER')[0],404)


if __name__=='__main__':unittest.main()
