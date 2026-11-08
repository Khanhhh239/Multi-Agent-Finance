import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np

from sme_fraud.company_ml import CompanyML, labels_csv
from sme_fraud.generate import write_csv
from sme_fraud.ml_estimators import CompanyEstimator, FrozenECOD, catalog
from sme_fraud.review_roles import ReviewPrincipal
from company_ml_fixture import CHIEF, ACCOUNTANT, fixture, label_text, bind_cache


class StubBag:
    """Module-level so the artifact can be pickled and reloaded by the evaluation guard."""
    seen=None

    def fit(self,x,columns):
        StubBag.seen=list(columns);self.diagnostics_={'kind':'stub'};return self

    def score(self,x):
        return np.arange(len(x),dtype=float)


class EstimatorTest(unittest.TestCase):
    def test_all_five_fit_reload_and_score_with_fixed_batch_reference(self):
        rng=np.random.RandomState(42); x=rng.normal(size=(30,4)); future=rng.normal(size=(5,4))
        for info in catalog():
            if not info['installed'] or info['id']=='bag_injection':continue   # needs column names and 60+ rows: tests/test_bag_of_methods.py
            with self.subTest(algorithm=info['id']):
                model=CompanyEstimator(info['id']).fit(x,np.arange(30)%2)
                before=model.score(future)
                buffer=io.BytesIO();joblib.dump(model,buffer);restored=joblib.load(io.BytesIO(buffer.getvalue()))
                np.testing.assert_allclose(before,restored.score(future),rtol=1e-10)
                np.testing.assert_allclose(before[:1],restored.score(future[:1]),rtol=1e-10)
                self.assertTrue(np.isfinite(before).all())

    def test_ecod_reference_is_training_only_and_constant_columns_are_finite(self):
        model=FrozenECOD().fit(np.asarray([[1,5],[2,5],[3,5],[4,5],[100,5]]))
        reference=model.reference_.copy(); point=np.asarray([[200,8]])
        first=model.score(point)
        np.testing.assert_allclose(first,model.score(np.vstack([point,[[10000,80]]]))[:1])
        np.testing.assert_array_equal(reference,model.reference_)
        self.assertGreater(first[0],model.score(np.asarray([[3,5]]))[0])

    def test_no_unsupported_algorithm_small_train_nonfinite_or_fake_labels(self):
        with self.assertRaises(ValueError):CompanyEstimator('other')
        with self.assertRaises(ValueError):CompanyEstimator('lof').fit([[1],[2]])
        with self.assertRaises(ValueError):CompanyEstimator('ecod').fit([[float('nan')]]*5)
        with self.assertRaises(ValueError):CompanyEstimator('catboost').fit(np.ones((8,2)))


class CompanyMLTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store,self.data,self.records=fixture(self.root)
        self.ml=CompanyML(self.store);self.company='C001'

    def status(self,company=None):return self.ml.status('003',company or self.company,CHIEF)
    def update(self,labels='',company=None):
        company=company or self.company;current=self.status(company)
        return self.ml.update_data('003',company,CHIEF,expected_revision=current['data']['revision'] if current['data'] else None,labels_text=labels)
    def evaluate(self,algorithm='isolation_forest'):
        current=self.status()
        return self.ml.evaluate('003',self.company,CHIEF,expected_revision=current['data']['revision'],algorithm=algorithm,
            train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00',alert_budget=.1)
    def activate(self,version=None,rollback=False):
        current=self.status()
        return self.ml.activate('003',self.company,CHIEF,version_id=version or current['versions'][0]['version_id'],
            expected_active=current['active_version'],expected_revision=current['data']['revision'],rollback=rollback)
    def score(self):
        current=self.status()
        return self.ml.score('003',self.company,CHIEF,expected_active=current['active_version'],expected_revision=current['data']['revision'])

    def test_update_train_activate_score_restart_and_company_isolation(self):
        self.update();self.assertIsNone(self.status()['active_version'])
        candidate=self.evaluate();self.assertIsNone(candidate['active_version'])
        first=self.activate()['active_version'];scores=self.score()
        self.assertEqual(scores['run']['version_id'],first)
        self.assertTrue(all(r['company_id']=='C001' and r['posted_at']>='2024-01-25' for r in scores['items']))
        self.ml=CompanyML(self.store)
        self.assertEqual(self.status()['active_version'],first)
        self.assertIsNone(self.status('C002')['active_version'])
        self.update(company='C002');self.assertEqual(self.status()['active_version'],first)

    def test_all_available_algorithms_are_real_versioned_candidates(self):
        self.update(label_text(self.records))
        for info in catalog():
            if info['installed'] and info['id']!='bag_injection':   # needs 60+ train rows; wiring is tested separately
                state=self.evaluate(info['id'])
                self.assertEqual(state['versions'][0]['algorithm'],info['id'])
                self.activate();self.assertGreater(self.score()['run']['rows'],0)
        self.assertEqual(len(self.status()['versions']),sum(c['installed'] and c['id']!='bag_injection' for c in catalog()))

    def test_bag_injection_receives_column_names_and_its_diagnostics_are_stored(self):
        self.update()
        with patch('sme_fraud.bag_of_methods.BagOfMethods',StubBag):
            state=self.evaluate('bag_injection')
        self.assertEqual(StubBag.seen,state['data']['columns'])
        self.assertEqual(state['versions'][0]['algorithm'],'bag_injection')
        self.assertEqual(state['versions'][0]['diagnostics']['kind'],'stub')

    def test_update_keeps_active_version_and_predictions_without_refitting(self):
        self.update();self.evaluate();self.activate();old=self.score()
        with patch.object(CompanyEstimator,'fit',side_effect=AssertionError('must not fit')):
            self.update();self.ml.keep('003','C001',CHIEF,expected_active=self.status()['active_version'],expected_revision=self.status()['data']['revision'])
            new=self.score()
        self.assertEqual(old['run']['version_id'],new['run']['version_id'])
        self.assertEqual(old['items'],new['items'])

    def test_stale_data_and_activation_rejected_and_other_company_version_inaccessible(self):
        self.update();self.evaluate();old=self.status();self.activate()
        with self.assertRaises(RuntimeError):self.ml.activate('003','C001',CHIEF,version_id=old['versions'][0]['version_id'],expected_active=None,expected_revision=old['data']['revision'])
        with self.assertRaises(RuntimeError):self.ml.update_data('003','C001',CHIEF,expected_revision=None)
        self.update(company='C002');c2=self.status('C002')
        with self.assertRaises(KeyError):self.ml.activate('003','C002',CHIEF,version_id=old['versions'][0]['version_id'],expected_active=None,expected_revision=c2['data']['revision'])

    def test_rollback_only_to_previously_active_version(self):
        self.update();self.evaluate();first=self.activate()['active_version']
        self.evaluate('ecod');second=self.status()['versions'][0]['version_id']
        with self.assertRaises(ValueError):self.activate(second,rollback=True)
        self.activate(second);self.activate(first,rollback=True)
        self.assertEqual(self.status()['active_version'],first)
        self.assertEqual(self.status()['history'][-1]['action'],'rolled_back')

    def test_catboost_without_verified_labels_is_blocked_not_replaced(self):
        self.update()
        with self.assertRaisesRegex(ValueError,'CatBoost'):self.evaluate('catboost')
        self.assertEqual(self.status()['versions'],[])

    def test_future_known_training_label_is_blocked_and_not_inferred_from_rules(self):
        text=label_text(self.records).replace('2024-01-01T13:00:00+07:00','2025-01-01T13:00:00+07:00')
        self.update(text)
        with self.assertRaisesRegex(ValueError,'trước cuối kỳ train'):self.evaluate('catboost')

    def test_labels_invalid_scope_duplicate_missing_evidence_and_future_time_rejected(self):
        text=label_text(self.records)
        for invalid in (text.replace('C001,','C002,'),text+text.splitlines()[1]+'\n',
                        text.replace('SIM_DOCUMENT_T0',''),text.replace('2025-08-01T13:00:00+07:00','2027-08-01T13:00:00+07:00')):
            with self.subTest(invalid=invalid[:30]),self.assertRaises(ValueError):self.update(invalid)
        self.assertIsNone(self.status()['data'])

    def test_corrupt_cache_does_not_replace_saved_data(self):
        self.update();before=self.status()['data']['revision']
        with (self.data/'features.csv').open('a') as stream:stream.write('BAD\n')
        with self.assertRaises(ValueError):self.update()
        self.assertEqual(self.status()['data']['revision'],before)

    def test_eval_rows_do_not_fit_preprocessor_model_or_threshold(self):
        self.update();self.evaluate('lof');first=self.status()['versions'][0]
        with self.store.connection() as db:
            old=joblib.load(io.BytesIO(db.execute('SELECT artifact FROM company_ml_versions WHERE version_id=?',(first['version_id'],)).fetchone()[0]))
        import csv
        with (self.data/'features.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        next(r for r in rows if r['transaction_id']=='C001_SIM_29').update({key:999999 for key in rows[0] if key!='transaction_id'})
        write_csv(self.data/'features.csv',rows);bind_cache(self.data)
        self.update();self.evaluate('lof');second=self.status()['versions'][0]
        with self.store.connection() as db:
            new=joblib.load(io.BytesIO(db.execute('SELECT artifact FROM company_ml_versions WHERE version_id=?',(second['version_id'],)).fetchone()[0]))
        self.assertEqual(first['threshold'],second['threshold'])
        self.assertEqual(first['training_ids_sha256'],second['training_ids_sha256'])
        np.testing.assert_array_equal(old['estimator'].scaler_.mean_,new['estimator'].scaler_.mean_)
        np.testing.assert_array_equal(old['estimator'].model_._fit_X,new['estimator'].model_._fit_X)

    def test_updated_data_requires_new_candidate_but_preserves_old_active(self):
        self.update();self.evaluate();first=self.activate()['active_version']
        # Adding reviewed labels changes the data revision but must not switch the model.
        self.update(label_text(self.records))
        self.assertEqual(self.status()['active_version'],first)
        with self.assertRaisesRegex(ValueError,'dữ liệu cũ'):self.activate(first)
        self.assertEqual(self.score()['run']['version_id'],first)

    def test_holdout_permissions_invalid_windows_and_unconfigured_score(self):
        foreign=ReviewPrincipal('SIM_OTHER','SIM_X','Mô phỏng','director',('C003',))
        for principal in (None,ACCOUNTANT,foreign):
            with self.assertRaises(PermissionError):self.ml.update_data('003','C001',principal,expected_revision=None)
        with self.assertRaises(ValueError):self.ml.update_data('005','C001',CHIEF,expected_revision=None)
        self.update()
        with self.assertRaises(ValueError):self.score()
        with self.assertRaises(ValueError):self.ml.evaluate('003','C001',CHIEF,expected_revision=self.status()['data']['revision'],algorithm='lof',train_end='2024-01-25T00:00:00+07:00',calibration_end='2024-01-20T00:00:00+07:00',alert_budget=.1)
        self.assertFalse(self.ml.overview(ACCOUNTANT)['can_manage'])
        self.assertEqual(self.ml.overview(None)['companies'],[])

    def test_artifact_and_audit_tampering_block_use(self):
        self.update();self.evaluate();self.activate()
        with self.store.connection() as db:db.execute("UPDATE company_ml_versions SET artifact=?",(b'NOT_PICKLE',))
        with patch('sme_fraud.company_ml.joblib.load',side_effect=AssertionError('Do not deserialize corrupt artifact')):
            with self.assertRaises(ValueError):self.score()
        with self.store.connection() as db:db.execute("UPDATE company_ml_events SET data=replace(data,'SIM_CHIEF','OTHER')")
        with self.assertRaises(ValueError):self.status()

    def test_model_metadata_cannot_silently_change_the_frozen_threshold(self):
        self.update();self.evaluate();self.activate()
        with self.store.connection() as db:
            row=db.execute('SELECT version_id,metadata FROM company_ml_versions').fetchone()
            meta=json.loads(row['metadata']);meta['threshold']+=1
            db.execute('UPDATE company_ml_versions SET metadata=? WHERE version_id=?',(json.dumps(meta),row['version_id']))
        with self.assertRaisesRegex(ValueError,'không khớp cấu hình'):self.score()

    def test_preserves_labels_on_same_data_and_releases_training_lock_on_failure(self):
        self.update(label_text(self.records));count=self.status()['data']['labels_count']
        self.update();self.assertEqual(self.status()['data']['labels_count'],count)
        with patch.object(CompanyEstimator,'fit',side_effect=OSError('test disk/worker failure')):
            with self.assertRaises(OSError):self.evaluate()
        self.assertEqual(len(self.evaluate()['versions']),1)

    def test_never_reads_source_labels_or_splits(self):
        original=Path.open
        def opened(path,*args,**kwargs):
            if path.name in {'labels.csv','splits.csv','oracle.json','control_oracle.jsonl'}:
                raise AssertionError('Forbidden truth input')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened):
            self.update();self.evaluate();self.activate();self.score()

    def test_other_snapshot_cannot_use_the_current_snapshot_matrix(self):
        self.update();self.evaluate();self.activate()
        self.store.scenarios.append('001')
        with self.store.connection() as db:
            db.execute("INSERT INTO companies SELECT '001',company_id,data FROM companies WHERE scenario='003'")
        state=self.status()
        with self.assertRaisesRegex(ValueError,'bộ đang chọn'):
            self.ml.score('001','C001',CHIEF,expected_active=state['active_version'],expected_revision=state['data']['revision'])
        with self.assertRaisesRegex(ValueError,'bộ đang chọn'):
            self.ml.evaluate('001','C001',CHIEF,expected_revision=state['data']['revision'],algorithm='ecod',
                train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00',alert_budget=.1)

    def test_concurrent_activation_only_one_tab_can_win(self):
        from concurrent.futures import ThreadPoolExecutor
        self.update();self.evaluate();self.evaluate('ecod');state=self.status()
        def activate(version):
            try:
                self.ml.activate('003','C001',CHIEF,version_id=version['version_id'],expected_active=None,
                                 expected_revision=state['data']['revision'])
                return 'activated'
            except RuntimeError:
                return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(activate,state['versions']))
        self.assertCountEqual(results,['activated','stale'])

    def test_backup_restore_retains_active_artifact_and_scores(self):
        from sme_fraud.review_backup import create_backup, restore_backup, restored_store
        self.update();self.evaluate();active=self.activate()['active_version'];before=self.score()['items']
        create_backup(self.store.database,self.store.data_root,self.store.reports_root,self.root/'backup')
        restore_backup(self.root/'backup',self.root/'restored')
        restored=restored_store(self.root/'restored');restored.clock=self.store.clock
        self.ml=CompanyML(restored);self.store=restored
        self.assertEqual(self.status()['active_version'],active)
        self.assertEqual(self.score()['items'],before)


if __name__=='__main__':unittest.main()
