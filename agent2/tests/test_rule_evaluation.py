"""Evaluated hit/no-hit versus unavailable, using source-bound canonical data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema
from sme_fraud.import_files import canonical, ImportFailure
from sme_fraud.rule_sources import _resolve
from sme_fraud.rule_evaluation import _evaluate
from sme_fraud.snapshot_features import build_feature_rows
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.rules import RULE_NAMES,DEFAULT_CONFIG,score_rules
from sme_fraud.rule_audit_cases import Case
from test_snapshot_features import bundle,scope,committed,AS_OF

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'sme_fraud/rule_results.schema.json').read_text('utf-8'))


class RuleEvaluationTests(unittest.TestCase):
    def setUp(self):self.data=bundle('C001');self.scope=scope()
    def add_vendor(self,identity='V002',name='North Harbour Equipment'):
        current=self.data['vendors'][0];current['name']='North Harbor Equipment'
        other=copy.deepcopy(current);other.update(record_id=identity,name=name)
        other['source']['record_id']=identity;self.data['vendors'].append(other)
        return other
    def context(self):
        frame=build_feature_rows(self.data,self.scope,AS_OF);private,public=_resolve(self.data,frame,self.scope)
        meta=next(r for r in frame['rows'] if r['record_id']=='T001');key=('T001',1)
        return private[key],public[key],meta
    def evaluate(self):
        source,inputs,meta=self.context();result=_evaluate(source,inputs,self.scope,meta)
        jsonschema.validate(result,SCHEMA)
        self.assertEqual({r['rule_id'] for r in result['rules']},set(RULE_NAMES))
        self.assertEqual(sum(result['summary'].values()),35)
        return result
    def rule(self,result,code='E3'):return next(r for r in result['rules'] if r['rule_id']==code)

    def test_hit_has_evidence_and_intrinsic_points_without_inflating_master_risk(self):
        self.add_vendor();result=self.evaluate();rule=self.rule(result)
        self.assertEqual(rule['status'],'evaluated_hit');self.assertTrue(rule['available']);self.assertTrue(rule['matched'])
        self.assertEqual(rule['intrinsic_points'],3);self.assertEqual(rule['score'],0);self.assertIsNone(rule['reason'])
        self.assertTrue(rule['evidence_refs']);self.assertEqual(rule['details']['evidence']['matched_vendor_count'],1)
        self.assertEqual(rule['details']['evidence']['top_matches'][0][1],'V002')
        self.assertFalse(result['aggregate']['available']);self.assertIsNone(result['aggregate']['score'])

    def test_no_hit_is_explicit_and_is_not_a_claim_of_validity(self):
        self.add_vendor(name='Orchid Marine Instruments');rule=self.rule(self.evaluate())
        self.assertEqual(rule['status'],'evaluated_no_hit');self.assertTrue(rule['available']);self.assertFalse(rule['matched'])
        self.assertEqual(rule['score'],0);self.assertEqual(rule['intrinsic_points'],0);self.assertIsNone(rule['reason'])
        self.assertTrue(rule['evidence_refs']);self.assertEqual(rule['details']['evidence']['top_matches'],[])
        self.assertIn('không xác nhận',rule['details']['score_reason'])

    def test_missing_sources_are_null_not_no_hit_and_have_specific_gaps(self):
        result=self.evaluate();rule=self.rule(result,'C2')
        self.assertEqual(rule['status'],'unavailable');self.assertFalse(rule['available'])
        self.assertIsNone(rule['matched']);self.assertIsNone(rule['score']);self.assertIsNone(rule['intrinsic_points'])
        self.assertEqual(rule['reason']['code'],'rule_sources_unavailable')
        self.assertTrue(any(g['table']=='approval_authorities' for g in rule['gaps']))
        self.assertTrue(all(g['action'] for g in rule['gaps']))

    def test_uninformative_name_is_unavailable_even_if_field_exists(self):
        self.add_vendor(name='12345');rule=self.rule(self.evaluate())
        self.assertEqual(rule['source_status'],'ready');self.assertEqual(rule['status'],'unavailable')
        self.assertEqual(rule['reason']['code'],'name_content_insufficient')
        self.assertIsNone(rule['matched']);self.assertIsNone(rule['score'])
        self.assertEqual(rule['details']['insufficient_vendor_ids'],['V002'])

    def test_not_applicable_is_not_a_no_hit(self):
        rule=self.rule(self.evaluate(),'E2')
        self.assertEqual(rule['status'],'not_applicable');self.assertFalse(rule['available'])
        self.assertIsNone(rule['score']);self.assertIsNone(rule['matched'])
        self.assertEqual(rule['reason']['code'],'rule_not_applicable')

    def test_future_vendor_and_revisions_never_change_past_result(self):
        self.add_vendor();before=self.evaluate()
        future=copy.deepcopy(self.data['vendors'][0]);future.update(record_id='V_FUT',name='North Harbor Equipment',observed_at='2026-10-12T00:00:00+07:00')
        future['source']['record_id']='V_FUT';self.data['vendors'].append(future)
        revision=copy.deepcopy(self.data['vendors'][1]);revision.update(revision=99,name='Unrelated future name',observed_at='2026-10-12T00:00:00+07:00')
        self.data['vendors'].append(revision)
        self.assertEqual(self.evaluate(),before)

    def test_unrelated_invoice_gap_does_not_disable_vendor_name_rule(self):
        self.add_vendor()
        future=copy.deepcopy(self.data['vendors'][0]);future.update(revision=99,observed_at='2026-10-12T00:00:00+07:00')
        self.data['vendors'].append(future)
        self.data['invoices'][0]['vendor_ref']['revision']=99
        result=self.evaluate();self.assertEqual(self.rule(result)['status'],'evaluated_hit')
        self.assertEqual(self.rule(result,'P1')['status'],'unavailable')
        self.assertTrue(any(g['field']=='vendor_ref' for g in self.rule(result,'P1')['gaps']))

    def test_scope_cutoff_checksum_and_evidence_tampering_are_rejected(self):
        self.add_vendor();sources,inputs,meta=self.context()
        foreign=copy.deepcopy(sources);foreign['vendors'][0]['company_id']='C002'
        with self.assertRaises(ImportFailure):_evaluate(foreign,inputs,self.scope,meta)
        with self.assertRaises(ImportFailure):_evaluate(sources,inputs,scope('C002'),meta)
        future=copy.deepcopy(sources);future['vendors'][0]['observed_at']='2026-10-12T00:00:00+07:00'
        with self.assertRaises(ValueError):_evaluate(future,inputs,self.scope,meta)
        changed=copy.deepcopy(sources);changed['vendor'][0]['name']='Forged name'
        with self.assertRaises(ValueError):_evaluate(changed,inputs,self.scope,meta)
        missing=copy.deepcopy(inputs);self.rule(missing)['evidence_refs']=[]
        with self.assertRaises(ValueError):_evaluate(sources,missing,self.scope,meta)

    def test_e3_matches_native_engine_hit_evidence_and_scoring_policy(self):
        case=Case();peers=[v for v in case.tables['vendors'] if v['company_id']=='C001' and v is not case.vendor]
        for i,v in enumerate(peers):v['name']=f'Công ty mô phỏng đối tác {i+1}'
        case.vendor['name']='North Harbor Equipment';peer=peers[0]
        peer.update(name='North Harbour Equipment',recorded_at=case.vendor['recorded_at'])
        case.pay();case.score()  # Prepare accounting/features; Case uses a pinned legacy audit profile.
        native=score_rules(case.tables,features=case.features)  # Compare the current default policy.
        expected=next(h for h in native['hits'] if h['rule_id']=='E3')
        self.add_vendor(identity=peer['vendor_id']);actual=self.rule(self.evaluate())
        # JSON output uses arrays for the native tuple pairs.
        self.assertEqual(actual['details']['evidence'],json.loads(json.dumps(expected['evidence'])))
        self.assertEqual(actual['score'],expected['points'])
        self.assertEqual(actual['intrinsic_points'],expected['intrinsic_points'])
        self.assertTrue(actual['matched']);self.assertEqual(expected['scoring_role'],'master_quality')

    def test_threshold_is_strict_on_raw_similarity_before_rounding(self):
        self.add_vendor(name='ABCDEFGHIJKLMNOPQXYZ');self.data['vendors'][0]['name']='ABCDEFGHIJKLMNOPQRST'
        rule=self.rule(self.evaluate())
        self.assertEqual(DEFAULT_CONFIG['fuzzy_similarity'],.85)
        self.assertEqual(rule['status'],'evaluated_no_hit')

    def test_snapshot_integration_preserves_every_result_and_never_fits(self):
        self.add_vendor();before=canonical(self.data)
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshot.sqlite3');identity=committed(store,data=self.data)
            with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('Inference fit')) as fit:
                output=score_snapshot(store,self.scope,identity,AS_OF,methods=('ecod',))
            fit.assert_not_called();self.assertEqual(output['row_count'],3)
            for row in output['rows']:
                rules=row['methods']['rules'];self.assertFalse(rules['available']);self.assertIsNone(rules['score'])
                result=rules['details']['rule_results'];jsonschema.validate(result,SCHEMA)
                self.assertEqual(len(result['rules']),35)
                self.assertEqual(self.rule(result)['status'],'evaluated_hit')
                self.assertEqual(row['methods']['ecod']['reason']['code'],'artifact_missing')
        self.assertEqual(canonical(self.data),before)

    def test_schema_rejects_zero_and_false_on_unavailable_result(self):
        result=self.evaluate();rule=self.rule(result,'C2');rule.update(score=0,matched=False)
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(result,SCHEMA)


if __name__=='__main__':unittest.main()
