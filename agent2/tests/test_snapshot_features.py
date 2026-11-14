"""Causal replay against a frozen multi-company fixture and real legacy kernel."""
from contextlib import closing
import copy
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import secrets
import subprocess
import sys

from finance_input import AccessScope
from sme_fraud.feature_pipeline import export_artifact, read_artifact, run_job
from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.snapshot_features import build_feature_rows, build_from_snapshot, feature_contract
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields
from sme_fraud.auth import FileAuthorizer, AuthError
from test_validation_backend import policy_for

FIXTURE=Path(__file__).parent/'fixtures/r1_feature_replay_v1.json'
AS_OF='2026-10-10T11:00:00+07:00'


def bundle(company=None):
    value=json.loads(FIXTURE.read_text('utf-8'))
    if company:
        for table,rows in value.items():
            if isinstance(rows,list):value[table]=[r for r in rows if r['company_id']==company]
    return value


def scope(company='C001',actor='feature-reviewer'):
    return AccessScope('demo',frozenset({company} if isinstance(company,str) else company),actor,frozenset({'data.import'}))


def feature(result,company,id):
    row=next(r for r in result['rows'] if r['company_id']==company and r['record_id']==id)
    return dict(zip(result['contract']['columns'],result['features'][row['row_index']]))


def committed(store,company='C001',data=None,key='feature-upload'):
    authority=scope(company)
    draft=store.upload(authority,canonical(data or bundle(company)),'feature-fixture.json',key)
    report=store.preview(authority,draft['import_id'],1)
    saved=store.commit(authority,draft['import_id'],commit_fields(report),key+'-commit')
    return saved['snapshot']['snapshot_id']


class SnapshotFeatureTests(unittest.TestCase):
    def setUp(self):self.data=bundle('C001');self.scope=scope()
    def build(self,as_of=AS_OF):return build_feature_rows(self.data,self.scope,as_of)

    def test_real_retained_feature_engine_is_called(self):
        from sme_fraud import features
        original=features.build_features
        with patch('sme_fraud.snapshot_features.legacy.build_features',wraps=original) as engine:
            result=self.build()
        self.assertTrue(engine.called)
        self.assertEqual(len(result['rows']),3)
        f=feature(result,'C001','T001')
        self.assertAlmostEqual(f['log_abs_amount'],math.log1p(6000000),places=7)
        self.assertAlmostEqual(f['prior_type_history_log_count'],math.log1p(1),places=7)

    def test_same_id_in_two_companies_never_shares_history_or_graph_members(self):
        result=build_feature_rows(bundle(),scope(('C001','C002')),AS_OF)
        first=feature(result,'C001','T001');second=feature(result,'C002','T001')
        self.assertAlmostEqual(first['prior_type_history_log_count'],math.log(2),places=7)
        self.assertEqual(second['prior_type_history_log_count'],0)
        self.assertEqual(first['graph_employee_count_observed'],1)
        self.assertEqual(second['graph_employee_count_observed'],1)

    def test_late_document_cannot_change_past_features(self):
        with_late=self.build()
        self.data['supporting_documents']=[r for r in self.data['supporting_documents'] if r['record_id']!='DOC_LATE']
        without_late=self.build()
        self.assertEqual(with_late['features'],without_late['features'])
        self.assertEqual(with_late['missing'],without_late['missing'])
        self.assertEqual(with_late['evidence'],without_late['evidence'])
        self.assertEqual(feature(with_late,'C001','T001')['known_document_count'],1)

    def test_later_global_run_does_not_rewrite_first_availability_features(self):
        before=self.build();after=self.build('2026-10-13T00:00:00+07:00')
        self.assertEqual(feature(before,'C001','T001'),feature(after,'C001','T001'))
        self.assertGreater(len(after['rows']),len(before['rows']))

    def test_late_invoice_document_can_affect_a_later_transaction_only(self):
        late=next(d for d in self.data['supporting_documents'] if d['record_id']=='DOC_LATE')
        late['subject_refs']=[dict(table='invoices',record_id='I001',revision=1)]
        known=self.build('2026-10-13T00:00:00+07:00')
        self.data['supporting_documents'].remove(late)
        absent=self.build('2026-10-13T00:00:00+07:00')
        self.assertEqual(feature(known,'C001','T001'),feature(absent,'C001','T001'))
        self.assertEqual(feature(known,'C001','NEXT01')['known_document_count'],1)
        self.assertEqual(feature(absent,'C001','NEXT01')['known_document_count'],0)

    def test_all_feature_evidence_is_within_the_row_knowledge_and_valid_time(self):
        from sme_fraud.snapshot_features import utc
        result=self.build('2026-10-13T00:00:00+07:00')
        for row,evidence in zip(result['rows'],result['evidence']):
            for record in evidence['records']:
                self.assertLessEqual(utc(record['observed_at']),utc(row['as_of']))
                self.assertLessEqual(utc(record['effective_at']),utc(row['event_at']))

    def test_simultaneous_transactions_use_history_before_group(self):
        result=self.build()
        for id in ('T001','T002'):
            row=feature(result,'C001',id)
            self.assertAlmostEqual(row['prior_type_history_log_count'],math.log(2),places=7)
            self.assertEqual(row['prior_invoice_payment_count'],1)
            self.assertAlmostEqual(row['prior_invoice_allocation_log_abs'],math.log1p(4000000))

    def test_input_reordering_is_invariant(self):
        expected=self.build()
        for rows in self.data.values():
            if isinstance(rows,list):random.Random(73).shuffle(rows)
        actual=self.build()
        for key in ('features','missing','rows','evidence'):self.assertEqual(actual[key],expected[key])

    def test_equal_knowledge_timestamp_does_not_enter_same_arrival_group(self):
        history=next(r for r in self.data['transactions'] if r['record_id']=='H0')
        history['observed_at']='2026-10-10T09:00:00+07:00'
        result=self.build()
        self.assertEqual(feature(result,'C001','T001')['prior_type_history_log_count'],0)

    def test_equal_event_timestamp_not_history_even_when_known_earlier(self):
        history=next(r for r in self.data['transactions'] if r['record_id']=='H0')
        history.update(effective_at='2026-10-10T09:00:00+07:00',observed_at='2026-10-10T08:00:00+07:00')
        result=self.build()
        self.assertEqual(feature(result,'C001','T001')['prior_type_history_log_count'],0)

    def test_late_historical_transaction_not_used_before_known(self):
        history=next(r for r in self.data['transactions'] if r['record_id']=='H0')
        history['observed_at']='2026-10-12T10:00:00+07:00'
        result=self.build('2026-10-13T00:00:00+07:00')
        self.assertEqual(feature(result,'C001','T001')['prior_type_history_log_count'],0)

    def test_late_revision_never_replaces_known_past_before_cutoff(self):
        before=self.build()
        vendor=copy.deepcopy(self.data['vendors'][0]);vendor.update(revision=2,observed_at='2026-10-12T10:00:00+07:00',bank_account=None)
        self.data['vendors'].append(vendor)
        self.assertEqual(before['features'],self.build()['features'])
        self.assertEqual(feature(before,'C001','T001'),feature(self.build('2026-10-13T00:00:00+07:00'),'C001','T001'))

    def test_future_effective_master_not_applied_even_if_already_known(self):
        before=self.build()
        vendor=copy.deepcopy(self.data['vendors'][0]);vendor.update(revision=2,observed_at='2026-10-09T10:00:00+07:00',effective_at='2026-10-12T10:00:00+07:00',bank_account=None)
        self.data['vendors'].append(vendor)
        self.assertEqual(before['features'],self.build()['features'])

    def test_eligible_master_clear_replaces_old_graph_slot(self):
        vendor=copy.deepcopy(self.data['vendors'][0]);vendor.update(revision=2,observed_at='2026-10-10T08:30:00+07:00',effective_at='2026-10-10T08:30:00+07:00',bank_account=None)
        self.data['vendors'].append(vendor)
        row=feature(self.build(),'C001','T001')
        self.assertIsNone(row['graph_employee_count_observed'])
        self.assertIsNone(row['graph_vendor_count_observed'])

    def test_equivalent_offsets_produce_identical_vectors_and_rows(self):
        one=self.build()
        for rows in self.data.values():
            if isinstance(rows,list):
                for row in rows:
                    for field in ('observed_at','effective_at'):
                        from sme_fraud.snapshot_features import utc
                        row[field]=utc(row[field]).isoformat()
        two=self.build('2026-10-10T04:00:00Z')
        self.assertEqual(one['features'],two['features']);self.assertEqual(one['rows'],two['rows'])

    def test_microsecond_order_is_not_truncated_to_legacy_seconds(self):
        for row in self.data['transactions']:
            if row['record_id']=='T001':row.update(effective_at='2026-10-10T09:00:00.100001+07:00',observed_at='2026-10-10T09:00:00.100001+07:00')
            if row['record_id']=='T002':row.update(effective_at='2026-10-10T09:00:00.100002+07:00',observed_at='2026-10-10T09:00:00.100002+07:00')
        result=self.build()
        self.assertAlmostEqual(feature(result,'C001','T002')['prior_type_history_log_count'],math.log(3),places=7)

    def test_negative_and_zero_rows_survive_with_sign_and_missing_reasons(self):
        result=self.build('2026-10-13T00:00:00+07:00')
        negative=feature(result,'C001','ADJ001');zero=feature(result,'C001','Z0001')
        self.assertEqual(negative['amount_negative'],1);self.assertAlmostEqual(negative['log_abs_amount'],math.log1p(2000000),places=7)
        self.assertEqual(zero['amount_zero'],1);self.assertEqual(zero['log_abs_amount'],0)
        later=feature(result,'C001','NEXT01')
        self.assertIsNone(later['log_abs_deviation_from_history'])
        for row,values,missing,evidence in zip(result['rows'],result['features'],result['missing'],result['evidence']):
            self.assertEqual(missing,[v is None for v in values])
            self.assertEqual({n for n,v in zip(result['contract']['columns'],values) if v is None},set(evidence['missing_reasons']))

    def test_identifiers_labels_and_evidence_are_not_numeric_predictors(self):
        result=self.build()
        for forbidden in ('record_id','transaction_id','company_id','revision','snapshot_id','as_of','label','fraud_label','content_sha256'):
            self.assertNotIn(forbidden,result['contract']['columns'])
        self.assertTrue(all(v is None or type(v) in (float,int) for row in result['features'] for v in row))
        self.assertTrue(any(e['records'] for e in result['evidence']))
        self.data['transactions'][0]['fraud_label']=1
        with self.assertRaises(ImportFailure):self.build()

    def test_source_system_names_and_document_hashes_do_not_change_predictors(self):
        expected=self.build()['features']
        for rows in self.data.values():
            if isinstance(rows,list):
                for row in rows:row['source'].update(system='different-source',record_id='unrelated-source-id')
        for doc in self.data['supporting_documents']:doc['content_sha256']='f'*64
        self.assertEqual(expected,self.build()['features'])

    def test_renaming_ids_with_references_preserves_numeric_predictors(self):
        original=self.build()
        mappings={table:{r['record_id']:f'R{index:04d}' for index,r in enumerate(rows)}
                  for table,rows in self.data.items() if isinstance(rows,list) and table!='companies'}
        relation={'vendor_ref':'vendors','employee_ref':'employees','created_by_ref':'employees',
                  'transaction_ref':'transactions','invoice_ref':'invoices'}
        for table,rows in self.data.items():
            if not isinstance(rows,list):continue
            for row in rows:
                if table in mappings:row['record_id']=mappings[table][row['record_id']]
                for field,target in relation.items():
                    if row.get(field):row[field]['record_id']=mappings[target][row[field]['record_id']]
                if row.get('adjusts_ref'):row['adjusts_ref']['record_id']=mappings[table][row['adjusts_ref']['record_id']]
                for ref in row.get('subject_refs',[]):ref['record_id']=mappings[ref['table']][ref['record_id']]
        renamed=self.build()
        for row in original['rows']:
            self.assertEqual(feature(original,'C001',row['record_id']),feature(renamed,'C001',mappings['transactions'][row['record_id']]))

    def test_unprovided_policy_fields_are_not_imputed_into_predictors(self):
        result=self.build()
        for name in ('framework_tt133','created_holiday','self_approval_permitted','vendor_age_log_days','invoice_vat_fraction'):
            self.assertNotIn(name,result['contract']['columns'])
        self.assertIsNone(feature(result,'C001','T002')['observed_approval_limit_ratio'])

    def test_no_history_z_is_missing_instead_of_false_normal_zero(self):
        self.assertIsNone(feature(self.build(),'C001','T001')['abs_amount_history_z'])

    def test_input_is_never_mutated(self):
        before=copy.deepcopy(self.data);self.build();self.assertEqual(before,self.data)

    def test_late_transaction_revision_does_not_rewrite_earlier_revision_features(self):
        before=self.build()
        revised=copy.deepcopy(next(r for r in self.data['transactions'] if r['record_id']=='T001'))
        revised.update(revision=2,observed_at='2026-10-12T10:00:00+07:00',amount_vnd=9000000)
        self.data['transactions'].append(revised)
        self.assertEqual(before['features'],self.build()['features'])
        after=self.build('2026-10-13T00:00:00+07:00')
        self.assertEqual(next(r for r in after['rows'] if r['record_id']=='T001')['revision'],2)
        self.assertAlmostEqual(feature(after,'C001','T001')['log_abs_amount'],math.log1p(9000000),places=7)
        self.assertEqual(feature(before,'C001','T002'),feature(after,'C001','T002'))

    def test_prior_signed_allocation_adjustment_is_not_turned_positive(self):
        old=copy.deepcopy(next(a for a in self.data['payment_allocations'] if a['record_id']=='A_H0'))
        old.update(record_id='A_CORRECTION',kind='adjustment',amount_vnd=-1000000,
            effective_at='2026-10-09T09:00:00+07:00',observed_at='2026-10-09T09:00:00+07:00',
            adjustment_reason='Giảm phân bổ có nguồn',adjusts_ref=dict(record_id='A_H0',revision=1))
        self.data['payment_allocations'].append(old)
        result=self.build();f=feature(result,'C001','T001')
        self.assertEqual(f['prior_invoice_payment_count'],1)
        self.assertAlmostEqual(f['prior_invoice_allocation_log_abs'],math.log1p(3000000))
        index=next(r['row_index'] for r in result['rows'] if r['record_id']=='T001')
        self.assertEqual(result['evidence'][index]['prior_signed_allocation_vnd'],3000000)


class SnapshotFeatureArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.store=SnapshotStore(self.base/'snapshots.sqlite3')
        self.snapshot_id=committed(self.store)
    def build(self):return build_from_snapshot(self.store,scope(),self.snapshot_id,AS_OF)

    def test_committed_snapshot_pipeline_binds_checksums_and_separate_channels(self):
        result=self.build();saved=export_artifact(result,self.base/'features')
        artifact=read_artifact(saved['directory'])
        self.assertEqual(artifact['manifest']['snapshot']['snapshot_id'],self.snapshot_id)
        self.assertEqual(artifact['features'],result['features']);self.assertEqual(artifact['rows'],result['rows'])
        self.assertEqual(set(artifact['manifest']['files']),{'features.json','missing.json','rows.json','evidence.json','contract.json'})

    def test_artifact_retry_is_immutable_and_idempotent(self):
        result=self.build();first=export_artifact(result,self.base/'features');again=export_artifact(result,self.base/'features')
        self.assertEqual(first,again);self.assertEqual(len(list((self.base/'features').iterdir())),1)

    def test_artifact_corruption_is_rejected_not_overwritten(self):
        result=self.build();saved=export_artifact(result,self.base/'features')
        path=Path(saved['directory'])/'features.json';path.write_bytes(b'[]')
        with self.assertRaises(ImportFailure):read_artifact(saved['directory'])
        with self.assertRaises(ImportFailure):export_artifact(result,self.base/'features')
        self.assertEqual(path.read_bytes(),b'[]')

    def test_wrong_company_cannot_read_snapshot_for_feature_job(self):
        with self.assertRaises(ImportFailure) as error:build_from_snapshot(self.store,scope('C002'),self.snapshot_id,AS_OF)
        self.assertEqual(error.exception.status,404)

    def test_revoked_scope_before_publish_leaves_no_complete_artifact(self):
        result=self.build();calls=[]
        def recheck():
            calls.append(1)
            return scope() if len(calls)==1 else scope('C002')
        with self.assertRaises(ImportFailure):export_artifact(result,self.base/'features',scope=scope(),recheck=recheck)
        self.assertEqual(list((self.base/'features').iterdir()),[])


class FeaturePipelineAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.db=self.base/'snapshots.sqlite3'
        self.store=SnapshotStore(self.db);self.snapshot_id=committed(self.store)
        self.token=secrets.token_urlsafe(32);self.policy=policy_for(self.token)
        self.policy_file=self.base/'policy.json';self.policy_file.write_bytes(canonical(self.policy))
        self.token_file=self.base/'token.txt';self.token_file.write_text(self.token,encoding='utf-8')
        self.authorizer=FileAuthorizer(self.policy_file)

    def test_authorized_cli_exports_a_verified_artifact_without_printing_token(self):
        command=[sys.executable,'-X','utf8','-B','-m','sme_fraud.feature_pipeline',
            '--snapshot-db',str(self.db),'--auth-file',str(self.policy_file),'--token-file',str(self.token_file),
            '--company','C001','--snapshot-id',self.snapshot_id,'--as-of',AS_OF,'--output-dir',str(self.base/'out')]
        result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertNotIn(self.token,result.stdout)
        artifact=read_artifact(next((self.base/'out').iterdir()))
        self.assertEqual(artifact['manifest']['row_count'],3)

    def test_unauthorized_cli_does_not_open_business_database(self):
        self.token_file.write_text(secrets.token_urlsafe(32),encoding='utf-8')
        target=self.base/'never-create.sqlite3'
        command=[sys.executable,'-X','utf8','-B','-m','sme_fraud.feature_pipeline',
            '--snapshot-db',str(target),'--auth-file',str(self.policy_file),'--token-file',str(self.token_file),
            '--company','C001','--snapshot-id',self.snapshot_id,'--as-of',AS_OF,'--output-dir',str(self.base/'out')]
        result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,1);self.assertFalse(target.exists());self.assertFalse((self.base/'out').exists())

    def test_scope_revocation_after_build_prevents_export(self):
        from sme_fraud.feature_pipeline import build_from_snapshot
        def revoke(*args,**kwargs):
            result=build_from_snapshot(*args,**kwargs)
            self.policy['principals'][0]['status']='revoked';self.policy_file.write_bytes(canonical(self.policy))
            return result
        with patch('sme_fraud.feature_pipeline.build_from_snapshot',side_effect=revoke),self.assertRaises(AuthError):
            run_job(self.store,self.authorizer,'Bearer '+self.token,'C001',self.snapshot_id,AS_OF,self.base/'out')
        self.assertFalse((self.base/'out').exists())


if __name__=='__main__':unittest.main()
