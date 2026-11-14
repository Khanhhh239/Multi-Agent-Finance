"""Review evidence projection only; simulated scoring data, no HE claim."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from experiments.he4.p1_demo import source,scope,save_snapshot,inspect,AS_OF
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.review_api import cases_for
from sme_fraud.import_files import ImportFailure


class RuleEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=SnapshotStore(Path(self.tmp.name)/'s.sqlite3');self.scope=scope('C001')
        self.source=source('C001');self.sid=save_snapshot(self.store,'C001',self.source);self.ref,self.plan=inspect(self.store,'C001',self.sid)
        refs={r['record_id']:r['branches']['rules'] for r in self.plan['rows']}
        self.result=dict(run_id='herun_'+'a'*32,snapshot_id=self.sid,as_of=AS_OF,rows=[dict(record_id=r['record_id'],revision=1,available=False,reason='artifact_missing',score=None,
            branches=dict(rules=dict(refs[r['record_id']],invoice_checks=r['invoice_checks'],simultaneous_checks=r['simultaneous_checks']))) for r in self.ref['rows']])
        self.reviews=SimpleNamespace(case_id=lambda scope,run,id,rev:'case_'+id,get=lambda scope,id:{})

    def cases(self):return cases_for(self.store,self.scope,self.result,self.reviews,lambda:self.scope)

    def test_concurrent_peer_and_coverage_are_visible_and_not_duplicated(self):
        row=next(r for r in self.cases() if r['record_id']=='P1_T06');keys={(e['table'],e['record']['record_id'],e['record']['revision']) for e in row['evidence']}
        self.assertIn(('transactions','P1_T07',1),keys);self.assertIn(('payment_allocations','P1_A_P1_T07',1),keys)
        self.assertIn(('payment_history_coverage','P1_COV_6',1),keys);self.assertEqual(len(keys),len(row['evidence']))
        self.assertTrue(all(e['simulated'] and not e['original_verified'] for e in row['evidence']))

    def test_missing_or_future_ref_fails_closed(self):
        row=next(r for r in self.result['rows'] if r['record_id']=='P1_T06');original=deepcopy(row['branches']['rules']['evidence_refs'])
        row['branches']['rules']['evidence_refs'].append(dict(table='invoices',record_id='OTHER',revision=1))
        with self.assertRaises(ImportFailure):self.cases()
        row['branches']['rules']['evidence_refs']=original
        row['branches']['rules']['evidence_refs'].append(dict(table='transactions',record_id='P1_T08',revision=1))
        with self.assertRaises(ImportFailure) as error:self.cases()
        self.assertEqual(error.exception.code,'REVIEW_EVIDENCE_TIME')

    def test_later_coverage_cannot_be_added_to_earlier_case(self):
        row=next(r for r in self.result['rows'] if r['record_id']=='P1_T02')
        row['branches']['rules']['evidence_refs'].append(dict(table='payment_history_coverage',record_id='P1_COV_6',revision=1))
        with self.assertRaises(ImportFailure) as error:self.cases()
        self.assertEqual(error.exception.code,'REVIEW_EVIDENCE_TIME')

    def test_adjustment_parent_and_rule_invoice_are_present(self):
        cases={r['record_id']:r for r in self.cases()}
        self.assertIn('P1_T01',[e['record']['record_id'] for e in cases['P1_T04']['evidence'] if e['table']=='transactions'])
        row=cases['P1_T03'];self.assertIn('P1_I_BASE',[e['record']['record_id'] for e in row['evidence'] if e['table']=='invoices'])
        self.assertIn('12000000',row['why']);self.assertIn('10000000',row['why'])

    def test_different_global_ceiling_preserves_past_p1_results(self):
        later,_=inspect(self.store,'C001',self.sid,'2026-11-13T12:00:00+07:00')
        self.assertEqual(later['rows'],self.ref['rows'])


if __name__=='__main__':unittest.main()
