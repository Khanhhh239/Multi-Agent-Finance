from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from finance_input import AccessScope
from experiments.he_inference.node_job_store import JobStore
from experiments.he_inference.key_manager import create_key
from sme_fraud.he_workbench import saved_runs


class SavedRuns(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name);key=root/'key.json';create_key(key)
        self.current=JobStore(root/'four',key);self.old=JobStore(root/'old',key);self.addCleanup(self.current.close);self.addCleanup(self.old.close)
        self.jobs=SimpleNamespace(store=self.current,legacy=SimpleNamespace(store=self.old));self.scope=AccessScope('tenant',frozenset({'C001'}),'reader',frozenset({'data.import'}))
        self.request=dict(snapshot_id='snp_'+'a'*32,as_of='2026-11-01T00:00:00+07:00')
    def test_hides_child_even_if_parent_died_before_link_checkpoint(self):
        parent=self.current.create(self.scope,'outer-request-key',self.request)
        child=self.old.create(self.scope,'four:'+parent,self.request)
        standalone=self.old.create(self.scope,'standalone-request',self.request)
        self.assertEqual({r['job_id'] for r in saved_runs(self.jobs,self.scope)['runs']},{parent,standalone})
        self.assertEqual(saved_runs(SimpleNamespace(store=self.old),self.scope)['runs'][0]['analysis_mode'],'mahalanobis')
    def test_scope_and_actor_separate_history(self):
        job=self.current.create(self.scope,'own-history-key',self.request)
        for company,actor in [('C002','reader'),('C001','other')]:
            other=AccessScope('tenant',frozenset({company}),actor,self.scope.permissions)
            self.current.create(other,'foreign-history',self.request)
            self.assertNotIn(job,[r['job_id'] for r in saved_runs(self.jobs,other)['runs']])
        self.assertEqual([r['job_id'] for r in saved_runs(self.jobs,self.scope)['runs']],[job])
