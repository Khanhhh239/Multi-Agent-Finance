"""Four-branch HTTP inference with real, company-specific offline fit artifacts."""
from contextlib import closing
import copy
import http.client
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import jsonschema
import numpy as np
from sme_fraud.analysis_resources import AnalysisResources,VERSION as BINDING_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical,digest
from sme_fraud.method_adapters import LocalArtifact
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.ml_estimators import CompanyEstimator,ALGORITHMS
from sme_fraud.unsupervised_statistics import RobustZ
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from test_validation_backend import policy_for
from test_snapshots import commit_fields
from test_p1_evaluation import payments,refresh,DAY

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from demo_method_scores import canonical_source
SCHEMA=json.loads((ROOT/'sme_fraud/snapshot_analysis.schema.json').read_text('utf-8'))


def query_source(company='C001'):
    data=payments([('T'+str(i),9_000_007 if i==4 else 1_100_003+i*17_239,DAY(i+1)) for i in range(5)],cap=100_000_000)
    data['invoices'][0]['record_id']='QUERY_INVOICE';data['invoices'][0]['source']['record_id']='QUERY_INVOICE';data['invoices'][0]['number']='QUERY-2026'
    for alloc in data['payment_allocations']:alloc['invoice_ref']['record_id']='QUERY_INVOICE'
    data['vendors'][0]['name']='Northern Harbour Industrial'
    peer=copy.deepcopy(data['vendors'][0]);peer['record_id']='PEER';peer['source']['record_id']='PEER';peer['name']='Delta Blossom Trading';data['vendors'].append(peer)
    for rows in data.values():
        if isinstance(rows,list):
            for row in rows:
                row['company_id']=company
                if rows is data['companies']:row['record_id']=company;row['source']['record_id']=company
    refresh(data)
    from sme_fraud.p1_inputs import export_manifest
    for claim in data['payment_history_coverage']:
        claim['company_id']=company
        claim['manifest']=export_manifest(data,claim)
    return data


class FourBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.base_temp.cleanup);cls.base=Path(cls.base_temp.name)
        cls.fit_token=secrets.token_urlsafe(32);policy=policy_for(cls.fit_token)
        policy['principals'][0]['memberships']=[dict(company_id=c,role='director',status='active',permissions=['data.import','model.fit']) for c in ('C001','C002')]
        path=cls.base/'fit-policy.json';path.write_bytes(canonical(policy));auth=FileAuthorizer(path)
        snapshots=SnapshotStore(cls.base/'snapshots.sqlite3');models=MethodStore(cls.base/'models.sqlite3');cls.artifacts={};cls.sids={};cls.training={}
        for company in ('C001','C002'):
            scope=auth.authorize('Bearer '+cls.fit_token,company)
            def commit(data,key):
                draft=snapshots.upload(scope,canonical(data),'fixture.json',key);report=snapshots.preview(scope,draft['import_id'],1)
                if report['status']=='rejected':raise AssertionError(report['errors'])
                return snapshots.commit(scope,draft['import_id'],commit_fields(report),key+'-save')['snapshot']['snapshot_id']
            training=canonical_source()
            for table,rows in training.items():
                if isinstance(rows,list):
                    for row in rows:
                        row['company_id']=company
                        if table=='companies':row['record_id']=company;row['source']['record_id']=company
            train_sid=commit(training,company+'-training');cls.training[company]=train_sid;cls.sids[company]=commit(query_source(company),company+'-query')
            methods=('robust_z',*ALGORITHMS) if company=='C001' else ('robust_z','ecod')
            for method in methods:
                config=dict(version='company-fit-config/1.0.0',snapshot_id=train_sid,method_id=method,missing_policy='strict',minimum_history=5,profile_id='four-branch-technical-demo',evaluation_mode='backtest',history_start='2026-09-02T00:00:00+07:00',history_end='2026-09-12T00:00:00+07:00',reference_start='2026-09-15T00:00:00+07:00',reference_end='2026-09-20T00:00:00+07:00',evaluation_start=DAY(1),selected_columns=['log_abs_amount','amount_negative'])
                fitted=run_fit_job(snapshots,models,auth,'Bearer '+cls.fit_token,company,config,company+'-fit-'+method)
                if fitted['job']['status']!='succeeded':raise AssertionError(fitted)
                cls.artifacts[company,method]=fitted['job']['artifact_id']
            if company=='C001':
                config.update(method_id='ecod',selected_columns=['log_abs_amount','journal_line_count'])
                fitted=run_fit_job(snapshots,models,auth,'Bearer '+cls.fit_token,company,config,'fit-missing-lines')
                if fitted['job']['status']!='succeeded':raise AssertionError(fitted)
                cls.lines_artifact=fitted['job']['artifact_id']
    @classmethod
    def tearDownClass(cls):cls.base_temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for name in ('snapshots.sqlite3','models.sqlite3'):shutil.copy2(self.base/name,self.root/name)
        self.token=secrets.token_urlsafe(32);policy=policy_for(self.token)
        policy['principals'][0]['memberships']=[dict(company_id=c,role='accountant' if c=='C001' else 'director',status='active',permissions=['data.import']) for c in ('C001','C002')]
        self.policy=policy;self.policy_path=self.root/'policy.json';self.policy_path.write_bytes(canonical(policy));self.auth=FileAuthorizer(self.policy_path)
        self.binding=dict(version=BINDING_VERSION,bindings=[dict(tenant_id='demo',company_id=c,statistics_artifact_id=self.artifacts[c,'robust_z'],ml_artifacts={'ecod':self.artifacts[c,'ecod']}) for c in ('C001','C002')])
        self.binding_path=self.root/'bindings.json';self.save_binding()
        self.store=SnapshotStore(self.root/'snapshots.sqlite3');self.resources=AnalysisResources(self.root/'models.sqlite3',self.binding_path)
        self.server=make_server(0,self.auth,self.store,self.resources);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5)
    def save_binding(self):self.binding_path.write_bytes(canonical(self.binding))
    def call(self,company='C001',view='review',sid=None,extra=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=40)
        try:
            c.request('POST',f'/api/v1/companies/{company}/snapshots/{sid or self.sids.get(company,self.sids["C001"])}/analyze',canonical(dict(as_of=DAY(6),view=view,**(extra or {}))),{'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()
    def valid(self,**kwargs):
        status,value=self.call(**kwargs);self.assertEqual(status,200,value);jsonschema.validate(value,SCHEMA);return value
    def check_unavailable(self,result):
        self.assertEqual(result['row_count'],5)
        for row in result['rows']:
            self.assertEqual(row['branches']['ml']['status'],'unavailable')
            self.assertTrue(all(r['relative_position'] is None for r in row['branches']['ml']['results']))
    def commit(self,data,key='extra-source'):
        scope=self.auth.authorize('Bearer '+self.token,'C001');draft=self.store.upload(scope,canonical(data),'extra.json',key);report=self.store.preview(scope,draft['import_id'],1)
        self.assertNotEqual(report['status'],'rejected',report)
        return self.store.commit(scope,draft['import_id'],commit_fields(report),key+'-save')['snapshot']['snapshot_id']
    def seed_older_artifact(self,change,payload_change=None):
        # Simulate a prior trusted producer's immutable DB row. No HTTP model
        # upload or production publisher is introduced by this fixture helper.
        with closing(sqlite3.connect(self.root/'models.sqlite3')) as conn:
            conn.row_factory=sqlite3.Row
            row=conn.execute('SELECT * FROM method_artifacts WHERE artifact_id=?',(self.artifacts['C001','ecod'],)).fetchone()
            manifest=json.loads(row['manifest_json']);change(manifest);raw=canonical(manifest);identity='mth_'+digest(raw)
            payload=payload_change(row['payload']) if payload_change else row['payload']
            conn.execute('INSERT INTO method_artifacts VALUES (?,?,?,?,?,?,?,?)',(identity,row['tenant_id'],row['company_id'],row['method_id'],row['job_id'],raw,payload,row['created_at']));conn.commit()
        self.binding['bindings'][0].update(statistics_artifact_id=None,ml_artifacts={'ecod':identity});self.save_binding()
        return identity
    def test_no_hit_rules_still_get_statistics_graph_and_ML_for_all_five(self):
        result=self.valid();self.assertEqual(result['row_count'],5)
        for row in result['rows']:
            self.assertTrue(all(c['status']=='no_signal' for c in row['checks'].values()),row['checks'])
            self.assertEqual(set(row['branches']),{'rules','statistics','graph','ml'})
            for branch in ('statistics','ml'):
                self.assertEqual(row['branches'][branch]['status'],'available')
                rank=row['branches'][branch]['results'][0]['relative_position'];self.assertIsInstance(rank,(int,float));self.assertTrue(0<=rank<=100)
            self.assertEqual(row['branches']['rules']['status'],'partial');self.assertFalse(row['branches']['rules']['available'])
            self.assertTrue(row['branches']['graph']['links']);self.assertTrue(row['branches']['graph']['findings'])
        self.assertEqual(result['summary']['transactions_to_review'],0);self.assertFalse(result['summary']['analysis_complete'])
    def test_inference_never_calls_fit_or_writes_model_store(self):
        with closing(sqlite3.connect(self.root/'models.sqlite3')) as conn:before='\n'.join(conn.iterdump())
        with (patch.object(CompanyEstimator,'fit',side_effect=AssertionError('No implicit fit')),
              patch.object(RobustZ,'fit',side_effect=AssertionError('No implicit fit')),
              patch('sme_fraud.method_jobs.run_fit_job',side_effect=AssertionError('No fit job')),
              patch.object(MethodStore,'publish',side_effect=AssertionError('No model write')),
              patch.object(MethodStore,'begin_fit',side_effect=AssertionError('No model job write'))):self.valid()
        with closing(sqlite3.connect(self.root/'models.sqlite3')) as conn:self.assertEqual(before,'\n'.join(conn.iterdump()))
    def test_all_four_retained_ML_choices_can_be_pinned_without_refit(self):
        for method in ALGORITHMS:
            with self.subTest(method=method):
                self.binding['bindings'][0]['ml_artifacts']={method:self.artifacts['C001',method]};self.save_binding()
                result=self.valid();self.assertTrue(all(r['branches']['ml']['available'] for r in result['rows']))
    def test_two_companies_with_same_ids_get_only_their_fitted_models(self):
        one=self.valid();two=self.valid(company='C002',view='technical')
        self.assertEqual([r['transaction_id'] for r in one['rows']],[r['transaction_id'] for r in two['rows']])
        self.assertTrue(all(r['methods']['ecod']['artifact_id']==self.artifacts['C002','ecod'] for r in two['rows']))
        self.assertNotEqual(one['analysis_id'],two['analysis_id'])
        self.assertEqual(self.call(view='technical')[0],403)
    def test_no_binding_or_store_keeps_five_rows_and_other_branches(self):
        self.resources.bindings_file=None;self.resources.model_db=None;result=self.valid();self.check_unavailable(result)
        self.assertTrue(all(r['branches']['statistics']['status']=='unavailable' and r['branches']['graph']['available'] for r in result['rows']))
    def test_missing_database_is_not_created_during_analysis(self):
        self.resources.model_db=self.root/'not-created'/'missing.sqlite3';result=self.valid();self.check_unavailable(result)
        self.assertFalse(self.resources.model_db.parent.exists())
    def test_invalid_bindings_fail_closed_without_disabling_law_or_graph(self):
        cases=[b'{',canonical(dict(version='wrong',bindings=[])),canonical(dict(self.binding,bindings=self.binding['bindings']*2))]
        bad=copy.deepcopy(self.binding);bad['bindings'][0]['ml_artifacts']={'catboost':'mth_'+'0'*64};cases.append(canonical(bad))
        for raw in cases:
            with self.subTest(raw=raw[:30]):self.binding_path.write_bytes(raw);self.check_unavailable(self.valid())
    def test_foreign_company_artifact_never_reaches_deserialization(self):
        row=self.binding['bindings'][0];row.update(statistics_artifact_id=None,ml_artifacts={'ecod':self.artifacts['C002','ecod']});self.save_binding()
        with patch('sme_fraud.method_adapters.joblib.load',side_effect=AssertionError('Foreign artifact loaded')):self.check_unavailable(self.valid())
    def test_no_implicit_latest_artifact_selection(self):
        self.binding['bindings'][0]['ml_artifacts']={};self.save_binding();result=self.valid();self.check_unavailable(result)
        self.assertTrue(all(r['branches']['ml']['results']==[] for r in result['rows']))
    def test_partially_available_selected_models_keep_valid_positions(self):
        self.binding['bindings'][0]['ml_artifacts'].update(lof='mth_'+'0'*64);self.save_binding();result=self.valid()
        for row in result['rows']:
            branch=row['branches']['ml'];self.assertEqual(branch['status'],'partial');self.assertEqual(sum(r['available'] for r in branch['results']),1)
    def test_other_tenant_binding_never_becomes_this_company_default(self):
        self.binding['bindings'][0]['tenant_id']='other-tenant';self.save_binding();self.check_unavailable(self.valid())
    def test_graph_missing_bank_code_keeps_weak_context_separate(self):
        data=query_source()
        for vendor in data['vendors']:vendor.pop('bank_code',None)
        result=self.valid(sid=self.commit(data))
        for row in result['rows']:
            graph=row['branches']['graph'];self.assertEqual(graph['status'],'partial');self.assertTrue(graph['missing_sources'])
            self.assertFalse(any('cùng tài khoản' in f['description'] for f in graph['findings']))
    def test_wrong_method_binding_is_unavailable(self):
        self.binding['bindings'][1]['ml_artifacts']={'ecod':self.artifacts['C002','robust_z']};self.save_binding();result=self.valid(company='C002',view='technical');self.check_unavailable(result)
        self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_incompatible' for r in result['rows']))
    def test_legacy_contract_order_runtime_or_preprocess_is_rejected_before_load(self):
        def fingerprint(m):m['feature_contract_fingerprint']='0'*64
        def columns(m):m['feature_contract']['columns'].reverse()
        def runtime(m):m['versions']['runtime']['numpy']='old-runtime'
        def preprocessing(m):m['preprocess_version']='legacy-preprocess'
        for change in (fingerprint,columns,runtime,preprocessing):
            with self.subTest(case=change.__name__):
                self.seed_older_artifact(change)
                with patch('sme_fraud.method_adapters.joblib.load',side_effect=AssertionError('Incompatible model loaded')):self.check_unavailable(self.valid())
    def test_corrupt_payload_is_unavailable_before_load_not_a_server_failure(self):
        self.seed_older_artifact(lambda m:m.update(profile_id='corruption-fixture'),lambda raw:raw+b'corrupt')
        with patch('sme_fraud.method_adapters.joblib.load',side_effect=AssertionError('Invalid model loaded')):self.check_unavailable(self.valid())
    def test_future_reference_cannot_score_past_transactions(self):
        self.seed_older_artifact(lambda m:m.update(reference_end=DAY(6)))
        with patch.object(CompanyEstimator,'score',side_effect=AssertionError('Future model scored history')):self.check_unavailable(self.valid())
    def test_prospective_artifact_created_later_cannot_score_past(self):
        def change(m):m['fit_context'].update(evaluation_mode='prospective',created_at='2026-11-12T00:00:00+07:00')
        self.seed_older_artifact(change)
        with patch.object(CompanyEstimator,'score',side_effect=AssertionError('Later model scored history')):self.check_unavailable(self.valid())
    def test_zero_relative_position_is_available_and_not_replaced_by_null(self):
        with patch.object(CompanyEstimator,'score',side_effect=lambda matrix:np.full(len(matrix),-1e9)):result=self.valid()
        self.assertTrue(all(r['branches']['ml']['available'] and r['branches']['ml']['results'][0]['relative_position']==0 for r in result['rows']))
    def test_strict_missing_predictor_is_null_not_zero(self):
        self.binding['bindings'][0]['ml_artifacts']={'ecod':self.lines_artifact};self.save_binding();result=self.valid();self.check_unavailable(result)
        self.assertTrue(all(r['branches']['ml']['results'][0]['missing_sources']==['Bản ghi kế toán'] for r in result['rows']))
    def test_training_identity_is_not_scored_as_new_observation(self):
        data=query_source();data['transactions'][0]['record_id']='H0';data['transactions'][0]['source']['record_id']='H0';data['payment_allocations'][0]['transaction_ref']['record_id']='H0';refresh(data)
        result=self.valid(sid=self.commit(data));self.assertEqual(result['rows'][0]['branches']['ml']['status'],'unavailable');self.assertTrue(all(r['branches']['ml']['available'] for r in result['rows'][1:]))
    def test_query_batch_does_not_change_frozen_reference(self):
        before=self.valid();data=query_source();data['transactions'][-1]['amount_vnd']=900_000_007;data['payment_allocations'][-1]['amount_vnd']=900_000_007;refresh(data)
        after=self.valid(sid=self.commit(data))
        for one,two in zip(before['rows'][:-1],after['rows'][:-1]):self.assertEqual(one['branches']['ml'],two['branches']['ml'])
    def test_review_contains_no_internal_model_algorithm_or_feature_details(self):
        result=self.valid();raw=json.dumps(result,ensure_ascii=False)
        for forbidden in ('artifact_id','method_id','raw_score','feature_contract','preprocess','selected_columns','isolation_forest','ecod','autoencoder','robust_z','fuzzy_similarity'):self.assertNotIn(forbidden,raw)
        self.assertTrue(all(r['branches']['ml']['results'][0]['retrospective'] for r in result['rows']))
    def test_binding_changes_during_compute_or_serialization_reject_stale_result(self):
        from sme_fraud.method_adapters import score_snapshot
        def change(*args,**kwargs):
            value=score_snapshot(*args,**kwargs);self.binding['bindings'][0]['ml_artifacts']={};self.save_binding();return value
        with patch('sme_fraud.method_adapters.score_snapshot',side_effect=change):self.assertEqual(self.call()[0],409)
        self.binding['bindings'][0]['ml_artifacts']={'ecod':self.artifacts['C001','ecod']};self.save_binding()
        def serialize(value):
            data=canonical(value);self.binding['bindings'][0]['ml_artifacts']={};self.save_binding();return data
        with patch('sme_fraud.analysis_api.canonical',side_effect=serialize):self.assertEqual(self.call()[0],409)
    def test_binding_changes_change_run_id_without_affecting_other_company(self):
        before=self.valid();foreign=self.valid(company='C002');self.binding['bindings'][0]['ml_artifacts']={'isolation_forest':self.artifacts['C001','isolation_forest']};self.save_binding()
        self.assertNotEqual(before['analysis_id'],self.valid()['analysis_id']);self.assertEqual(foreign['analysis_id'],self.valid(company='C002')['analysis_id'])
    def test_forbidden_client_model_selection_rejected_before_compute(self):
        for field in ('artifacts','methods','model_id','bindings'):
            with self.subTest(field=field):self.assertEqual(self.call(extra={field:{}})[0],400)
    def test_graph_never_uses_future_peer(self):
        data=query_source();data['vendors'][1]['observed_at']=DAY(6);sid=self.commit(data)
        result=self.valid(sid=sid)
        for row in result['rows']:
            graph=row['branches']['graph'];self.assertNotIn('PEER',{n.get('record_id') for n in graph['nodes']})
            for link in graph['links']:self.assertLessEqual(link['evidence']['observed_at'],row['knowledge_at'])
    def test_no_entity_graph_is_unavailable_not_an_empty_verified_network(self):
        data=query_source()
        for tx in data['transactions']:tx.pop('vendor_ref',None);tx.pop('employee_ref',None)
        refresh(data);result=self.valid(sid=self.commit(data))
        self.assertTrue(all(not r['branches']['graph']['available'] and r['branches']['graph']['status']=='unavailable' for r in result['rows']))
    def test_public_evidence_and_source_limits_remain_business_readable(self):
        result=self.valid();self.assertTrue(result['source_limits'])
        for row in result['rows']:
            ref=row['checks']['payment_invoice']['facts'][0]['invoice_refs'][0];self.assertEqual(ref['document_number'],'QUERY-2026')
            self.assertTrue(all('evidence' in link for link in row['branches']['graph']['links']))


if __name__=='__main__':unittest.main()
