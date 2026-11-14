"""Offline demo preparation and guarded dynamic model activation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sme_fraud.import_files import canonical
from sme_fraud.method_store import MethodStore
from sme_fraud.ml_estimators import CompanyEstimator
from sme_fraud.rule_bridge_demo import source_data
from sme_fraud.rule_bridge_models import activate, check, prepare
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.unsupervised_statistics import RobustZ


class RuleBridgeModelSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.snapshot_db = cls.root / 'snapshots.sqlite3'; SnapshotStore(cls.snapshot_db)
        cls.model_db = cls.root / 'models.sqlite3'; MethodStore(cls.model_db)
        cls.bindings = cls.root / 'bindings.json'
        cls.old_bindings = canonical(dict(version='analysis-bindings/1.0.0', bindings=[dict(
            tenant_id='other', company_id='C999', statistics_artifact_id=None, ml_artifacts={})]))
        cls.bindings.write_bytes(cls.old_bindings)
        cls.access = cls.root / 'access.json'
        cls.old_policy = canonical(dict(version='portal-agent2-access/1.0.0', actor_id='demo-reader', tenant_id='demo', status='active',
                                       memberships=[dict(company_id=c, role='accountant', status='active', permissions=['data.import']) for c in ('C001','C002')]))
        cls.access.write_bytes(cls.old_policy)
        cls.output = cls.root / 'prepared'
        cls.receipt = prepare(cls.snapshot_db,cls.model_db,cls.bindings,cls.access,cls.output)
        cls.candidate = (cls.output / 'analysis-bindings.candidate.json').read_bytes()

    def setUp(self):
        self.bindings.write_bytes(self.old_bindings)
        self.access.write_bytes(self.old_policy)
        (self.output / 'analysis-bindings.candidate.json').write_bytes(self.candidate)

    def test_held_out_data_and_unmapped_features_are_explicit(self):
        for company in ('C001','C002'):
            train,evaluation=source_data(company)
            ids={r['transaction_id'] for r in train['source']['tables']['transactions']}
            self.assertEqual(len(ids),40)
            self.assertEqual(len(evaluation['candidate_transaction_ids']),5)
            self.assertFalse(ids & set(evaluation['candidate_transaction_ids']))
        for record in self.receipt['companies']:
            for model in record['models'].values():
                self.assertEqual(model['history_rows'],32)
                self.assertEqual(model['reference_rows'],8)
                self.assertEqual(len(model['selected_columns']),33)
                self.assertIn('known_invoice_count',model['dropped_columns'])
        self.assertEqual(self.bindings.read_bytes(),self.old_bindings)

    def test_activation_preserves_foreign_binding_and_permissions_without_refit(self):
        with patch.object(CompanyEstimator,'fit',side_effect=AssertionError('No fit on check/activate')), patch.object(RobustZ,'fit',side_effect=AssertionError('No fit on check/activate')):
            report=activate(self.output)
            again=check(self.output)
            retried=activate(self.output)
        self.assertEqual(report['status'],'passed')
        self.assertEqual(report['companies'],again['companies'])
        self.assertEqual(report['companies'],retried['companies'])
        self.assertTrue(all(r['rows']==r['ml_available']==r['statistics_available']==5 for r in report['companies']))
        self.assertEqual(json.loads(self.bindings.read_bytes())['bindings'][0]['tenant_id'],'other')
        self.assertEqual(self.access.read_bytes(),self.old_policy)

    def test_binding_or_access_change_cannot_be_silently_overwritten(self):
        changed=json.loads(self.old_bindings);changed['bindings']=[];self.bindings.write_bytes(canonical(changed))
        with self.assertRaisesRegex(ValueError,'bindings changed'):activate(self.output)
        self.assertEqual(self.bindings.read_bytes(),canonical(changed))
        self.bindings.write_bytes(self.old_bindings)
        policy=json.loads(self.old_policy);policy['actor_id']='changed-operator';self.access.write_bytes(canonical(policy))
        with self.assertRaisesRegex(ValueError,'access policy changed'):activate(self.output)
        self.assertEqual(self.bindings.read_bytes(),self.old_bindings)

    def test_tampered_candidate_and_missing_grants_are_rejected(self):
        (self.output / 'analysis-bindings.candidate.json').write_bytes(self.old_bindings)
        with self.assertRaisesRegex(ValueError,'Bindings do not match'):activate(self.output)
        self.assertEqual(self.bindings.read_bytes(),self.old_bindings)
        policy=json.loads(self.old_policy);policy['memberships']=policy['memberships'][:1];self.access.write_bytes(canonical(policy))
        with self.assertRaises(ValueError):prepare(self.snapshot_db,self.model_db,self.bindings,self.access,self.root/'denied')
        self.assertFalse((self.root/'denied').exists())
