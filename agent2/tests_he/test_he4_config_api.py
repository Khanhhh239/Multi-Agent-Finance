"""Real fit/activation and Portal permissions; circuit files are test metadata.

No HE score or private key provisioning is claimed by these tests.
"""
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from web_support import WebHarness
from experiments.he4.web import FourWorkbench
from experiments.he4.coordinator import FourJobs,Settings
from experiments.he4.config_manager import Manager
from experiments.he_inference.protocol import canonical,sha
from sme_fraud.review_server import make_server
from sme_fraud.import_files import ImportFailure
from portal import server as portal


class ConfigurationAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=WebHarness().__enter__();f=cls.f;root=f.pair.enterprise/'configuration-test';root.mkdir();builds={}
        for profile in ('rules','statistics','graph'):
            p=root/profile;p.mkdir();files={'server.zip':b'test server only','client.specs.json':b'test metadata only'}
            for name,data in files.items():(p/name).write_bytes(data)
            (p/'manifest.json').write_bytes(canonical(dict(version='he4-circuit-build/0.1.0',profile=profile,files={n:sha(v) for n,v in files.items()})));builds[profile]=str(p)
        cls.path=root/'bindings.json';cls.path.write_bytes(canonical(dict(version='he4-company-bindings/1.0.0',bindings=[dict(tenant_id='demo',company_id=c,statistics_artifact_id=None) for c in ('C001','C002')])))
        cfg=dict(version='he4-enterprise/1.0.0',state_dir=str(root/'jobs'),enterprise_root=str(root/'private'),state_key_file=str(f.pair.state_key_path),worker_url='http://127.0.0.1:1',worker_verify_key='a'*64,builds=builds,bindings_file=str(cls.path),linux_distro='Debian',linux_python='/python')
        f.h.agent.shutdown();f.h.agent.server_close()
        with patch('experiments.he4.web.FourJobs',side_effect=lambda node,settings:FourJobs(node,settings,workers=0)):f.backend=FourWorkbench(f.node,f.bindings,cfg)
        f.h.agent=make_server(0,f.h.authorizer,f.h.store,he_backend=f.backend);portal.CFG['agents']['agent2']['port']=f.h.agent.server_port
        thread=threading.Thread(target=f.h.agent.serve_forever,daemon=True);thread.start();f.h.threads.append(thread)

    @classmethod
    def tearDownClass(cls):cls.f.__exit__()

    def request(self,tail='',body=None,company='C002',key='configuration-request-key'):
        return self.f.h.request(self.f.h.url('analysis-config'+tail,company),body,headers={'Idempotency-Key':key})

    def test_01_permissions_fit_and_atomic_activation(self):
        self.assertEqual(self.request(company='C001')[0],403)
        status,initial=self.request();self.assertEqual(status,200,initial);self.assertFalse(initial['can_fit'])
        self.assertEqual(self.request('/fit',dict(expected_revision=0))[0],403)
        # Explicit fixture grant, never an application-side role upgrade.
        member=self.f.h.policy['memberships'][1];member['permissions'].append('model.fit');self.f.h.write_policy()
        cfg=dict(self.f.pair.env['configs']['C002'],version='company-fit-config/1.0.0',method_id='robust_z',profile_id='technical-test')
        status,draft=self.request('/draft',dict(expected_revision=0,config=cfg),key='save-config-draft');self.assertEqual(status,200,draft)
        status,value=self.request('/fit',dict(expected_revision=draft['revision']),key='fit-config-pair');self.assertEqual(status,202,value)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            status,value=self.request()
            if value.get('fit',{}).get('status')!='fitting':break
            time.sleep(.1)
        self.assertEqual(value['fit']['status'],'succeeded',value)
        before=self.path.read_bytes();scope=self.f.h.authorizer.authorize_director('Bearer '+self.f.h.token,'C002')
        pending=self.f.node.jobs.store.create(scope,'pending-model-swap',dict(snapshot_id=self.f.pair.env['queries']['C002'],as_of='2026-11-01T00:00:00+07:00'))
        status,blocked=self.request('/activate',dict(expected_revision=value['revision']),key='activate-config-pair');self.assertEqual(status,409,blocked);self.assertEqual(before,self.path.read_bytes())
        _,data=self.f.node.jobs.store.get(scope,pending);self.f.node.jobs.store.save(scope,pending,data,'failed','TEST_CANCELLED')
        status,active=self.request('/activate',dict(expected_revision=value['revision']),key='activate-config-pair');self.assertEqual(status,200,active)
        self.assertEqual(active['active']['ml_artifact_id'],value['fit']['ml_artifact_id']);self.assertEqual(active['active']['statistics_artifact_id'],value['fit']['statistics_artifact_id'])
        self.assertEqual(self.f.backend.selection(scope),active['active']['ml_artifact_id']);self.assertEqual(active['business_policy']['weights'],None)
        self.assertEqual(self.request('/activate',dict(expected_revision=value['revision']),key='activate-config-pair')[1]['revision'],active['revision'])
        self.assertEqual(self.f.backend.settings.capture(self.f.h.authorizer.authorize('Bearer '+self.f.h.token,'C001'))['binding']['statistics_artifact_id'],None)
        # Fresh settings object after restart reads the active bindings.
        self.assertEqual(Settings(self.f.backend.settings.config).capture(scope)['binding'],active['active'])
        member['permissions'].remove('model.fit');self.f.h.write_policy()
        self.assertEqual(self.request('/draft',dict(expected_revision=active['revision'],config=cfg),key='revoked-config')[0],403)

    def test_02_reader_cannot_claim_manager_or_fit_permissions(self):
        self.assertEqual(self.request(company='C001')[0],403)
        self.assertEqual(self.f.h.request(self.f.h.url('analysis-config','C001'),headers={'X-Role':'director','X-Permissions':'model.fit'})[0],403)
        self.assertEqual(self.request(body={},key='bad-route')[0],405)

    def test_03_comparison_uses_current_four_branch_plan_and_review_store(self):
        from comparison_support import seed_run
        from sme_fraud.selection_comparison import POLICY
        run=seed_run(self.f,'C001','four-current-store-comparison')
        url=self.f.h.url('workspace/runs/'+run+'/comparison','C001')
        status,value=self.f.h.request(url,dict(policy=POLICY,budget=5))
        self.assertEqual(status,200,value);self.assertEqual(value['baseline']['metrics']['selected'],3);self.assertEqual(value['combined']['metrics']['selected'],5)
        self.assertEqual(self.f.h.request(url)[1]['plan_sha256'],value['plan_sha256'])
        self.assertEqual(self.f.h.request(self.f.h.url('workspace/runs/'+run+'/comparison','C002'))[0],404)


if __name__=='__main__':unittest.main()
