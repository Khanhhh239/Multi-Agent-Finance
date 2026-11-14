"""Durable company fit, frozen missing policies and inference without refitting."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import jsonschema
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.method_adapters import (fit_local_reference, score_batch, LocalArtifact, _versions)
from sme_fraud.method_jobs import run_fit_job, run_score_job, validate_config
from sme_fraud.method_store import MethodStore
from sme_fraud.method_preprocess import fit_preprocess, transform_frame
from sme_fraud.snapshot_features import build_from_snapshot, feature_contract
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.ml_estimators import CompanyEstimator
from sme_fraud.unsupervised_statistics import RobustZ
from test_validation_backend import policy_for
from test_snapshots import commit_fields
from test_method_adapters import frame, FROZEN
from test_snapshot_features import scope as test_scope

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from demo_method_scores import canonical_source


class CompanyMethodJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.snapshot_path=self.base/'snapshots.sqlite3';self.model_path=self.base/'models.sqlite3'
        self.snapshots=SnapshotStore(self.snapshot_path);self.models=MethodStore(self.model_path)
        self.token=secrets.token_urlsafe(32);self.reader=secrets.token_urlsafe(32)
        self.policy=policy_for(self.token)
        owner=self.policy['principals'][0]
        owner['memberships']=[dict(company_id=c,role='director',status='active',permissions=['data.import','model.fit']) for c in ('C001','C002')]
        reader=copy.deepcopy(policy_for(self.reader)['principals'][0]);reader['actor_id']='read-only'
        self.policy['principals'].append(reader)
        self.policy_file=self.base/'policy.json';self.save_policy();self.auth=FileAuthorizer(self.policy_file)
        self.header='Bearer '+self.token;self.read_header='Bearer '+self.reader
        self.source=canonical_source();self.snapshot=self.commit(self.source,'C001','base-upload-0001')

    def save_policy(self):self.policy_file.write_bytes(canonical(self.policy))
    def authority(self,company='C001'):return self.auth.authorize(self.header,company)

    def commit(self,source,company,key):
        scope=self.authority(company)
        draft=self.snapshots.upload(scope,canonical(source),'synthetic.json',key)
        preview=self.snapshots.preview(scope,draft['import_id'],1)
        return self.snapshots.commit(scope,draft['import_id'],commit_fields(preview),key+'-commit')['snapshot']['snapshot_id']

    def config(self,snapshot=None):
        return dict(version='company-fit-config/1.0.0',snapshot_id=snapshot or self.snapshot,method_id='ecod',
            missing_policy='median_flags',minimum_history=5,profile_id='technical-demo-not-production',evaluation_mode='backtest',
            history_start='2026-09-02T00:00:00+07:00',history_end='2026-09-12T00:00:00+07:00',
            reference_start='2026-09-15T00:00:00+07:00',reference_end='2026-09-20T00:00:00+07:00',evaluation_start='2026-10-01T00:00:00+07:00')

    def fit(self,config=None,key='fit-request-0001',company='C001'):
        return run_fit_job(self.snapshots,self.models,self.auth,self.header,company,config or self.config(),key)

    def score(self,artifact_id,snapshot=None,models=None):
        return run_score_job(self.snapshots,models or self.models,self.auth,self.read_header,'C001',snapshot or self.snapshot,
                             '2026-10-06T00:00:00+07:00',{'ecod':artifact_id})

    def count_artifacts(self):
        with closing(sqlite3.connect(self.model_path)) as conn:return conn.execute('SELECT count(*) FROM method_artifacts').fetchone()[0]

    def test_fit_persists_33_contract_and_fresh_reader_scores_without_fit(self):
        before=self.snapshots.get_snapshot(self.authority(),self.snapshot,data=True)
        result=self.fit();self.assertEqual(result['job']['status'],'succeeded')
        manifest=result['manifest'];self.assertEqual(len(manifest['feature_contract']['columns']),33)
        self.assertEqual(manifest['feature_contract'],feature_contract())
        self.assertEqual(manifest['history_rows'],10);self.assertEqual(manifest['reference_rows'],5)
        self.assertTrue(manifest['preprocess']['dropped_columns'])
        self.assertEqual(manifest['preprocess_sha256'],digest(canonical(manifest['preprocess'])))
        restarted=MethodStore(self.model_path)
        with (patch.object(CompanyEstimator,'fit',side_effect=AssertionError('Inference fit')),
              patch.object(RobustZ,'fit',side_effect=AssertionError('Inference fit')),
              patch('sme_fraud.method_jobs.fit_local_reference',side_effect=AssertionError('Inference fit'))):
            scored=self.score(result['job']['artifact_id'],models=restarted)
        new=[r for r in scored['rows'] if r['record_id'].startswith('T')]
        self.assertEqual(len(new),5);self.assertTrue(all(r['methods']['ecod']['available'] for r in new))
        self.assertEqual(before,self.snapshots.get_snapshot(self.authority(),self.snapshot,data=True))
        self.assertNotIn('model.fit',self.auth.authorize(self.read_header,'C001').permissions)

    def test_read_permission_cannot_create_fit_job(self):
        with self.assertRaises(ImportFailure) as error:
            run_fit_job(self.snapshots,self.models,self.auth,self.read_header,'C001',self.config(),'denied-fit-0001')
        self.assertEqual(error.exception.code,'MODEL_FIT_DENIED');self.assertEqual(self.count_artifacts(),0)

    def test_five_transaction_snapshot_returns_five_results_with_or_without_model(self):
        # Score a separate real snapshot containing exactly five new transactions,
        # rather than selecting five results from the twenty-row training source.
        source=copy.deepcopy(self.source)
        source['transactions']=[r for r in source['transactions'] if r['record_id'].startswith('T')]
        identities=[r['record_id'] for r in source['transactions']]
        source['payment_allocations']=[r for r in source['payment_allocations']
                                      if r['transaction_ref']['record_id'] in identities]
        snapshot=self.commit(source,'C001','five-transaction-input')
        schema=json.loads((ROOT/'sme_fraud/method_scores.schema.json').read_text('utf-8'))
        fitted=self.fit();artifact_id=fitted['job']['artifact_id']
        with closing(sqlite3.connect(self.model_path)) as conn:
            before=conn.iterdump();before='\n'.join(before)
        reader=MethodStore(self.model_path,read_only=True)
        with (patch.object(CompanyEstimator,'fit',side_effect=AssertionError('Inference fit')) as estimator_fit,
              patch.object(RobustZ,'fit',side_effect=AssertionError('Inference fit')) as stats_fit,
              patch('sme_fraud.method_jobs.fit_local_reference',side_effect=AssertionError('Inference fit')) as job_fit,
              patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('Inference fit')) as adapter_fit):
            available=self.score(artifact_id,snapshot=snapshot,models=reader)
            missing=self.score('mth_'+'0'*64,snapshot=snapshot,models=reader)
            unconfigured=run_score_job(self.snapshots,reader,self.auth,self.read_header,'C001',snapshot,
                                       '2026-10-06T00:00:00+07:00',{})
        for spy in (estimator_fit,stats_fit,job_fit,adapter_fit):spy.assert_not_called()
        for result in (available,missing,unconfigured):
            jsonschema.validate(result,schema)
            self.assertEqual(result['row_count'],5)
            self.assertEqual([r['record_id'] for r in result['rows']],identities)
            self.assertEqual([r['row_index'] for r in result['rows']],list(range(5)))
            self.assertTrue(all(r['company_id']=='C001' for r in result['rows']))
        self.assertTrue(all(r['methods']['ecod']['available'] for r in available['rows']))
        for result in (missing,unconfigured):
            for row in result['rows']:
                for method_id,method in row['methods'].items():
                    if method_id=='rules':continue  # Canonical rule bridge is a separate pending task.
                    self.assertFalse(method['available'])
                    self.assertIsNone(method['raw_score']);self.assertIsNone(method['score'])
                    self.assertEqual(method['reason']['code'],'artifact_missing')
        with closing(sqlite3.connect(self.model_path)) as conn:
            self.assertEqual('\n'.join(conn.iterdump()),before)

    def test_completed_retry_survives_restart_without_refit(self):
        first=self.fit();self.models=MethodStore(self.model_path)
        with patch('sme_fraud.method_jobs.fit_local_reference',side_effect=AssertionError('Retry refit')):again=self.fit()
        self.assertTrue(again['reused']);self.assertEqual(first['job'],again['job']);self.assertEqual(self.count_artifacts(),1)
        changed=self.config();changed['missing_policy']='strict'
        with self.assertRaises(ImportFailure) as error:self.fit(changed)
        self.assertEqual(error.exception.code,'FIT_IDEMPOTENCY_CONFLICT')

    def test_same_transaction_ids_in_two_companies_have_separate_models(self):
        one=self.fit();source=copy.deepcopy(self.source)
        for table,rows in source.items():
            if isinstance(rows,list):
                for row in rows:
                    row['company_id']='C002'
                    if table=='companies':row['record_id']='C002';row['name']='Doanh nghiệp mô phỏng C002'
                    if 'amount_vnd' in row:row['amount_vnd']*=2
                    for line in row.get('accounting_lines',[]):line['debit_vnd']*=2;line['credit_vnd']*=2
        snapshot=self.commit(source,'C002','company-two-upload')
        two=self.fit(self.config(snapshot),company='C002')
        self.assertEqual(two['job']['status'],'succeeded')
        self.assertNotEqual(one['job']['artifact_id'],two['job']['artifact_id'])
        with self.assertRaises(ImportFailure) as error:self.models.get_artifact(self.authority(),two['job']['artifact_id'])
        self.assertEqual(error.exception.status,404)

    def test_missing_model_and_corrupt_model_are_unavailable_without_loading(self):
        empty=run_score_job(self.snapshots,self.models,self.auth,self.read_header,'C001',self.snapshot,'2026-10-06T00:00:00+07:00',{})
        self.assertEqual(len(empty['rows']),20)
        self.assertTrue(all(not method['available'] for row in empty['rows'] for method in row['methods'].values()))
        missing=self.score('mth_'+'0'*64)
        self.assertEqual(len(missing['rows']),20)
        self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_missing' for r in missing['rows']))
        result=self.fit();identity=result['job']['artifact_id']
        with closing(sqlite3.connect(self.model_path)) as conn:
            with conn:
                conn.execute('DROP TRIGGER method_artifacts_update')
                conn.execute('UPDATE method_artifacts SET payload=? WHERE artifact_id=?',(b'corrupt',identity))
        with patch('sme_fraud.method_adapters.joblib.load',side_effect=AssertionError('Corrupt model loaded')):bad=self.score(identity)
        self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_invalid' for r in bad['rows']))

    def test_legacy_or_same_width_reordered_contract_never_reaches_model_load(self):
        result=self.fit();artifact=self.models.get_artifact(self.authority(),result['job']['artifact_id'])
        features=build_from_snapshot(self.snapshots,self.authority(),self.snapshot,'2026-10-06T00:00:00+07:00')
        legacy=json.loads(artifact.manifest);legacy['feature_contract_fingerprint']='legacy-98-feature-contract'
        old=LocalArtifact('mth_'+digest(canonical(legacy)),canonical(legacy),artifact.payload)
        reordered=copy.deepcopy(features);reordered['contract']['columns'].reverse()
        unsigned=dict(reordered['contract']);unsigned.pop('fingerprint');reordered['contract']['fingerprint']=digest(canonical(unsigned))
        for row in reordered['features']:row.reverse()
        for row in reordered['missing']:row.reverse()
        with patch('sme_fraud.method_adapters.joblib.load',side_effect=AssertionError('Incompatible model loaded')):
            a=score_batch(features,self.authority(),methods=('ecod',),artifacts={'ecod':old})
            b=score_batch(reordered,self.authority(),methods=('ecod',),artifacts={'ecod':artifact})
        self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_incompatible' for r in a['rows']+b['rows']))

    def test_full_contract_preprocess_and_runtime_mismatches_are_rejected_before_load(self):
        fitted=self.fit();artifact=self.models.get_artifact(self.authority(),fitted['job']['artifact_id'])
        features=build_from_snapshot(self.snapshots,self.authority(),self.snapshot,'2026-10-06T00:00:00+07:00')
        self.assertEqual(len(features['contract']['columns']),33)
        cases={
            'artifact_format':lambda m:m.update(version='legacy/0.0.0'),
            'wrong_method':lambda m:m.update(method_id='isolation_forest'),
            'preprocess_version':lambda m:m.update(preprocess_version='unknown/0.0.0'),
            'runtime_version':lambda m:m['versions']['runtime'].update(python='0.0.0'),
            'kernel_version':lambda m:m['versions']['implementation'].update(**{'ml_estimators.py':'0'*64}),
            # Keep the fingerprint identical on purpose: comparing it alone is insufficient.
            'contract_dtype':lambda m:m['feature_contract'].update(dtype='float32'),
            'contract_semantics':lambda m:m['feature_contract'].update(semantics='changed-without-new-fingerprint'),
        }
        schema=json.loads((ROOT/'sme_fraud/method_scores.schema.json').read_text('utf-8'))
        with (patch('sme_fraud.method_adapters.joblib.load',side_effect=AssertionError('Incompatible model loaded')) as load,
              patch.object(CompanyEstimator,'fit',side_effect=AssertionError('Inference fit')) as fit):
            for name,change in cases.items():
                with self.subTest(mismatch=name):
                    manifest=json.loads(artifact.manifest);change(manifest)
                    stale=LocalArtifact('mth_'+digest(canonical(manifest)),canonical(manifest),artifact.payload)
                    result=score_batch(features,self.authority(),methods=('ecod',),artifacts={'ecod':stale})
                    jsonschema.validate(result,schema)
                    self.assertEqual(result['row_count'],len(features['rows']))
                    for row in result['rows']:
                        method=row['methods']['ecod'];self.assertFalse(method['available'])
                        self.assertIsNone(method['score']);self.assertIsNone(method['raw_score'])
                        self.assertEqual(method['reason']['code'],'artifact_incompatible')
        load.assert_not_called();fit.assert_not_called()

    def test_strict_missing_policy_fails_without_silent_drop_or_model(self):
        config=self.config();config['missing_policy']='strict'
        result=self.fit(config)
        self.assertEqual(result['job']['status'],'failed');self.assertEqual(self.count_artifacts(),0)
        self.assertEqual(self.models.get_job(self.authority(),result['job']['job_id'])['failure_code'],'FIT_DATA_INVALID')

    def test_late_transaction_revision_does_not_replace_train_version(self):
        baseline=self.fit();source=copy.deepcopy(self.source)
        revised=copy.deepcopy(next(t for t in source['transactions'] if t['record_id']=='H0'))
        revised.update(revision=2,observed_at='2026-09-14T12:00:00+07:00',amount_vnd=99000007)
        revised['accounting_lines']=[dict(account='331',debit_vnd=99000007,credit_vnd=0),dict(account='112',debit_vnd=0,credit_vnd=99000007)]
        source['transactions'].append(revised)
        snapshot=self.commit(source,'C001','late-revision-upload')
        later=self.fit(self.config(snapshot),key='late-version-fit')
        self.assertEqual(later['job']['status'],'succeeded')
        self.assertEqual(later['manifest']['history_rows'],10)
        self.assertEqual(later['manifest']['preprocess'],baseline['manifest']['preprocess'])

    def test_fit_cannot_cross_reference_or_evaluation_windows(self):
        invalid=self.config();invalid['snapshot_id']={}
        with self.assertRaises(ValueError):validate_config(invalid)
        config=self.config();config['reference_end']='2026-10-03T00:00:00+07:00'
        with self.assertRaises(ValueError),patch('sme_fraud.method_jobs.fit_local_reference',side_effect=AssertionError('Invalid fit')):self.fit(config)
        config=self.config();config['evaluation_mode']='prospective'
        self.models=MethodStore(self.model_path,clock=lambda:datetime(2026,11,1,tzinfo=timezone.utc))
        result=self.fit(config);self.assertEqual(result['job']['status'],'failed');self.assertEqual(self.count_artifacts(),0)

    def test_prospective_fit_and_publication_must_finish_before_period(self):
        config=self.config();config['evaluation_mode']='prospective'
        early=lambda:datetime(2026,9,25,tzinfo=timezone.utc)
        late=lambda:datetime(2026,10,2,tzinfo=timezone.utc)
        self.models=MethodStore(self.model_path,clock=early)
        valid=self.fit(config,key='prospective-valid')
        self.assertEqual(valid['job']['status'],'succeeded');self.assertEqual(self.count_artifacts(),1)
        scored=self.score(valid['job']['artifact_id'])
        self.assertTrue(all(r['methods']['ecod']['available'] for r in scored['rows'] if r['record_id'].startswith('T')))
        original=fit_local_reference
        def slow(*args,**kwargs):
            artifact=original(*args,**kwargs);self.models.clock=late;return artifact
        with patch('sme_fraud.method_jobs.fit_local_reference',side_effect=slow):
            failed=self.fit(config,key='prospective-finished-late')
        self.assertEqual(failed['job']['status'],'failed');self.assertEqual(self.count_artifacts(),1)
        self.models.clock=early;event=self.models._event
        def late_publish(*args,**kwargs):
            event(*args,**kwargs)
            if args[3]=='succeeded':self.models.clock=late
        with patch.object(self.models,'_event',side_effect=late_publish),self.assertRaises(ImportFailure) as error:
            self.fit(config,key='prospective-publish-late')
        self.assertEqual(error.exception.code,'FIT_PERIOD_STARTED');self.assertEqual(self.count_artifacts(),1)

    def test_revoked_fit_cannot_publish_even_after_training_completes(self):
        original=fit_local_reference
        def revoke(*args,**kwargs):
            result=original(*args,**kwargs)
            self.policy['principals'][0]['memberships'][0]['permissions']=['data.import'];self.save_policy()
            return result
        with patch('sme_fraud.method_jobs.fit_local_reference',side_effect=revoke),self.assertRaises(ImportFailure):self.fit()
        self.assertEqual(self.count_artifacts(),0)
        with closing(sqlite3.connect(self.model_path)) as conn:self.assertEqual(conn.execute('SELECT status FROM fit_jobs').fetchone()[0],'running')

    def test_publication_rolls_back_artifact_and_success_audit_together(self):
        with closing(sqlite3.connect(self.model_path)) as conn:
            with conn:conn.execute("CREATE TRIGGER fail_success BEFORE INSERT ON fit_events WHEN NEW.event='succeeded' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        result=self.fit();self.assertEqual(result['job']['status'],'failed');self.assertEqual(self.count_artifacts(),0)

    def test_concurrent_receipts_claim_one_job(self):
        config=validate_config(self.config());manifest=self.snapshots.get_snapshot(self.authority(),self.snapshot)
        binding={k:manifest[k] for k in ('snapshot_id','tenant_id','company_id','checksum','data_checksum','contract_version')}
        request=dict(version='company-fit-job/1.0.0',config=config,snapshot=binding,feature_contract=feature_contract(),versions=_versions())
        def create(_):return self.models.begin_fit(self.authority(),request,'concurrent-fit-key')
        with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(create,range(10)))
        self.assertEqual(sum(claimed for job,claimed in results),1)
        self.assertEqual(len({job['job_id'] for job,claimed in results}),1)

    def test_legacy_storage_is_not_migrated_or_unpickled(self):
        with self.assertRaises(ImportFailure):MethodStore(self.snapshot_path)
        old=self.base/'legacy.pkl';old.write_bytes(b'legacy-pickle-file')
        with self.assertRaises(ImportFailure):MethodStore(old)
        self.assertEqual(old.read_bytes(),b'legacy-pickle-file')

    def test_score_store_is_read_only_and_missing_store_is_not_created(self):
        result=self.fit();identity=result['job']['artifact_id']
        reader=MethodStore(self.model_path,read_only=True)
        self.assertTrue(self.score(identity,models=reader)['rows'])
        with self.assertRaises(ImportFailure) as error:reader.begin_fit(self.authority(),{},'read-only-denied')
        self.assertEqual(error.exception.code,'MODEL_STORE_READ_ONLY')
        missing_path=self.base/'absent'/'models.sqlite3';missing=MethodStore(missing_path,read_only=True)
        scored=self.score(identity,models=missing)
        self.assertTrue(all(not r['methods']['ecod']['available'] for r in scored['rows']))
        self.assertFalse(missing_path.parent.exists())

    def test_cli_fits_and_scores_in_separate_processes_and_checks_permission_first(self):
        config=self.base/'fit.json';config.write_bytes(canonical(self.config()))
        owner=self.base/'owner.token';owner.write_text(self.token,encoding='utf-8')
        reader=self.base/'reader.token';reader.write_text(self.reader,encoding='utf-8')
        common=['--snapshot-db',str(self.snapshot_path),'--model-db',str(self.model_path),'--auth-file',str(self.policy_file),'--company','C001']
        fit_output=self.base/'fit-output.json'
        command=[sys.executable,'-X','utf8','-B','-m','sme_fraud.method_jobs','fit',*common,'--token-file',str(owner),'--config',str(config),'--idempotency-key','cli-fit-key-0001','--output',str(fit_output)]
        done=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(done.returncode,0,done.stdout+done.stderr);self.assertNotIn(self.token,done.stdout)
        identity=json.loads(fit_output.read_text('utf-8'))['job']['artifact_id']
        mapping=self.base/'mapping.json';mapping.write_bytes(canonical(dict(ecod=identity)))
        output=self.base/'score.json'
        command=[sys.executable,'-X','utf8','-B','-m','sme_fraud.method_jobs','score',*common,'--token-file',str(reader),'--snapshot-id',self.snapshot,'--as-of','2026-10-06T00:00:00+07:00','--artifacts-file',str(mapping),'--output',str(output)]
        done=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        result=json.loads(output.read_text('utf-8'));self.assertEqual(result['row_count'],20)
        self.assertTrue(all(r['methods']['ecod']['available'] for r in result['rows'] if r['record_id'].startswith('T')))
        denied_snapshot=self.base/'never-snapshot.sqlite3';denied_model=self.base/'never-model.sqlite3'
        denied=[sys.executable,'-X','utf8','-B','-m','sme_fraud.method_jobs','fit','--snapshot-db',str(denied_snapshot),'--model-db',str(denied_model),'--auth-file',str(self.policy_file),'--token-file',str(reader),'--company','C001','--output',str(self.base/'denied.json')]
        done=subprocess.run(denied,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(done.returncode,1);self.assertFalse(denied_snapshot.exists());self.assertFalse(denied_model.exists())


class MissingPolicyTests(unittest.TestCase):
    def test_median_uses_only_train_all_null_columns_are_frozen_out(self):
        history=frame(FROZEN['train'],'2025-01-01T00:00:00+07:00','H')
        reference=frame(FROZEN['test'],'2025-02-01T00:00:00+07:00','R')
        query=frame(FROZEN['test'],'2025-03-01T00:00:00+07:00','T')
        for i,row in enumerate(history['features']):
            row[1]=None;history['missing'][i][1]=True
            if i%3==0:row[0]=None;history['missing'][i][0]=True
        original=copy.deepcopy(history)
        for row in reference['features']:row[0]=1000000
        artifact=fit_local_reference(history,reference,test_scope(),'ecod',selected_columns=history['contract']['columns'],minimum_history=5,profile_id='missing-policy-test',missing_policy='median_flags')
        manifest=json.loads(artifact.manifest);state=manifest['preprocess']
        self.assertEqual(state['medians']['f0'],float(np.median([r[0] for r in history['features'] if r[0] is not None])))
        self.assertEqual(state['dropped_columns'],{'f1':'no_observed_training_values'})
        self.assertEqual(len(state['output_columns']),10);self.assertEqual(history,original)
        query['features'][0][0]=None;query['missing'][0][0]=True
        for c in state['kept_columns']:
            i=query['contract']['columns'].index(c);query['features'][1][i]=None;query['missing'][1][i]=True
        result=score_batch(query,test_scope(),methods=('ecod',),artifacts={'ecod':artifact})
        self.assertTrue(result['rows'][0]['methods']['ecod']['available'])
        self.assertEqual(result['rows'][0]['methods']['ecod']['details']['imputed_features'],['f0'])
        self.assertEqual(result['rows'][1]['methods']['ecod']['reason']['code'],'features_all_missing')
        self.assertIsNone(query['features'][0][0])


if __name__=='__main__':unittest.main()
