"""Per-rule source plans on real R1 replay, without pretending to score rules."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema
from sme_fraud.import_files import canonical, ImportFailure
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.rule_sources import _resolve, source_catalog, REQUIREMENTS
from sme_fraud.rules import RULE_NAMES
from sme_fraud.snapshot_features import build_feature_rows, utc
from sme_fraud.snapshots import SnapshotStore
from test_snapshot_features import bundle, scope, committed, AS_OF

ROOT=Path(__file__).resolve().parents[1]


class RuleSourceTests(unittest.TestCase):
    def setUp(self):self.data=bundle('C001');self.scope=scope()
    def resolve(self,data=None,as_of=AS_OF):
        data=self.data if data is None else data
        frame=build_feature_rows(data,self.scope,as_of)
        private,public=_resolve(data,frame,self.scope)
        return private,public,frame
    def rule(self,public,code,identity='T001'):
        return next(r for r in public[(identity,1)]['rules'] if r['rule_id']==code)

    def test_catalog_covers_every_retained_rule_and_explicit_contract_gaps(self):
        catalog=source_catalog()
        self.assertEqual({r['rule_id'] for r in catalog},set(RULE_NAMES))
        self.assertEqual(len(catalog),35)
        self.assertEqual(set(REQUIREMENTS),set(RULE_NAMES))
        for rule in catalog:
            self.assertTrue(rule['bindings'])
            self.assertEqual(rule['evaluation_status'],'not_evaluated')
        c2=next(r for r in catalog if r['rule_id']=='C2')
        self.assertTrue(any(b['table']=='approval_authorities' and b['contract_missing_fields'] for b in c2['bindings']))
        c1=next(r for r in catalog if r['rule_id']=='C1')
        self.assertTrue(any('created_at' in b['contract_missing_fields'] for b in c1['bindings']))

    def test_real_sources_ready_is_distinct_from_evaluated_or_missing(self):
        private,public,_=self.resolve()
        e3=self.rule(public,'E3');self.assertEqual(e3['source_status'],'ready')
        self.assertFalse(e3['gaps']);self.assertTrue(e3['evidence_refs'])
        self.assertEqual(e3['evaluation_status'],'not_evaluated')
        c2=self.rule(public,'C2');self.assertEqual(c2['source_status'],'unavailable')
        self.assertTrue(any(g['table']=='approval_authorities' for g in c2['gaps']))
        self.assertTrue(all(g['action'] for g in c2['gaps']))
        self.assertEqual(private[('T001',1)]['transactions'][0]['amount_vnd'],6000000)
        self.assertNotIn('approval_authorities',private[('T001',1)])

    def test_late_document_and_future_source_values_cannot_change_past_bindings(self):
        _,before,_=self.resolve()
        changed=copy.deepcopy(self.data)
        late=next(r for r in changed['supporting_documents'] if r['record_id']=='DOC_LATE')
        late['name']='Future secret must not appear'
        # A later global request must preserve each transaction's own cutoff.
        _,after,_=self.resolve(changed,'2026-10-13T00:00:00+07:00')
        for key in before:self.assertEqual(before[key],after[key])
        self.assertNotIn('Future secret',json.dumps(list(before.values())))

    def test_history_excludes_self_and_simultaneous_rows_on_both_clocks(self):
        private,_,_=self.resolve()
        for identity in ('T001','T002'):
            history=private[(identity,1)]['transaction_history']
            self.assertEqual([r['record_id'] for r in history],['H0'])
        changed=copy.deepcopy(self.data)
        t=next(r for r in changed['transactions'] if r['record_id']=='H0')
        t['observed_at']='2026-10-10T09:00:00+07:00'
        private,public,_=self.resolve(changed)
        self.assertFalse(private[('T001',1)]['transaction_history'])
        self.assertTrue(any(g['code']=='p1_history_scope_missing' for g in self.rule(public,'P1')['gaps']))

    def test_late_revision_is_filtered_before_choosing_latest_master(self):
        private,before,_=self.resolve()
        original=next(v for v in self.data['vendors'] if v['record_id']=='V001')
        revision=copy.deepcopy(original);revision.update(revision=99,name='Future vendor',observed_at='2026-10-12T12:00:00+07:00')
        changed=copy.deepcopy(self.data);changed['vendors'].append(revision)
        later,after,_=self.resolve(changed)
        self.assertEqual(private,later);self.assertEqual(before,after)

    def test_current_master_revision_can_change_only_when_both_clocks_allow_it(self):
        changed=copy.deepcopy(self.data)
        original=next(v for v in changed['vendors'] if v['record_id']=='V001')
        revision=copy.deepcopy(original);revision.update(revision=99,name='Known revised name',
            observed_at='2026-10-10T08:30:00+07:00',effective_at='2026-10-10T08:30:00+07:00')
        changed['vendors'].append(revision)
        private,public,_=self.resolve(changed)
        self.assertEqual(private[('T001',1)]['vendor'][0]['revision'],99)
        self.assertTrue(any(r['revision']==99 for r in self.rule(public,'E3')['evidence_refs']))

    def test_signed_adjustments_are_retained_without_legacy_placeholders(self):
        private,_,_=self.resolve(as_of='2026-10-13T00:00:00+07:00')
        source=private[('ADJ001',1)]['transactions'][0]
        self.assertEqual(source['amount_vnd'],-2000000)
        self.assertEqual(source['adjusts_ref']['record_id'],'T001')
        self.assertNotIn('approval_limit_vnd',source)
        self.assertNotIn('private_unobserved_creator',json.dumps(private[('ADJ001',1)]))

    def test_missing_invoice_revision_is_gap_not_zero_or_future_invoice(self):
        changed=copy.deepcopy(self.data)
        allocation=next(a for a in changed['payment_allocations'] if a['transaction_ref']['record_id']=='T001')
        old=next(i for i in changed['invoices'] if i['record_id']==allocation['invoice_ref']['record_id'])
        future=copy.deepcopy(old);future.update(revision=99,observed_at='2026-10-12T12:00:00+07:00',amount_vnd=999999999)
        changed['invoices'].append(future);allocation['invoice_ref']['revision']=99
        private,public,_=self.resolve(changed)
        self.assertFalse(private[('T001',1)]['invoices'])
        p1=self.rule(public,'P1')
        self.assertEqual(p1['source_status'],'unavailable')
        self.assertTrue(any(g['field']=='invoice_ref' and g['code']=='referenced_revision_unavailable' for g in p1['gaps']))
        self.assertNotIn('999999999',json.dumps(private[('T001',1)]))
        self.assertNotIn('2026-10-12',json.dumps(public[('T001',1)]))

    def test_documents_preserve_simulation_and_verification_provenance(self):
        private,_,_=self.resolve()
        docs=private[('T001',1)]['supporting_documents']
        self.assertTrue(docs)
        self.assertNotIn('DOC_LATE',[d['record_id'] for d in docs])
        lookup={(d['record_id'],d['revision']):d for d in self.data['supporting_documents']}
        for doc in docs:self.assertEqual(doc,lookup[(doc['record_id'],doc['revision'])])

    def test_company_isolation_and_permission_guards(self):
        one,_,_=self.resolve()
        two=bundle('C002');frame=build_feature_rows(two,scope('C002'),AS_OF)
        private,_=_resolve(two,frame,scope('C002'))
        self.assertNotEqual(one[('T001',1)]['transactions'][0],private[('T001',1)]['transactions'][0])
        for sources in private.values():
            for records in sources.values():self.assertTrue(all(r['company_id']=='C002' for r in records))
        with self.assertRaises(ImportFailure):_resolve(two,frame,self.scope)
        with self.assertRaises(ImportFailure):_resolve(bundle(),frame,scope('C002'))

    def test_bad_cutoff_or_foreign_frame_is_rejected(self):
        _,_,frame=self.resolve();changed=copy.deepcopy(frame)
        changed['rows'][0]['as_of']='2026-10-11T00:00:00+07:00'
        with self.assertRaises(ValueError):_resolve(self.data,changed,self.scope)
        changed=copy.deepcopy(frame);changed['rows'][0]['tenant_id']='foreign'
        with self.assertRaises(ImportFailure):_resolve(self.data,changed,self.scope)

    def test_immutable_source_and_payload_separation(self):
        before=canonical(self.data);private,public,_=self.resolve()
        self.assertEqual(canonical(self.data),before)
        public_data=json.dumps(list(public.values()),ensure_ascii=False)
        self.assertNotIn('content_sha256',public_data)
        self.assertNotIn('signed_amount_vnd',public_data)
        for inputs in public.values():
            for rule in inputs['rules']:self.assertNotIn('sources',rule)
        private[('T001',1)]['transactions'][0]['amount_vnd']=1
        self.assertEqual(canonical(self.data),before)

    def test_snapshot_pipeline_has_one_diagnostic_per_rule_and_never_scores_from_readiness(self):
        schema=json.loads((ROOT/'sme_fraud/method_scores.schema.json').read_text('utf-8'))
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshots.sqlite3');identity=committed(store)
            with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('Inference fit')):
                result=score_snapshot(store,self.scope,identity,AS_OF,methods=('ecod',))
        jsonschema.validate(result,schema);self.assertEqual(result['row_count'],3)
        for row in result['rows']:
            rule=row['methods']['rules'];self.assertFalse(rule['available']);self.assertIsNone(rule['score'])
            inputs=rule['details']['rule_inputs']
            self.assertEqual({r['rule_id'] for r in inputs['rules']},set(RULE_NAMES))
            self.assertEqual(inputs['evaluation_status'],'not_evaluated')
            self.assertEqual(next(r for r in inputs['rules'] if r['rule_id']=='E1')['source_status'],'not_applicable')
            for plan in inputs['rules']:
                for ref in plan['evidence_refs']:
                    self.assertLessEqual(utc(ref['observed_at']),utc(row['as_of']))
                    self.assertLessEqual(utc(ref['effective_at']),utc(row['event_at']))


if __name__=='__main__':unittest.main()
