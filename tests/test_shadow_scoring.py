"""Score-only replay boundaries: no fit, labels, queue changes or holdout access."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.shadow_scoring import run_shadow, main, np, joblib, sklearn
from sme_fraud.feature_contract import cache_contract, current_contract, sha
from sme_fraud.generate import write_csv


class ReplayEstimator:
    n_features_in_=len(current_contract()['columns'])

    def fit(self,*args,**kwargs):
        raise AssertionError('Runner must never fit')

    def score_samples(self,x):
        return -0.5-np.asarray(x[:,0],dtype=np.float64)/100


class ShadowScoringTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.dataset=self.root/'cache';self.dataset.mkdir()
        self.model_dir=self.root/'models';self.model_dir.mkdir()
        self.model=self.model_dir/'trusted.joblib'
        self.columns=current_contract()['columns']
        self.transactions=[dict(transaction_id=t,company_id=c,posted_at=d) for t,c,d in [
            ('T1','C001','2025-01-01T09:00:00+07:00'),('T2','C001','2025-01-02T09:00:00+07:00'),
            ('T3','C002','2025-01-01T09:00:00+07:00'),('T4','C001','2025-01-03T09:00:00+07:00')]]
        self.features=[dict(transaction_id=t['transaction_id'],**{c:i+1 for c in self.columns}) for i,t in enumerate(self.transactions)]
        write_csv(self.dataset/'transactions.csv',self.transactions)
        write_csv(self.dataset/'features.csv',self.features)
        self.bind()
        artifact=dict(model=ReplayEstimator(),dataset_version=self.metadata['version'],feature_columns=self.columns,
            feature_contract_fingerprint=self.metadata['feature_contract']['fingerprint'],sklearn_version=sklearn.__version__,
            training_feature_fingerprint='SIM_TRAIN_FINGERPRINT',score_direction='higher_is_more_anomalous')
        joblib.dump(artifact,self.model)
        self.scope=dict(company_ids=['C001'],start_at='2025-01-01T09:00:00+07:00',end_at='2025-01-03T09:00:00+07:00',source_ref='SIM_TECHNICAL_TEST')

    def tearDown(self):self.temp.cleanup()

    def bind(self):
        files={n:dict(sha256=sha(self.dataset/n)) for n in ('transactions.csv','features.csv')}
        # No label/split files exist. They are not inference dependencies.
        files.update({'labels.csv':{'sha256':'MUST_NOT_READ'},'splits.csv':{'sha256':'MUST_NOT_READ'}})
        self.metadata=dict(version='fixture-v1',feature_columns=self.columns,files=files,feature_contract=cache_contract(files))
        self.save_metadata()

    def save_metadata(self):
        (self.dataset/'manifest.json').write_text(json.dumps(self.metadata),encoding='utf-8')

    def run_score(self,name='output',**values):
        args=dict(model_sha256=sha(self.model),scope=self.scope)
        args.update(values)
        return run_shadow(self.dataset,self.model,self.root/name,**args)

    def test_company_time_scope_and_score_direction_are_explicit(self):
        before={p:sha(p) for p in (self.model,self.dataset/'features.csv',self.dataset/'transactions.csv',self.dataset/'manifest.json')}
        result=self.run_score()
        import csv
        with (self.root/'output/shadow_scores.csv').open() as stream:rows=list(csv.DictReader(stream))
        self.assertEqual([r['transaction_id'] for r in rows],['T1','T2'])
        self.assertEqual({r['company_id'] for r in rows},{'C001'})
        self.assertGreater(float(rows[1]['anomaly_score']),float(rows[0]['anomaly_score']))
        self.assertEqual(result['rows_scored'],2)
        self.assertEqual(result['models_fitted'],0)
        for field in ('labels_loaded','splits_loaded','queue_changed','threshold_changed','external_notifications','operational_benefit_measured','source_acceptance_verified'):
            self.assertFalse(result[field],field)
        self.assertEqual(set(rows[0]),{'run_id','transaction_id','company_id','posted_at','anomaly_score'})
        self.assertEqual(before,{p:sha(p) for p in before})

    def test_replay_is_deterministic_across_batch_sizes_and_never_overwrites(self):
        first=self.run_score('first',batch_size=1)
        second=self.run_score('second',batch_size=5)
        self.assertEqual(first['run_id'],second['run_id'])
        self.assertEqual((self.root/'first/shadow_scores.csv').read_bytes(),(self.root/'second/shadow_scores.csv').read_bytes())
        with self.assertRaises(FileExistsError):self.run_score('first')

    def test_no_label_or_split_reads_even_if_manifest_lists_them(self):
        original=Path.open
        def opened(path,*args,**kwargs):
            if path.name in {'labels.csv','splits.csv'}:raise AssertionError('Forbidden label/split read')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened):self.run_score()

    def test_wrong_model_hash_rejected_before_deserialization(self):
        with patch('sme_fraud.shadow_scoring.joblib.load',side_effect=AssertionError('must not deserialize')):
            with self.assertRaisesRegex(ValueError,'Model checksum'):self.run_score(model_sha256='wrong')
        self.assertFalse((self.root/'output').exists())

    def test_dataset_format_mismatch_is_not_bypassed(self):
        self.metadata['version']='synthetic-source-world-v1';self.save_metadata()
        with patch.object(ReplayEstimator,'score_samples',side_effect=AssertionError('must not score')):
            with self.assertRaisesRegex(ValueError,'dataset_format_version_mismatch'):self.run_score()
        self.assertFalse((self.root/'output').exists())

    def test_legacy_semantics_rejected_before_deserialization(self):
        del self.metadata['feature_contract'];self.save_metadata()
        with patch('sme_fraud.shadow_scoring.joblib.load',side_effect=AssertionError('must not deserialize')):
            with self.assertRaisesRegex(ValueError,'Legacy feature cache'):self.run_score()

    def test_changed_source_or_feature_file_is_rejected(self):
        for name in ('features.csv','transactions.csv'):
            path=self.dataset/name;original=path.read_bytes()
            path.write_bytes(original+b'changed')
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'checksum'):self.run_score()
            path.write_bytes(original)
        self.assertFalse((self.root/'output').exists())

    def test_scope_validation_and_empty_window(self):
        bad=[dict(company_ids=[]),dict(company_ids=['C001','C001']),dict(company_ids=['UNKNOWN']),
             dict(start_at='2025-01-01T00:00:00'),dict(end_at=self.scope['start_at']),
             dict(start_at='2028-01-01T00:00:00+07:00',end_at='2028-01-02T00:00:00+07:00'),
             dict(source_ref=''),dict(unexpected=True)]
        for values in bad:
            with self.subTest(values=values),self.assertRaises(ValueError):self.run_score(scope=dict(self.scope,**values))
        for size in (0,True,10001):
            with self.assertRaises(ValueError):self.run_score(batch_size=size)

    def test_nonfinite_values_and_extra_feature_columns_rejected(self):
        self.features[0][self.columns[0]]='nan'
        write_csv(self.dataset/'features.csv',self.features);self.bind()
        with self.assertRaisesRegex(ValueError,'Nonfinite'):self.run_score()
        for row in self.features:row['fraud_label']=1;row[self.columns[0]]=1
        write_csv(self.dataset/'features.csv',self.features);self.bind()
        with self.assertRaisesRegex(ValueError,'ordered allowlist'):self.run_score()

    def test_duplicate_and_unmapped_observations_rejected(self):
        for identifier in ('T1','UNKNOWN'):
            self.features[1]['transaction_id']=identifier
            write_csv(self.dataset/'features.csv',self.features);self.bind()
            with self.subTest(identifier=identifier),self.assertRaises(ValueError):self.run_score()

    def test_naive_source_time_and_duplicate_transaction_id_rejected(self):
        self.transactions[0]['posted_at']='2025-01-01T09:00:00'
        write_csv(self.dataset/'transactions.csv',self.transactions);self.bind()
        with self.assertRaisesRegex(ValueError,'timezone'):self.run_score()
        self.transactions[0]['posted_at']='2025-01-01T09:00:00+07:00'
        self.transactions[1]['transaction_id']='T1'
        write_csv(self.dataset/'transactions.csv',self.transactions);self.bind()
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.run_score()

    def test_malformed_estimator_output_leaves_no_partial_run(self):
        for result in (np.array([.5]),np.array([np.nan,np.nan]),np.ones((2,1))):
            with patch.object(ReplayEstimator,'score_samples',return_value=result):
                with self.assertRaisesRegex(ValueError,'invalid scores'):self.run_score()
            self.assertFalse((self.root/'output').exists())

    def test_source_changed_during_scoring_is_rejected(self):
        def changed(estimator,x):
            (self.dataset/'transactions.csv').write_text('changed',encoding='utf-8')
            return -np.ones(len(x))
        with patch.object(ReplayEstimator,'score_samples',changed):
            with self.assertRaisesRegex(ValueError,'checksum'):self.run_score()
        self.assertFalse((self.root/'output').exists())

    def test_manifest_paths_cannot_escape_cache(self):
        self.metadata['files']['../outside.csv']={'sha256':'x'}
        self.metadata['feature_contract']=cache_contract(self.metadata['files']);self.save_metadata()
        with self.assertRaisesRegex(ValueError,'plain filenames'):self.run_score()

    def test_failed_output_write_removes_only_its_staged_files(self):
        with patch.object(Path,'write_text',side_effect=OSError('SIM_DISK_FAILURE')):
            with self.assertRaisesRegex(OSError,'SIM_DISK_FAILURE'):self.run_score()
        self.assertFalse((self.root/'output').exists())
        self.assertEqual(list(self.root.glob('.shadow-*')),[])

    def test_unsafe_output_and_holdout_are_rejected_before_reading(self):
        for output in (self.dataset/'new',self.model_dir/'new'):
            with self.assertRaises(ValueError):
                run_shadow(self.dataset,self.model,output,model_sha256=sha(self.model),scope=self.scope)
        frozen=self.root/'frozen';frozen.mkdir();(frozen/'case_queue.csv').write_text('frozen')
        with self.assertRaisesRegex(ValueError,'snapshots'):
            run_shadow(self.dataset,self.model,frozen/'new',model_sha256=sha(self.model),scope=self.scope)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Holdout must not be read')):
            with self.assertRaisesRegex(ValueError,'005'):
                run_shadow(self.root/'sme_fraud_005',self.model,self.root/'new',model_sha256='unused',scope=self.scope)

    def test_cli_produces_a_score_only_manifest(self):
        scope=self.root/'scope.json';scope.write_text(json.dumps(self.scope),encoding='utf-8')
        args=['shadow_scoring','--dataset',str(self.dataset),'--model',str(self.model),'--model-sha256',sha(self.model),
              '--scope',str(scope),'--output',str(self.root/'cli')]
        with patch('sys.argv',args),contextlib.redirect_stdout(io.StringIO()) as captured:main()
        self.assertEqual(json.loads(captured.getvalue())['rows_scored'],2)
