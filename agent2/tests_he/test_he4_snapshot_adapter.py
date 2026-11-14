from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_p1_evaluation import payments,DAY,evaluate
from test_snapshot_features import scope
from experiments.he_inference.registry_demo import setup_demo,commit
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.import_files import canonical,ImportFailure
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.unsupervised_statistics import RobustZ
from experiments.he4.snapshot_adapter import prepare_snapshot
from experiments.he4.inputs import decode_payment
from experiments.he4 import circuits


class Sources(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=SnapshotStore(Path(self.tmp.name)/'snapshot.sqlite3');self.scope=scope()

    def plan(self,data):
        sid=commit(self.store,self.scope,data,'he4-source-'+str(len(data['transactions'])))
        return prepare_snapshot(self.store,self.scope,sid,DAY(30))

    def test_p1_raw_plan_matches_retained_engine_and_keeps_all_rows(self):
        data=payments([('OLD',6_000_000,DAY(1)),('A',4_000_000,DAY(2)),('B',4_000_000,DAY(2))])
        plan=self.plan(data);self.assertEqual(len(plan['rows']),3)
        for row in plan['rows']:
            branch=row['branches']['rules'];self.assertTrue(branch['available'],branch)
            clear=evaluate(data,row['record_id'])
            outputs=[(request['role'],decode_payment(circuits.p1(*[np.array(v,dtype=np.int64) for v in request['values']]))) for request in branch['requests']]
            hits=[out['matched'] for role,out in outputs if role=='row']
            self.assertEqual(any(hits),clear['matched'])
            self.assertEqual([out['matched'] for role,out in outputs if role=='simultaneous_group'],[g['matched'] for g in clear['details']['simultaneous_checks']])
            self.assertEqual(row['branches']['statistics']['reason'],'artifact_not_pinned')

    def test_missing_history_is_unavailable_not_zero(self):
        data=payments([('A',12_000_000,DAY(2))]);data['payment_history_coverage']=[]
        branch=self.plan(data)['rows'][0]['branches']['rules']
        self.assertFalse(branch['available']);self.assertEqual(branch['requests'],[])
        self.assertEqual(branch['reason'],'rule_sources_unavailable')

    def test_late_source_does_not_change_past_plan_inputs(self):
        data=payments([('OLD',6_000_000,DAY(1)),('A',6_000_000,DAY(2))])
        first=self.plan(data)
        vendor=deepcopy(data['vendors'][0]);vendor.update(record_id='LATE',observed_at=DAY(29),effective_at=DAY(1));vendor['source']['record_id']='LATE';data['vendors'].append(vendor)
        # Separate DB/idempotency scope, keeping exactly the same source period.
        other=SnapshotStore(Path(self.tmp.name)/'other.sqlite3');sid=commit(other,self.scope,data,'late-source-input')
        later=prepare_snapshot(other,self.scope,sid,DAY(30))
        self.assertEqual([r['branches'] for r in first['rows']],[r['branches'] for r in later['rows']])

    def test_foreign_company_snapshot_denied_and_revocation_rechecked(self):
        data=payments([('A',1_000_000,DAY(2))]);sid=commit(self.store,self.scope,data,'source-access-test')
        with self.assertRaises(ImportFailure):prepare_snapshot(self.store,scope('C002'),sid,DAY(30))
        with self.assertRaises(ImportFailure):prepare_snapshot(self.store,self.scope,sid,DAY(30),recheck=lambda:scope('C002'))


class StatisticsModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.env=setup_demo(cls.tmp.name);cls.pins={}
        for company,old in cls.env['configs'].items():
            cfg=dict(old,version='company-fit-config/1.0.0',method_id='robust_z',profile_id='he4-statistics-test')
            fit=run_fit_job(cls.env['snapshots'],MethodStore(cls.env['model_db']),cls.env['auth'],cls.env['fit_header'],company,cfg,'fit-he4-stat-'+company)
            if fit.get('error'):raise AssertionError(fit)
            cls.pins[company]=fit['job']['artifact_id']

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def plan(self,company,pin=None):
        e=self.env;s=e['auth'].authorize(e['header'],company)
        return prepare_snapshot(e['snapshots'],s,e['queries'][company],'2026-10-20T00:00:00+07:00',model_db=e['model_db'],statistics_artifact=pin or self.pins[company])

    def test_two_company_models_are_separate_and_scoring_never_fits_or_scores_clear(self):
        self.assertNotEqual(self.pins['C001'],self.pins['C002'])
        with patch.object(RobustZ,'fit',side_effect=AssertionError('no fit')),patch.object(RobustZ,'score',side_effect=AssertionError('no plaintext branch score')):
            for company in ('C001','C002'):
                plan=self.plan(company);self.assertEqual(len(plan['rows']),5)
                for row in plan['rows']:
                    b=row['branches']['statistics'];self.assertTrue(b['available'],b);self.assertEqual(b['artifact_id'],self.pins[company])

    def test_other_company_model_is_not_deserialized(self):
        with patch('experiments.he4.snapshot_adapter.joblib.load',side_effect=AssertionError('foreign model')):
            plan=self.plan('C001',self.pins['C002'])
        self.assertTrue(all(not row['branches']['statistics']['available'] for row in plan['rows']))


if __name__=='__main__':unittest.main()
