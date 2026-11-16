"""Real snapshot/rule engine joins; synthetic saved shadow DTOs, no FHE claim."""
from copy import deepcopy
from contextlib import closing
from dataclasses import replace
import hashlib
import math
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from batch_training_support import native_batches
from training_snapshot_support import commit
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.import_files import ImportFailure,canonical,digest
from sme_fraud.rule_snapshot_features import build_from_rule_snapshot
from sme_fraud.pipeline_benchmark import build_matrix,benchmark_shadow_run


class SavedManager:
    def __init__(self,shadow):self.shadow=shadow;self.called=False
    def get_shadow_run(self,scope,sid,recheck=None):
        self.called=True
        return dict(shadow_run=deepcopy(self.shadow))


class PipelineBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.scope=AccessScope('batch-demo',frozenset({'C001'}),'benchmark-operator',frozenset({'data.import'}))
        self.store=SnapshotStore(self.root/'snapshots.sqlite3');self.data,request=native_batches()
        self.sid=commit(self.store,self.data,self.scope);self.as_of=request['as_of']
        self.manifest=self.store.get_snapshot(self.scope,self.sid)
        self.analysis=analyze_snapshot(self.store,self.scope,self.sid,self.as_of,technical=True)
        frame=build_from_rule_snapshot(self.store,self.scope,self.sid,self.as_of,candidates_only=False)
        bykey={(r['record_id'],r['revision']):(r,frame['features'][i]) for i,r in enumerate(frame['rows'])}
        columns=frame['contract']['columns'];rows=[]
        for tx in self.data['source']['tables']['transactions']:
            meta,x=bykey[tx['transaction_id'],1]
            z=(x[columns.index('round_million')]+x[columns.index('creator_equals_approver')]-1)/2
            rows.append(dict(record_id=tx['transaction_id'],revision=1,event_at=meta['event_at'],
                available=True,status='scored',score=1/(1+math.exp(-z)),history_status='new_transaction',is_new_transaction=True,issues=[]))
        self.shadow=dict(tenant_id='batch-demo',company_id='C001',shadow_run_id='shrun_1_synthetic',
            snapshot={k:self.manifest[k] for k in ('snapshot_id','checksum','data_checksum')},
            model=dict(approved_for_shadow=True,approval_sha256='a'*64,model_cipher_sha256='b'*64),rows=rows)
        self.shadow['snapshot']['as_of']=self.as_of

    def join(self,analysis=None,shadow=None):
        return build_matrix(self.scope,analysis or self.analysis,shadow or self.shadow,self.manifest,self.data)

    def denied(self,code,fn):
        with self.assertRaises(ImportFailure) as ctx:fn()
        self.assertEqual(ctx.exception.code,code)

    def test_real_engine_preserves_all_candidates_35_rules_and_method_coverage(self):
        result=self.join()
        self.assertEqual(result['candidate_rows'],12)
        self.assertTrue(all(len(r['rule_results'])==35 for r in result['rows']))
        self.assertTrue(all('supervised_shadow' in r['methods'] for r in result['rows']))
        self.assertEqual(result['coverage']['supervised_shadow']['available'],12)
        self.assertEqual(result['status'],'technical_only');self.assertFalse(result['fit_performed'])
        self.assertFalse(result['operational_queue_changed'])
        self.assertTrue(all(a['selected_count']<=5 for a in result['comparison']['arms']))

    def test_missing_model_stays_unavailable_and_raw_scales_not_combined(self):
        result=self.join()
        self.assertIsNone(result['unsupervised_method'])
        self.assertFalse(result['comparison']['raw_scores_mixed_across_methods'])
        self.assertTrue(all(r['methods']['supervised_shadow']['percentile'] is None for r in result['rows']))
        self.assertTrue(all(a['recall'] is None and a['precision_resolved'] is None for a in result['comparison']['arms']))

    def test_each_arm_preserves_rule_baseline_and_fill_only_unused_slots(self):
        analysis=deepcopy(self.analysis);analysis['catalogue_results']=[];analysis['groups']=[]
        for row in analysis['rows']:
            for e in row['rule_coverage']['rules']:
                if e['rule_id'] not in ('D1','D2','D3','D4','D5','D6','F4'):
                    e.update(status='evaluated_no_hit',score=0,hits=[])
        result=self.join(analysis=analysis)
        arms={a['name']:a for a in result['comparison']['arms']}
        self.assertEqual(arms['rules_only']['selected'],[])
        self.assertEqual(arms['rules_plus_supervised_shadow']['selected_count'],5)
        self.assertEqual(arms['rules_plus_unsupervised']['selected_count'],0)
        self.assertFalse(result['comparison']['prospective'])

    def test_seen_training_and_holdout_excluded_without_dropping_matrix_rows(self):
        shadow=deepcopy(self.shadow)
        shadow['rows'][0].update(is_new_transaction=False,history_status='seen_in_training')
        shadow['rows'][1].update(is_new_transaction=False,history_status='seen_in_evaluation')
        result=self.join(shadow=shadow)
        self.assertEqual(len(result['rows']),12);self.assertGreaterEqual(result['excluded_rows'],2)
        for arm in result['comparison']['arms']:
            self.assertNotIn([shadow['rows'][0]['record_id'],1],arm['selected'])
            self.assertNotIn([shadow['rows'][1]['record_id'],1],arm['selected'])

    def test_unavailable_shadow_null_preserved(self):
        shadow=deepcopy(self.shadow);shadow['rows'][0].update(available=False,status='unavailable',score=None,issues=[dict(code='FEATURE_MISSING')])
        result=self.join(shadow=shadow)
        branch=result['rows'][0]['methods']['supervised_shadow']
        self.assertFalse(branch['available']);self.assertIsNone(branch['raw_score'])
        self.assertEqual(branch['reason'][0]['code'],'FEATURE_MISSING')

    def test_snapshot_cutoff_scope_approval_and_revision_binding(self):
        for kind,code in [('snapshot','BENCHMARK_SNAPSHOT_MISMATCH'),('cutoff','BENCHMARK_CUTOFF_MISMATCH'),('scope','BENCHMARK_SCOPE'),('approval','BENCHMARK_MODEL_NOT_APPROVED'),('revision','BENCHMARK_ROW_BINDING')]:
            shadow=deepcopy(self.shadow)
            if kind=='snapshot':shadow['snapshot']['data_checksum']='0'*64
            if kind=='cutoff':shadow['snapshot']['as_of']='2025-08-14T00:00:00+07:00'
            if kind=='scope':shadow['company_id']='C002'
            if kind=='approval':shadow['model']['approved_for_shadow']=False
            if kind=='revision':shadow['rows'][0]['revision']=2
            with self.subTest(kind=kind):self.denied(code,lambda:self.join(shadow=shadow))

    def test_nonfinite_or_invented_unavailable_score_rejected(self):
        for score in (float('nan'),float('inf'),-1,2):
            shadow=deepcopy(self.shadow);shadow['rows'][0]['score']=score
            self.denied('BENCHMARK_SHADOW_SCORE',lambda:self.join(shadow=shadow))
        shadow=deepcopy(self.shadow);shadow['rows'][0]['available']=False
        self.denied('BENCHMARK_SHADOW_SCORE',lambda:self.join(shadow=shadow))

    def test_saved_run_wrapper_does_not_write_snapshot_or_fit_models(self):
        manager=SavedManager(self.shadow);before=hashlib.sha256(self.store.path.read_bytes()).hexdigest()
        result=benchmark_shadow_run(self.store,manager,self.scope,self.shadow['shadow_run_id'])
        self.assertTrue(manager.called);self.assertEqual(result['candidate_rows'],12)
        self.assertEqual(hashlib.sha256(self.store.path.read_bytes()).hexdigest(),before)
        self.assertFalse((self.root/'models.sqlite3').exists())

    def test_revocation_before_read_and_before_return(self):
        manager=SavedManager(self.shadow)
        denied=lambda:replace(self.scope,company_ids=frozenset({'C002'}))
        self.denied('AUTH_CONTEXT_CHANGED',lambda:benchmark_shadow_run(self.store,manager,self.scope,'x',recheck=denied))
        self.assertFalse(manager.called)

    def test_report_checksum_is_reproducible_from_bound_results(self):
        first=self.join();second=self.join();self.assertEqual(first,second)
        expected=first.pop('report_sha256');self.assertEqual(digest(canonical(first)),expected)

    def test_multiple_real_model_pins_require_explicit_benchmark_choice(self):
        analysis=deepcopy(self.analysis)
        analysis['bridge_provenance']['model_pins'].update(ecod=dict(artifact_id='one'),isolation_forest=dict(artifact_id='two'))
        self.denied('BENCHMARK_METHOD_SELECTION_REQUIRED',lambda:self.join(analysis=analysis))

    def test_config_reopens_both_existing_key_derivations_without_rewriting_history(self):
        from types import SimpleNamespace
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from sme_fraud.batch_training_api import BatchTrainingManager
        from sme_fraud.label_packets import LabelStore
        raw=b'synthetic-state-key-32-bytes-00000'[:32]
        jobs=HKDF(algorithm=hashes.SHA256(),length=64,salt=b'he-node-jobs-v1',info=b'enterprise-storage-and-idempotency').derive(raw)
        for kind,material in [('portal',jobs[32:]),('legacy',raw)]:
            key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-batch-training-v1',info=b'enterprise-batch-training').derive(material)
            path=self.root/(kind+'.sqlite3');manager=BatchTrainingManager(path,key)
            state=dict(tenant_id=self.scope.tenant_id,company_id='C001',revision=1,run_id='test-run',phase='plan_ready')
            with manager._tx(self.scope,None,'data.import') as conn:manager._append(conn,self.scope.tenant_id,'C001',state)
            config=self.root/(kind+'.json');config.write_text(json.dumps(dict(node_state_key_file='synthetic-only',batch_training_db=str(path))),encoding='utf-8')
            with closing(manager._connect()) as conn:before=bytes(conn.execute('SELECT ciphertext FROM batch_training_journal').fetchone()[0])
            with patch('experiments.he_inference.key_manager.load_key',return_value=SimpleNamespace(material=raw)):
                reopened=BatchTrainingManager.from_config(config)
            with closing(reopened._connect()) as conn:
                self.assertEqual(reopened._latest(conn,self.scope.tenant_id,'C001'),state)
                self.assertEqual(bytes(conn.execute('SELECT ciphertext FROM batch_training_journal').fetchone()[0]),before)
            with patch('experiments.he_inference.key_manager.load_key',return_value=SimpleNamespace(material=b'X'*32)):
                self.denied('BATCH_TRAINING_STATE_KEY_MISMATCH',lambda:BatchTrainingManager.from_config(config))


if __name__=='__main__':unittest.main()
