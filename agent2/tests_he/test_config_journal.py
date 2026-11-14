import tempfile
from pathlib import Path
import unittest
from finance_input import AccessScope
from experiments.he4.config_manager import Journal
from sme_fraud.import_files import ImportFailure


class ConfigJournal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'config.sqlite3'
        self.scope=AccessScope('t',frozenset({'C001'}),'manager',frozenset({'data.import','model.fit'}));self.key=b'k'*32;self.store=Journal(self.path,self.key)
    def test_revisions_idempotency_persistence_and_no_clear_configuration(self):
        first=self.store.save(self.scope,0,'config-save-1',dict(draft={'source':'private source marker'},fit=None),'draft')
        self.assertEqual(self.store.save(self.scope,0,'config-save-1',dict(draft={'source':'private source marker'},fit=None),'draft'),first)
        later=self.store.save(self.scope,1,'config-save-2',dict(fit={'status':'succeeded'}),'fit_finished')
        self.assertEqual(Journal(self.path,self.key).get(self.scope),later);self.assertEqual(len(later['history']),2)
        self.assertNotIn(b'private source marker',self.path.read_bytes())
        with self.assertRaises(ImportFailure):self.store.save(self.scope,1,'stale-request',dict(draft={}), 'draft')
        with self.assertRaises(ImportFailure):self.store.save(self.scope,0,'config-save-1',dict(draft={'changed':1}),'draft')
    def test_foreign_company_and_wrong_key(self):
        self.store.save(self.scope,0,'first-request',dict(draft={'id':1}),'draft')
        other=AccessScope('t',frozenset({'C002'}),'manager',self.scope.permissions)
        self.assertEqual(self.store.get(other)['revision'],0)
        with self.assertRaises(Exception):Journal(self.path,b'x'*32).get(self.scope)
    def test_receipt_binds_original_intent(self):
        change=dict(activation=dict(status='requested',fit_id='fit1'))
        first=self.store.save(self.scope,0,'activate-one',change,'activation_requested')
        self.assertEqual(self.store.receipt(self.scope,'activate-one',0,change,'activation_requested'),first)
        with self.assertRaises(ImportFailure):self.store.receipt(self.scope,'activate-one',1,change,'activation_requested')
