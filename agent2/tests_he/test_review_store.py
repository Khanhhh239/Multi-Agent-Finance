import json
import base64
import tempfile
from pathlib import Path
import unittest
from finance_input import AccessScope
from sme_fraud.import_files import ImportFailure
from sme_fraud.review_store import ReviewStore


class Reviews(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'reviews.sqlite3';self.now=100.
        self.scope=AccessScope('t',frozenset({'C001'}),'reviewer',frozenset({'data.import'}))
        self.key=b'k'*32;self.store=ReviewStore(self.path,self.key,lambda:self.now)
        self.case=self.store.case_id(self.scope,'job','TX',1)
        self.feedback=dict(outcome='inconclusive',usefulness='not_assessed',explanation='Missing original invoice',action='Request original invoice from AP',missing_materials='invoice',evidence_ids=[],checks_completed=False)

    def save(self,lease,revision=0,request='save-request-1',feedback=None):
        return self.store.save(self.scope,self.case,revision,feedback or self.feedback,{'ev1'},lease,request)

    def test_encrypted_persistent_idempotent_revisions(self):
        token=self.store.start(self.scope,self.case)['lease'];self.now+=5
        value=self.save(token);self.assertEqual(value['revision'],1);self.assertEqual(value['active_seconds'],5)
        self.assertEqual(self.save(token),value)
        reopened=ReviewStore(self.path,self.key)
        self.assertEqual(reopened.get(self.scope,self.case),value)
        self.assertNotIn(b'Missing original invoice',self.path.read_bytes())
        token=reopened.start(self.scope,self.case)['lease']
        newer=reopened.save(self.scope,self.case,1,self.feedback,{'ev1'},token,'save-request-2')
        self.assertEqual(len(newer['history']),2)

    def test_timer_excludes_outage_and_restart(self):
        token=self.store.start(self.scope,self.case)['lease'];self.now+=5
        self.store.heartbeat(self.scope,self.case,token);self.now+=100
        self.assertEqual(self.save(token)['active_seconds'],5)
        reopened=ReviewStore(self.path,self.key)
        with self.assertRaises(ImportFailure):reopened.save(self.scope,self.case,1,self.feedback,{'ev1'},token,'save-request-2')

    def test_duplicate_tabs_conflict_and_stale_writes(self):
        token=self.store.start(self.scope,self.case)['lease']
        with self.assertRaises(ImportFailure):self.store.start(self.scope,self.case)
        self.save(token);new=self.store.start(self.scope,self.case)['lease']
        with self.assertRaises(ImportFailure):self.save(new,request='save-request-2')

    def test_evidence_and_outcome_constraints(self):
        token=self.store.start(self.scope,self.case)['lease']
        for change in (dict(evidence_ids=['foreign']),dict(outcome='confirmed_risk',evidence_ids=[]),dict(usefulness='yes',action=''),dict(outcome='legitimate',evidence_ids=['ev1'],checks_completed=False)):
            with self.subTest(change=change),self.assertRaises(ImportFailure):self.save(token,feedback=dict(self.feedback,**change))

    def test_cross_company_and_actor_isolation(self):
        token=self.store.start(self.scope,self.case)['lease'];self.save(token)
        for scope in (AccessScope('t',frozenset({'C002'}),'reviewer',frozenset({'data.import'})),AccessScope('t',frozenset({'C001'}),'other',frozenset({'data.import'}))):
            self.assertEqual(self.store.get(scope,self.case)['revision'],0)

    def test_wrong_key_and_tamper_fail_closed(self):
        with self.assertRaises(Exception):ReviewStore(self.path,b'x'*32)
        token=self.store.start(self.scope,self.case)['lease'];self.save(token)
        with self.store.transaction() as conn:
            conn.execute('DROP TRIGGER reviews_update');conn.execute('UPDATE reviews SET revision=2')
        with self.assertRaises(Exception):self.store.get(self.scope,self.case)

    def test_attachments_are_scoped_sealed_and_never_auto_verified(self):
        content=base64.b64encode(b'%PDF-1.4\nSynthetic document').decode()
        identity=self.store.attach(self.scope,self.case,'invoice.pdf',content)
        self.assertEqual(self.store.attach(self.scope,self.case,'other.pdf',content),identity)
        item=self.store.attachment(self.scope,self.case,identity)
        self.assertFalse(item['original_verified']);self.assertEqual(item['name'],'invoice.pdf')
        self.assertEqual(len(self.store.get(self.scope,self.case)['attachments']),1)
        foreign=AccessScope('t',frozenset({'C002'}),'reviewer',frozenset({'data.import'}))
        with self.assertRaises(ImportFailure):self.store.attachment(foreign,self.case,identity)
        for name,raw in (('../invoice.pdf',content),('bad.pdf',base64.b64encode(b'<script>').decode())):
            with self.assertRaises(ImportFailure):self.store.attach(self.scope,self.case,name,raw)
        token=self.store.start(self.scope,self.case)['lease']
        value=self.save(token,feedback=dict(self.feedback,evidence_ids=[identity]))
        self.assertEqual(value['feedback']['evidence_ids'],[identity])
        self.assertNotIn(b'Synthetic document',self.path.read_bytes())


if __name__=='__main__':unittest.main()
