"""Real Portal/Agent2 HTTP boundary, isolated policies, sessions and SQLite only."""
from contextlib import closing, ExitStack
import http.client
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from portal import server as portal
from sme_fraud.auth import AuthError
from sme_fraud.import_files import canonical
from sme_fraud.portal_auth import PortalAuthorizer
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields

SAMPLE=Path(__file__).resolve().parents[1]/'sme_fraud/web/import-demo.json'


class PortalHarness:
    def __enter__(self):
        self.stack=ExitStack();self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.access=self.root/'access.json';self.secret=secrets.token_urlsafe(32)
        self.policy=dict(version='portal-agent2-access/1.0.0',actor_id='portal-reviewer',tenant_id='demo',status='active',memberships=[dict(company_id=cid,role=role,status='active',permissions=['data.import']) for cid,role in [('C001','accountant'),('C002','director')]])
        self.write_policy()
        for name,value in dict(WORK=self.root,PENDING=self.root/'pending',LOGS=self.root/'logs',SECURITY_FILE=self.root/'security.json',AUDIT_FILE=self.root/'audit.jsonl',BATCH_FILE=self.root/'batches.json',COMPANY_FILE=self.root/'company.json',SESSIONS={},AGENT2_TOKEN=self.secret,PROCS={},FAILS={'n':0,'until':0.0}).items():self.stack.enter_context(patch.object(portal,name,value))
        portal.PENDING.mkdir();portal.LOGS.mkdir()
        self.portal=portal.ThreadingHTTPServer(('127.0.0.1',0),portal.Handler);self.portal_url=f'http://127.0.0.1:{self.portal.server_port}'
        self.authorizer=PortalAuthorizer(self.portal_url,self.secret)
        self.store=SnapshotStore(self.root/'snapshots.sqlite3');self.resources=AnalysisResources();self.agent=make_server(0,self.authorizer,self.store,self.resources)
        config=dict(port=self.portal.server_port,agents={'agent2':{'port':self.agent.server_port,'access_file':str(self.access)}})
        self.stack.enter_context(patch.object(portal,'CFG',config));self.stack.enter_context(patch.object(portal,'ORIGIN',self.portal_url));self.stack.enter_context(patch.object(portal,'ORIGINS',(self.portal_url,f'http://localhost:{self.portal.server_port}')))
        self.threads=[]
        for server in (self.portal,self.agent):
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.threads.append(thread)
        self.token=portal.new_session();self.data=json.loads(SAMPLE.read_text('utf-8'))
        return self
    def write_policy(self):self.access.write_text(json.dumps(self.policy),encoding='utf-8')
    def __exit__(self,*exc):
        for server in (self.agent,self.portal):server.shutdown();server.server_close()
        for thread in self.threads:thread.join(5)
        self.stack.close()
    def request(self,path,body=None,*,method=None,headers=None,token=True,agent=False):
        h={'X-Platform':'1'}
        if token:h['X-Session']=self.token
        if body is not None:h['Content-Type']='application/json'
        h.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1',self.agent.server_port if agent else self.portal.server_port,timeout=30)
        try:
            c.request(method or ('POST' if body is not None else 'GET'),path,body=body if isinstance(body,bytes) else canonical(body) if body is not None else None,headers=h)
            r=c.getresponse();raw=r.read()
            return r.status,json.loads(raw) if r.headers.get('Content-Type','').startswith('application/json') else raw
        finally:c.close()
    def url(self,path,company='C001'):return '/agent2/api/v1/companies/'+company+'/'+path
    def preview(self,company='C001',data=None):
        status,draft=self.request(self.url('imports/upload',company),canonical(data or self.data),headers={'X-File-Name':'demo.json','Idempotency-Key':secrets.token_hex(16)})
        if status!=201:raise AssertionError((status,draft))
        status,report=self.request(self.url('imports/'+draft['import_id']+'/preview',company),{'expected_revision':draft['revision']})
        if status!=200:raise AssertionError((status,report))
        return draft,report
    def commit(self,company='C001',data=None):
        draft,report=self.preview(company,data);status,saved=self.request(self.url('imports/'+draft['import_id']+'/commit',company),commit_fields(report),headers={'Idempotency-Key':secrets.token_hex(16)})
        if status!=200:raise AssertionError((status,saved))
        return saved['snapshot']['snapshot_id']
    def count(self):
        with closing(sqlite3.connect(self.store.path)) as c:return c.execute('SELECT count(*) FROM snapshots').fetchone()[0]


class PortalAuthTests(unittest.TestCase):
    def setUp(self):self.h=PortalHarness().__enter__();self.addCleanup(self.h.__exit__)
    def test_no_session_no_access_and_browser_assertions_ignored(self):
        for head in ({},{'Authorization':'Bearer '+'x'*40,'X-Role':'director','X-Tenant':'demo'}):
            self.assertEqual(self.h.request('/agent2/api/v1/ui/context',token=False,headers=head)[0],401)
    def test_context_has_only_own_companies_and_no_backend_secret(self):
        status,value=self.h.request('/agent2/api/v1/ui/context');self.assertEqual(status,200)
        self.assertEqual(value['companies'],['C001','C002']);self.assertEqual(value['actor_id'],'portal-reviewer');self.assertEqual(len(value['context_id']),64)
        raw=json.dumps(value);self.assertNotIn(self.h.secret,raw);self.assertNotIn(self.h.token,raw);self.assertNotIn('memberships',value)
    def test_profile_edit_does_not_grant_company_membership(self):
        portal.write_json(portal.COMPANY_FILE,dict(code='OTHER',agent2_company='OTHER'))
        self.assertEqual(self.h.request(self.h.url('imports/validate','OTHER'),self.h.data)[0],403)
        self.assertEqual(self.h.request('/agent2/api/v1/ui/context')[1]['companies'],['C001','C002'])
    def test_upload_preview_commit_analyze_using_only_portal_session(self):
        sid=self.h.commit();self.assertEqual(self.h.count(),1)
        status,value=self.h.request(self.h.url('snapshots/'+sid+'/analyze'),dict(as_of='2026-10-30T09:00:00+07:00'))
        self.assertEqual(status,200,value);self.assertEqual(value['row_count'],5);self.assertEqual(len(value['groups']),1);self.assertEqual(value['view'],'review')
        self.assertIn('unavailable',[c['status'] for r in value['rows'] for c in r['checks'].values()])
        self.assertEqual(self.h.request(self.h.url('snapshots/'+sid+'/analyze'),dict(as_of='2026-10-30T09:00:00+07:00',view='technical'))[0],403)
    def test_director_requires_own_company_and_backend_role(self):
        scope=self.h.authorizer.authorize_director('Bearer '+self.h.token,'C002');self.assertEqual(scope.company_ids,frozenset({'C002'}))
        for company in ('C001','OTHER'):
            with self.assertRaises(AuthError):self.h.authorizer.authorize_director('Bearer '+self.h.token,company)
    def test_director_technical_http_only_in_granted_company(self):
        from sme_fraud.p1_inputs import export_manifest
        data=json.loads(json.dumps(self.h.data).replace('C001','C002'))
        for claim in data['payment_history_coverage']:claim['manifest']=export_manifest(data,claim)
        sid=self.h.commit('C002',data)
        status,value=self.h.request(self.h.url('snapshots/'+sid+'/analyze','C002'),dict(as_of='2026-10-30T09:00:00+07:00',view='technical'))
        self.assertEqual(status,200,value);self.assertEqual(value['row_count'],5);self.assertEqual(value['view'],'technical')
        self.assertEqual(self.h.request(self.h.url('snapshots/'+sid+'/analyze'),dict(as_of='2026-10-30T09:00:00+07:00',view='technical'))[0],403)
    def test_revoked_session_blocks_preview_commit_and_snapshot_reads(self):
        sid=self.h.commit();draft,report=self.h.preview();portal.SESSIONS.pop(self.h.token)
        for path,body in [(self.h.url('snapshots/'+sid),None),(self.h.url('imports/'+draft['import_id']+'/preview'),dict(expected_revision=1)),(self.h.url('imports/'+draft['import_id']+'/commit'),commit_fields(report))]:
            self.assertEqual(self.h.request(path,body,headers={'Idempotency-Key':'revoked-commit'})[0],401)
        self.assertEqual(self.h.count(),1)
    def test_logout_during_analysis_returns_no_private_rows(self):
        from sme_fraud.snapshot_analysis import analyze_snapshot
        sid=self.h.commit()
        def revoke(*args,**kwargs):
            result=analyze_snapshot(*args,**kwargs);portal.SESSIONS.pop(self.h.token,None);return result
        with patch('sme_fraud.analysis_api.analyze_snapshot',side_effect=revoke):
            status,value=self.h.request(self.h.url('snapshots/'+sid+'/analyze'),dict(as_of='2026-10-30T09:00:00+07:00'))
        self.assertEqual(status,401);self.assertNotIn('rows',value)
    def test_expired_session_fails_and_get_poll_does_not_extend_ttl(self):
        expiry=portal.SESSIONS[self.h.token];self.assertEqual(self.h.request('/agent2/api/v1/ui/context')[0],200);self.assertEqual(portal.SESSIONS[self.h.token],expiry)
        portal.SESSIONS[self.h.token]=time.time()-1;self.assertEqual(self.h.request('/agent2/api/v1/ui/context')[0],401)
    def test_membership_and_permission_rechecked_without_restart(self):
        draft,report=self.h.preview();self.h.policy['memberships'][0]['permissions']=[];self.h.write_policy()
        self.assertEqual(self.h.request('/agent2/api/v1/ui/context')[1]['companies'],['C002'])
        status,_=self.h.request(self.h.url('imports/'+draft['import_id']+'/commit'),commit_fields(report),headers={'Idempotency-Key':'rights-revoked'});self.assertEqual(status,403);self.assertEqual(self.h.count(),0)
    def test_role_revocation_rechecked_and_context_changes(self):
        first=self.h.request('/agent2/api/v1/ui/context')[1]['context_id'];self.h.policy['memberships'][1]['role']='accountant';self.h.write_policy()
        self.assertNotEqual(first,self.h.request('/agent2/api/v1/ui/context')[1]['context_id'])
        with self.assertRaises(AuthError):self.h.authorizer.authorize_director('Bearer '+self.h.token,'C002')
    def test_missing_invalid_or_revoked_policy_fails_closed(self):
        for content in ('{}','{"version": "bad"}',json.dumps(dict(self.h.policy,status='revoked'))):
            self.h.access.write_text(content,encoding='utf-8');self.assertIn(self.h.request('/agent2/api/v1/ui/context')[0],(403,503))
        self.h.access.unlink();self.assertEqual(self.h.request('/agent2/api/v1/ui/context')[0],503)
    def test_internal_identity_requires_bridge_secret_and_no_browser_origin(self):
        for headers in ({},{'Authorization':'Bearer '+self.h.token},{'Authorization':'Bearer '+self.h.secret,'Origin':self.h.portal_url}):
            self.assertEqual(self.h.request('/api/internal/agent2/identity',dict(session=self.h.token),headers=headers)[0],403)
    def test_proxy_requires_same_origin_host_and_platform_header(self):
        for headers in ({'Host':'evil.example'},{'Origin':'https://evil.example'},{'X-Platform':'0'}):
            self.assertEqual(self.h.request('/agent2/api/v1/ui/context',headers=headers)[0],403)
    def test_proxy_rejects_queries_and_non_allowlisted_routes(self):
        for path in ('/agent2/api/v1/ui/context?role=director','/agent2/assets/../auth.py','/agent2/api/legacy','/agent2/api/v1/ui/context/extra'):
            self.assertEqual(self.h.request(path)[0],404)
    def test_direct_backend_still_validates_portal_and_no_local_fallback(self):
        path='/api/v1/ui/context'
        self.assertEqual(self.h.request(path,agent=True,headers={'Authorization':'Bearer '+self.h.token})[0],200)
        self.assertEqual(self.h.request(path,agent=True,headers={'Authorization':'Bearer '+'x'*40})[0],401)
        self.assertEqual(self.h.request('/api/v1/ui/settings',agent=True)[1],{'auth_mode':'portal','portal_url':self.h.portal_url})
    def test_tenant_change_cannot_read_previous_tenant_snapshot(self):
        sid=self.h.commit();self.h.policy['tenant_id']='another-tenant';self.h.write_policy()
        self.assertEqual(self.h.request(self.h.url('snapshots/'+sid))[0],404)
    def test_actor_change_cannot_read_previous_actor_import(self):
        draft,_=self.h.preview();self.h.policy['actor_id']='another-reviewer';self.h.write_policy()
        self.assertEqual(self.h.request(self.h.url('imports/'+draft['import_id']))[0],404)
    def test_bad_bridge_secret_and_unreachable_portal_fail_closed(self):
        bad=PortalAuthorizer(self.h.portal_url,secrets.token_urlsafe(32))
        with self.assertRaises(AuthError):bad.authorize('Bearer '+self.h.token,'C001')
        bad=PortalAuthorizer('http://127.0.0.1:1',self.h.secret)
        with self.assertRaises(AuthError) as error:bad.authorize('Bearer '+self.h.token,'C001')
        self.assertEqual(error.exception.status,503)
    def test_only_loopback_origin_and_strong_backend_secret_are_accepted(self):
        for url,secret in [('https://example.com',self.h.secret),('http://127.0.0.1:8800/path',self.h.secret),('http://user:pass@localhost:8800',self.h.secret),('http://localhost:8800','short')]:
            with self.assertRaises(ValueError):PortalAuthorizer(url,secret)
    def test_launcher_uses_portal_bridge_and_dedicated_snapshot_db(self):
        cmd,_,env=portal.launch_spec('agent2');self.assertIn('--portal-url',cmd);self.assertIn('--snapshot-db',cmd);self.assertNotIn('--demo-ml-manager',cmd)
        self.assertNotIn(self.h.secret,' '.join(cmd));self.assertEqual(env['AGENT2_PORTAL_BRIDGE_SECRET'],self.h.secret)
    def test_stop_only_targets_the_agent2_process_tree_owned_by_portal(self):
        proc=Mock(pid=12345);proc.poll.return_value=None;portal.PROCS['agent2']=proc
        with patch.object(portal,'agent_state',return_value={'state':'stopped'}),patch.object(portal.subprocess,'run',return_value=Mock(returncode=0)) as terminate:
            self.assertEqual(portal.stop_agent('agent2'),{'state':'stopped'})
            if os.name=='nt':self.assertEqual(terminate.call_args.args[0],['taskkill','/PID','12345','/T','/F'])
            else:proc.terminate.assert_called_once()
        self.assertNotIn('agent2',portal.PROCS)
        with self.assertRaises(ValueError):portal.stop_agent('agent2')


if __name__=='__main__':unittest.main()
