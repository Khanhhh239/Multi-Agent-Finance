"""Checker fault tests using plain fixture results, not an HE execution claim."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import numpy as np
from experiments.he4.p1_demo import source,scope,save_snapshot,inspect,AS_OF
from experiments.he4.p1_portal_check import reconcile
from experiments.he4.coordinator import FourJobs
from experiments.he4 import circuits
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.review_api import cases_for


class PortalComparison(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);store=SnapshotStore(Path(self.tmp.name)/'s.sqlite3');authority=scope('C001');self.data=source('C001');sid=save_snapshot(store,'C001',self.data)
        self.reference,plan=inspect(store,'C001',sid);tasks=[]
        for row in plan['rows']:
            for name,branch in row['branches'].items():
                branch['task_indexes']=[]
                if name!='rules':branch.update(available=False,status='unavailable',reason='test_branch_not_run',requests=[]);continue
                for request in branch['requests']:
                    branch['task_indexes'].append(len(tasks));tasks.append(dict(result=circuits.p1(*[np.asarray(v,dtype=np.int64) for v in request['values']]).tolist()))
        legacy=dict(company_id='C001',rows=[dict(record_id=t['record_id'],revision=1,available=False,status='unavailable',reason='test_ml_not_run',score=None) for t in self.data['transactions']])
        self.result=FourJobs.assemble('herun_'+'c'*32,dict(snapshot_id=sid,as_of=AS_OF),dict(plan=plan,tasks=tasks),legacy)
        fake=SimpleNamespace(case_id=lambda scope,run,id,rev:'case_'+id,get=lambda scope,id:{})
        self.packet=dict(company_id='C001',run_id=self.result['run_id'],snapshot_id=sid,as_of=AS_OF,cases=cases_for(store,authority,self.result,fake,lambda:authority))

    def check(self):return reconcile('C001',self.data,self.result,self.packet,self.reference)

    def test_exact_manual_and_engine_reconciliation(self):
        report=self.check();self.assertEqual(report['row_count'],8);self.assertTrue(report['all_rows_match']);self.assertFalse(report['human_review_feedback_written'])
        group=next(r['group_check'] for r in report['rows'] if r['record_id']=='P1_T06');self.assertEqual(group['group_allocated_vnd'],8_000_000);self.assertTrue(group['matched'])

    def test_wrong_amount_and_missing_history_false_no_hit_are_rejected(self):
        row=next(r for r in self.result['rows'] if r['record_id']=='P1_T03');row['branches']['rules']['invoice_checks'][0]['cumulative_paid_vnd']+=1
        with self.assertRaises(AssertionError):self.check()
        row['branches']['rules']['invoice_checks'][0]['cumulative_paid_vnd']-=1
        gap=next(r for r in self.result['rows'] if r['record_id']=='P1_T08');gap['branches']['rules']['matched']=False
        with self.assertRaises(AssertionError):self.check()

    def test_missing_peer_evidence_and_claimed_verified_original_are_rejected(self):
        case=next(c for c in self.packet['cases'] if c['record_id']=='P1_T06');case['evidence']=[e for e in case['evidence'] if e['record']['record_id']!='P1_A_P1_T07']
        with self.assertRaises(AssertionError):self.check()
        self.packet['cases'][0]['evidence'][0]['original_verified']=True
        with self.assertRaises(AssertionError):self.check()

    def test_wrong_company_and_run_binding_are_rejected(self):
        self.result['company_id']='C002'
        with self.assertRaises(AssertionError):self.check()
        self.result['company_id']='C001';self.packet['run_id']='herun_'+'d'*32
        with self.assertRaises(AssertionError):self.check()


if __name__=='__main__':unittest.main()
