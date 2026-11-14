"""Explicit channel, exact references and declared/export-bound history scope."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from finance_input import schema
from finance_input.validation import StrictValidator
from sme_fraud.imports import validate_input
from sme_fraud.import_files import canonical,ImportFailure
from sme_fraud.p1_inputs import export_manifest,transaction_inputs
from sme_fraud.snapshot_features import build_feature_rows,build_from_snapshot,feature_contract
from sme_fraud.rule_sources import _resolve
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshot_features import bundle,scope,AS_OF
from test_snapshots import commit_fields


def p1_bundle(company='C001'):
    data=bundle(company);data['contract_version']='1.1.0'
    for row in data['transactions']:row['payment_channel']='bank'
    template=copy.deepcopy(data['companies'][0])
    claim={k:template[k] for k in ('tenant_id','company_id','revision','source')}
    claim.update(record_id='COVERAGE_1',effective_at='2026-09-01T00:00:00+07:00',
        observed_at='2026-10-10T09:00:00+07:00',invoice_refs=[dict(record_id='I001',revision=1)],
        covered_from='2026-09-01T00:00:00+07:00',covered_through='2026-10-10T09:00:00+07:00',
        history_basis='since_inception',coverage_status='complete',export_id='EXPORT_1')
    claim['source']['record_id']='COVERAGE_1'
    data['payment_history_coverage']=[claim]
    claim['manifest']=export_manifest(data,claim)
    return data


class P1InputTests(unittest.TestCase):
    def setUp(self):self.data=p1_bundle();self.scope=scope()
    def report(self):return validate_input(self.data,self.scope)
    def tx(self,identity='T001'):return next(r for r in self.data['transactions'] if r['record_id']==identity)
    def state(self):return transaction_inputs(self.data,self.tx())[1]
    def errors(self):return {e['code'] for e in self.report()['errors']}
    def rebind(self):
        for claim in self.data['payment_history_coverage']:claim['manifest']=export_manifest(self.data,claim)

    def test_both_schemas_validate_and_legacy_channel_is_not_auto_added(self):
        for version in ('1.0.0','1.1.0'):StrictValidator.check_schema(schema(version))
        old=bundle('C001');before=canonical(old);report=validate_input(old,self.scope)
        self.assertFalse(report['errors']);self.assertEqual(report['contract_version'],'1.0.0')
        self.assertFalse(report['capabilities']['C001']['p1_input']['available'])
        self.assertEqual(canonical(old),before)
        old['transactions'][0]['payment_channel']='bank'
        self.assertTrue(validate_input(old,self.scope)['errors'])

    def test_valid_claim_preserves_all_rows_and_is_only_source_declared_ready(self):
        before=canonical(self.data);report=self.report();self.assertFalse(report['errors'])
        self.assertEqual(report['contract_version'],'1.1.0')
        self.assertEqual(report['counts']['transactions'],6)
        self.assertTrue(self.state()['available'])
        self.assertIn('not_verified_external_books',self.state()['history_basis'])
        self.assertEqual(canonical(self.data),before)

    def test_channel_is_never_inferred_from_bank_code_or_accounting_lines(self):
        for channel in (None,'unknown','other'):
            with self.subTest(channel=channel):
                self.tx()['payment_channel']=channel;self.rebind()
                self.assertFalse(self.report()['errors'])
                self.assertFalse(self.state()['available'])
                self.assertTrue(any(g['field']=='payment_channel' for g in self.state()['gaps']))
        self.tx()['payment_channel']='112';self.assertIn('SCHEMA',self.errors())

    def test_missing_scope_and_partial_or_bounded_scope_do_not_become_zero(self):
        self.data['payment_history_coverage']=[]
        self.assertTrue(any(g['code']=='p1_history_scope_missing' for g in self.state()['gaps']))
        self.data=p1_bundle()
        for status,basis in (('partial','since_inception'),('unknown','unknown'),('complete','bounded_period')):
            with self.subTest(status=status,basis=basis):
                c=self.data['payment_history_coverage'][0];c.update(coverage_status=status,history_basis=basis);self.rebind()
                self.assertFalse(self.report()['errors']);self.assertFalse(self.state()['available'])
                self.assertNotIn('prior_paid_vnd',self.state())

    def test_manifest_missing_extra_duplicate_refs_and_counts_are_rejected(self):
        original=copy.deepcopy(self.data)
        for change,code in (
            (lambda m:m['allocation_refs'].pop(),'P1_MANIFEST_MEMBERSHIP'),
            (lambda m:m['allocation_refs'].append(copy.deepcopy(m['allocation_refs'][0])),'P1_DUPLICATE_MANIFEST_REF'),
            (lambda m:m['record_counts'].update(payment_allocations=0),'P1_MANIFEST_COUNT'),
            (lambda m:m.update(records_sha256='0'*64),'P1_MANIFEST_CHECKSUM')):
            self.data=copy.deepcopy(original);change(self.data['payment_history_coverage'][0]['manifest'])
            self.assertIn(code,self.errors())
        self.data=copy.deepcopy(original)
        self.data['payment_history_coverage'][0]['manifest']['transaction_refs'].append(dict(record_id='NEXT01',revision=1))
        self.assertIn('P1_COVERAGE_REFERENCE_TIME',self.errors())

    def test_changed_data_cannot_reuse_old_manifest(self):
        self.tx()['amount_vnd']+=1
        self.assertIn('P1_MANIFEST_CHECKSUM',self.errors())
        self.assertFalse(self.state()['available'])

    def test_scope_time_and_references_must_be_explicit_and_consistent(self):
        original=copy.deepcopy(self.data)
        for field,value in (('covered_from','2026-10-11T00:00:00+07:00'),('covered_through','2026-10-11T00:00:00+07:00')):
            self.data=copy.deepcopy(original);self.data['payment_history_coverage'][0][field]=value
            self.assertIn('P1_COVERAGE_TIME',self.errors())
        self.data=copy.deepcopy(original);self.data['payment_history_coverage'][0]['invoice_refs'][0]['revision']=99
        self.assertIn('REFERENCE_MISSING',self.errors())
        self.data=copy.deepcopy(original);self.data['payment_history_coverage'][0]['covered_from']='2026-10-10T00:00:00+07:00'
        self.assertIn('P1_COVERAGE_RANGE',self.errors())

    def test_negative_allocation_is_retained_and_overpayment_is_not_an_import_error(self):
        original=copy.deepcopy(self.data['payment_allocations'][0])
        original.update(record_id='A_CORRECTION',amount_vnd=-2000000,kind='adjustment',
            adjustment_reason='Correction from source',adjusts_ref=dict(record_id='A_H0',revision=1),
            effective_at='2026-10-10T08:00:00+07:00',observed_at='2026-10-10T08:00:00+07:00')
        self.data['payment_allocations'].append(original);self.rebind()
        self.assertFalse(self.report()['errors'])
        payload,state=transaction_inputs(self.data,self.tx())
        self.assertTrue(state['available'])
        self.assertTrue(any(a['amount_vnd']==-2000000 for a in payload['p1_allocations']))
        self.data['invoices'][0]['amount_vnd']=1;self.rebind()
        self.assertFalse(self.report()['errors'])

    def test_newer_partial_claim_does_not_resurrect_older_complete_claim(self):
        c=self.data['payment_history_coverage'][0]
        earlier=copy.deepcopy(c);earlier.update(revision=1,observed_at='2026-10-10T08:30:00+07:00',covered_through='2026-10-10T08:30:00+07:00')
        earlier['manifest']=export_manifest(self.data,earlier)
        c.update(revision=2,coverage_status='partial');self.data['payment_history_coverage'].insert(0,earlier)
        self.assertFalse(self.report()['errors']);self.assertFalse(self.state()['available'])
        self.assertEqual(self.state()['selected_scope_refs'][0]['revision'],2)

    def test_conflicting_same_time_claims_are_unavailable(self):
        other=copy.deepcopy(self.data['payment_history_coverage'][0]);other.update(record_id='COVERAGE_2',coverage_status='unknown')
        self.data['payment_history_coverage'].append(other)
        self.assertFalse(self.report()['errors'])
        self.assertTrue(any(g['code']=='p1_history_scope_conflict' for g in self.state()['gaps']))

    def test_late_claim_and_late_revision_do_not_rewrite_old_inputs(self):
        before=transaction_inputs(self.data,self.tx())
        other=copy.deepcopy(self.data['payment_history_coverage'][0]);other.update(revision=2,observed_at='2026-10-12T00:00:00+07:00')
        other['manifest']=export_manifest(self.data,other);self.data['payment_history_coverage'].append(other)
        future=copy.deepcopy(self.tx());future.update(revision=2,observed_at='2026-10-12T00:00:00+07:00')
        self.data['transactions'].append(future)
        self.assertEqual(transaction_inputs(self.data,self.tx()),before)

    def test_claim_is_stale_when_relevant_revision_is_known_after_export(self):
        earlier=copy.deepcopy(self.data['payment_history_coverage'][0])
        earlier.update(observed_at='2026-10-10T08:59:00+07:00',covered_through='2026-10-10T08:59:00+07:00')
        earlier['manifest']=export_manifest(self.data,earlier);self.data['payment_history_coverage']=[earlier]
        self.assertFalse(self.report()['errors'])
        self.assertTrue(any(g['code']=='p1_history_scope_stale' for g in self.state()['gaps']))

    def test_vendor_mismatch_warns_and_blocks_p1_without_changing_links(self):
        other=copy.deepcopy(self.data['vendors'][0]);other['record_id']='V_OTHER';self.data['vendors'].append(other)
        self.tx()['vendor_ref']['record_id']='V_OTHER';self.rebind()
        report=self.report();self.assertFalse(report['errors'])
        self.assertTrue(any(w['code']=='P1_VENDOR_MISMATCH' for w in report['warnings']))
        self.assertFalse(self.state()['available'])
        self.assertEqual(self.tx()['vendor_ref']['record_id'],'V_OTHER')

    def test_same_ids_two_companies_do_not_share_claims_or_capability(self):
        two=p1_bundle('C002');two['payment_history_coverage']=[]
        for table,rows in two.items():
            if isinstance(rows,list):self.data.setdefault(table,[]).extend(rows)
        scope_two=scope(('C001','C002'));report=validate_input(self.data,scope_two)
        self.assertFalse(report['errors']);self.assertEqual(report['counts']['transactions'],11)
        one=transaction_inputs(self.data,self.tx())[1];other=transaction_inputs(self.data,next(r for r in self.data['transactions'] if r['company_id']=='C002' and r['record_id']=='T001'))[1]
        self.assertTrue(one['available']);self.assertFalse(other['available'])
        self.data['payment_history_coverage'][0]['company_id']='C002'
        denied=validate_input(self.data,self.scope)
        self.assertEqual(denied['errors'][0]['code'],'ACCESS_DENIED');self.assertFalse(denied['counts'])

    def test_source_ready_still_does_not_run_p1_or_change_feature_contract(self):
        frame=build_feature_rows(self.data,self.scope,AS_OF);private,public=_resolve(self.data,frame,self.scope)
        p1=next(r for r in public[('T001',1)]['rules'] if r['rule_id']=='P1')
        self.assertEqual(p1['source_status'],'ready');self.assertTrue(p1['input_details']['available'])
        self.assertIn('T002',{r['record_id'] for r in private[('T001',1)]['p1_transactions']})
        self.assertEqual(len(frame['contract']['columns']),33)
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshots.sqlite3')
            draft=store.upload(self.scope,canonical(self.data),'p1.json','p1-upload-source')
            preview=store.preview(self.scope,draft['import_id'],1)
            saved=store.commit(self.scope,draft['import_id'],commit_fields(preview),'p1-commit-source')
            self.assertEqual(saved['snapshot']['contract_version'],'1.1.0')
            result=score_snapshot(store,self.scope,saved['snapshot']['snapshot_id'],AS_OF,methods=())
            p1=next(r for r in next(r for r in result['rows'] if r['record_id']=='T001')['methods']['rules']['details']['rule_results']['rules'] if r['rule_id']=='P1')
            self.assertIsNone(p1['reason']);self.assertEqual(p1['status'],'evaluated_no_hit');self.assertEqual(p1['score'],0)
            features=build_from_snapshot(store,self.scope,saved['snapshot']['snapshot_id'],AS_OF)
            self.assertEqual(features['contract'],feature_contract())

    def test_explicit_empty_prior_history_is_distinct_from_missing_coverage(self):
        self.data['transactions']=[r for r in self.data['transactions'] if r['record_id']!='H0']
        self.data['payment_allocations']=[a for a in self.data['payment_allocations'] if a['record_id']!='A_H0']
        self.rebind();self.assertFalse(self.report()['errors'])
        frame=build_feature_rows(self.data,self.scope,AS_OF);private,public=_resolve(self.data,frame,self.scope)
        self.assertEqual(private[('T001',1)]['transaction_history'],[])
        self.assertEqual(next(r for r in public[('T001',1)]['rules'] if r['rule_id']=='P1')['source_status'],'ready')
        self.data['payment_history_coverage']=[]
        self.assertFalse(self.state()['available'])

    def test_since_inception_cannot_start_after_known_invoice_even_with_no_prior_payment(self):
        self.data['payment_allocations']=[a for a in self.data['payment_allocations'] if a['record_id']!='A_H0']
        self.data['payment_history_coverage'][0]['covered_from']='2026-10-10T00:00:00+07:00'
        self.rebind();self.assertIn('P1_COVERAGE_RANGE',self.errors())

    def test_channel_mapping_is_explicit_and_changing_it_invalidates_preview(self):
        raw=copy.deepcopy(self.data)
        for row in raw['transactions']:row['source_channel']=row.pop('payment_channel')
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshots.sqlite3')
            draft=store.upload(self.scope,canonical(raw),'mapped.json','mapped-upload-0001')
            report=store.preview(self.scope,draft['import_id'],1)
            self.assertEqual(report['status'],'rejected')
            changed=store.revise(self.scope,draft['import_id'],1,'mapped-columns-0001',mapping={'tables':{'transactions':{'source_channel':'payment_channel'}}})
            p=store.preview(self.scope,draft['import_id'],changed['revision'])
            self.assertNotEqual(p['status'],'rejected')
            store.revise(self.scope,draft['import_id'],changed['revision'],'mapped-columns-0002',mapping={})
            with self.assertRaises(ImportFailure):store.commit(self.scope,draft['import_id'],commit_fields(p),'mapped-stale-0001')

    def test_old_snapshot_unchanged_and_new_mapping_or_file_requires_new_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshots.sqlite3')
            old=canonical(bundle('C001'));draft=store.upload(self.scope,old,'old.json','old-upload-source')
            preview=store.preview(self.scope,draft['import_id'],1)
            saved=store.commit(self.scope,draft['import_id'],commit_fields(preview),'old-commit-source')
            self.assertEqual(saved['snapshot']['contract_version'],'1.0.0')
            newer=store.upload(self.scope,canonical(self.data),'new.json','new-upload-source')
            p=store.preview(self.scope,newer['import_id'],1)
            store.revise(self.scope,newer['import_id'],1,'change-file-0001',raw=canonical(dict(self.data,payment_history_coverage=[])),filename='changed.json')
            with self.assertRaises(ImportFailure):store.commit(self.scope,newer['import_id'],commit_fields(p),'stale-commit-0001')
            self.assertEqual(store.get_snapshot(self.scope,saved['snapshot']['snapshot_id'],data=True),old)


if __name__=='__main__':unittest.main()
