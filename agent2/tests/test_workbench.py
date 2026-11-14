"""HTTP UI boundary: no identity bypass, policy disclosure or arbitrary static reads."""
import copy
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest

from sme_fraud.auth import FileAuthorizer
from sme_fraud.review_server import make_server
from test_validation_backend import policy_for


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.token=secrets.token_urlsafe(32);self.policy=policy_for(self.token)
        self.path=Path(self.temp.name)/'policy.json';self.write()
        self.server=make_server(0,FileAuthorizer(self.path))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
    def write(self):self.path.write_text(json.dumps(self.policy),encoding='utf-8')
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5)
    def get(self,path,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            c.request('GET',path,headers=headers or {});r=c.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally:c.close()
    def context(self,**headers):
        return self.get('/api/v1/ui/context',{'Authorization':'Bearer '+self.token,**headers})
    def test_own_memberships_only_and_no_policy_secrets(self):
        member=self.policy['principals'][0]['memberships'][0]
        for cid,status,permissions in [('C002','active',['data.import']),('C003','suspended',['data.import']),('C004','active',[])]:
            new=copy.deepcopy(member);new.update(company_id=cid,status=status,permissions=permissions);self.policy['principals'][0]['memberships'].append(new)
        self.write();status,_,body=self.context();self.assertEqual(status,200)
        value=json.loads(body);self.assertEqual(set(value),{'actor_id','companies'});self.assertEqual(value['companies'],['C001','C002'])
        self.assertNotIn(self.token.encode(),body);self.assertNotIn(b'token_sha256',body);self.assertNotIn(b'permissions',body)
    def test_missing_bad_expired_and_revoked_credentials_are_denied(self):
        self.assertEqual(self.get('/api/v1/ui/context')[0],401)
        self.assertEqual(self.context(Authorization='Bearer '+'x'*40)[0],401)
        self.policy['principals'][0]['expires_at']='2020-01-01T00:00:00+00:00';self.write();self.assertEqual(self.context()[0],401)
        self.policy['principals'][0]['status']='revoked';self.write();self.assertEqual(self.context()[0],401)
    def test_membership_revocation_effective_without_restart(self):
        self.assertEqual(json.loads(self.context()[2])['companies'],['C001'])
        self.policy['principals'][0]['memberships'][0]['status']='revoked';self.write()
        self.assertEqual(json.loads(self.context()[2])['companies'],[])
    def test_host_origin_query_guards_and_no_cors(self):
        for headers in [{'Host':'evil.example'},{'Origin':'https://evil.example'}]:
            self.assertEqual(self.context(**headers)[0],403)
        self.assertEqual(self.get('/api/v1/ui/context?token=secret',{'Authorization':'Bearer '+self.token})[0],400)
        self.assertNotIn('Access-Control-Allow-Origin',self.context()[1])
    def test_static_allowlist_csp_no_secrets_and_utf8(self):
        for path,mime in [('/','text/html'),('/assets/workbench.js','text/javascript'),('/assets/workbench.css','text/css'),('/samples/import-demo.json','application/json')]:
            status,h,body=self.get(path);self.assertEqual(status,200);self.assertTrue(h['Content-Type'].startswith(mime));self.assertEqual(h['Cache-Control'],'no-store')
            self.assertIn("script-src 'self'",h['Content-Security-Policy']);self.assertNotIn(self.token.encode(),body);body.decode('utf-8')
        for path in ['/assets/../auth.py','/assets/%2e%2e/auth.py','/assets/auth-policy.json','/samples/../../auth.py']:
            self.assertNotEqual(self.get(path)[0],200)
    def test_public_sample_is_only_synthetic_not_private_uploads(self):
        data=json.loads(self.get('/samples/import-demo.json')[2]);self.assertEqual(data['tenant_id'],'demo')
        rows=[r for v in data.values() if isinstance(v,list) for r in v]
        self.assertTrue(all(r['source']['is_simulated'] for r in rows));self.assertEqual(len(data['transactions']),5)
        self.assertNotIn('payment_channel',data['transactions'][-1])


if __name__=='__main__':unittest.main()
