"""Form eligibility agrees with training/scoring guards and never changes state."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.company_ml import CompanyML, dump
from sme_fraud.feature_contract import digest, sha
from company_ml_fixture import fixture, CHIEF, ACCOUNTANT, label_text

WINDOWS=dict(train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00')


class CompanyMLReadinessTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store,_,self.records=fixture(self.root)
        self.ml=CompanyML(self.store);self.update()
    def status(self):return self.ml.status('003','C001',CHIEF)
    def update(self,labels=''):
        state=self.status()
        return self.ml.update_data('003','C001',CHIEF,expected_revision=state['data']['revision'] if state['data'] else None,labels_text=labels)
    def readiness(self,**kw):
        return self.ml.readiness('003','C001',CHIEF,**(WINDOWS|kw))
    def csv_labels(self,transform=lambda rows:rows):
        rows=transform(list(csv.DictReader(io.StringIO(label_text(self.records)))))
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
        return stream.getvalue()
    def activate(self):
        state=self.status();revision=state['data']['revision']
        state=self.ml.evaluate('003','C001',CHIEF,expected_revision=revision,algorithm='ecod',alert_budget=.1,**WINDOWS)
        return self.ml.activate('003','C001',CHIEF,expected_revision=revision,expected_active=None,version_id=state['versions'][0]['version_id'])
    def score(self):
        state=self.status()
        return self.ml.score('003','C001',CHIEF,expected_revision=state['data']['revision'],expected_active=state['active_version'])

    def test_no_or_partial_training_labels_stay_blocked_despite_labels_elsewhere(self):
        state=self.readiness();self.assertTrue(state['evaluation']['eligible'])
        self.assertFalse(state['catboost']['eligible']);self.assertEqual(state['catboost']['verified_train_rows'],0)
        # Existing 2025 labels are outside this 2024 train window.
        text=self.csv_labels(lambda rows:[r for r in rows if r['transaction_id'].startswith('T') or r['transaction_id']=='C001_SIM_0'])
        data=self.update(text);self.assertGreater(data['data']['labels_count'],1)
        state=self.readiness();self.assertFalse(state['catboost']['eligible']);self.assertEqual(state['catboost']['verified_train_rows'],1)
        self.assertEqual(state['catboost']['missing_labels'],18)

    def test_complete_verified_labels_with_both_classes_match_actual_training_gate(self):
        self.update(label_text(self.records));state=self.readiness()
        self.assertTrue(state['catboost']['eligible'],state)
        self.assertEqual(state['catboost']['verified_train_rows'],state['catboost']['train_rows'])
        self.assertTrue(all(state['catboost']['class_counts'][key]>0 for key in ('0','1')))
        with patch('sme_fraud.company_ml.CompanyEstimator.fit',side_effect=RuntimeError('FIT_REACHED')):
            with self.assertRaisesRegex(RuntimeError,'FIT_REACHED'):
                self.ml.evaluate('003','C001',CHIEF,expected_revision=state['data_revision'],algorithm='catboost',alert_budget=.1,**WINDOWS)

    def test_label_at_exclusive_train_end_is_late_and_period_change_recomputes_coverage(self):
        text=self.csv_labels(lambda rows:[dict(r,reviewed_at=WINDOWS['train_end']) if r['transaction_id']=='C001_SIM_0' else r for r in rows])
        self.update(text);state=self.readiness()
        self.assertFalse(state['catboost']['eligible']);self.assertEqual(state['catboost']['late_labels'],1)
        with patch('sme_fraud.company_ml.CompanyEstimator.fit',side_effect=AssertionError('must not fit')):
            with self.assertRaisesRegex(ValueError,'trước cuối kỳ train'):
                self.ml.evaluate('003','C001',CHIEF,expected_revision=state['data_revision'],algorithm='catboost',alert_budget=.1,**WINDOWS)
        later=self.readiness(train_end='2024-01-21T00:00:00+07:00')
        self.assertTrue(later['catboost']['eligible']);self.assertEqual(later['catboost']['train_rows'],20)

    def test_one_class_is_blocked_before_estimator_fit(self):
        self.update(self.csv_labels(lambda rows:[dict(r,label='0') for r in rows]));state=self.readiness()
        self.assertFalse(state['catboost']['eligible']);self.assertIn('hai lớp',state['catboost']['reason'])
        with patch('sme_fraud.company_ml.CompanyEstimator.fit',side_effect=AssertionError('must not fit')):
            with self.assertRaisesRegex(ValueError,'hai lớp'):
                self.ml.evaluate('003','C001',CHIEF,expected_revision=state['data_revision'],algorithm='catboost',alert_budget=.1,**WINDOWS)

    def test_uninstalled_catboost_is_disabled_even_with_complete_labels(self):
        self.update(label_text(self.records))
        with patch('sme_fraud.company_ml.catalog',return_value=[dict(id='catboost',installed=False)]):
            state=self.readiness();self.assertFalse(state['catboost']['eligible']);self.assertIn('Chưa cài',state['catboost']['reason'])
            with self.assertRaisesRegex(ValueError,'Chưa cài'):
                self.ml.evaluate('003','C001',CHIEF,expected_revision=state['data_revision'],algorithm='catboost',alert_budget=.1,**WINDOWS)

    def test_invalid_empty_or_too_small_period_blocks_training_but_not_compatible_scoring(self):
        self.activate();self.update(label_text(self.records))
        for values in (dict(train_end=''),dict(train_end='invalid'),dict(train_end='2024-01-03T00:00:00+07:00'),
                       dict(train_end='2024-01-26T00:00:00+07:00')):
            with self.subTest(values=values):
                state=self.readiness(**values);self.assertFalse(state['evaluation']['eligible']);self.assertFalse(state['catboost']['eligible'])
                self.assertTrue(state['model']['can_score']);self.assertTrue(state['model']['can_keep'])

    def test_active_compatible_model_has_same_scoring_population_and_readiness_is_readonly(self):
        self.activate();before=sha(self.store.database)
        state=self.readiness();self.assertEqual(sha(self.store.database),before)
        self.assertTrue(state['model']['compatible']);self.assertTrue(state['model']['can_score']);self.assertTrue(state['model']['can_keep'])
        result=self.score();self.assertEqual(state['model']['inference_rows'],result['run']['rows'])

    def test_no_active_model_and_unconfigured_company_have_no_score_action(self):
        state=self.readiness();self.assertFalse(state['model']['can_score']);self.assertFalse(state['model']['can_keep'])
        state=self.ml.readiness('003','C002',CHIEF,**WINDOWS)
        self.assertIsNone(state['data_revision']);self.assertFalse(state['evaluation']['eligible']);self.assertFalse(state['model']['can_score'])

    def test_data_format_mismatch_blocks_readiness_and_actual_score(self):
        self.activate()
        with self.store.connection() as db:
            row=db.execute('SELECT * FROM company_ml_data WHERE company_id=?',('C001',)).fetchone()
            meta=json.loads(row['metadata']);meta['dataset_version']='other-source-format'
            revision=digest([meta,json.loads(row['records']),hashlib.sha256(row['matrix']).hexdigest(),json.loads(row['labels'])])
            db.execute('UPDATE company_ml_data SET metadata=?,revision=? WHERE company_id=?',(json.dumps(meta),revision,'C001'))
        state=self.readiness();self.assertFalse(state['model']['compatible']);self.assertFalse(state['model']['can_score']);self.assertFalse(state['model']['can_keep'])
        self.assertIn('khác hợp đồng',state['model']['reason'])
        with self.assertRaisesRegex(ValueError,'khác hợp đồng'):self.score()

    def test_corrupt_artifact_blocks_readiness_without_deserialization(self):
        self.activate()
        with self.store.connection() as db:db.execute('UPDATE company_ml_versions SET artifact=?',(b'CORRUPT',))
        with patch('sme_fraud.company_ml.joblib.load',side_effect=AssertionError('must not deserialize')):
            state=self.readiness();self.assertFalse(state['model']['can_score']);self.assertFalse(state['model']['can_keep'])
            with self.assertRaises(ValueError):self.score()

    def test_runtime_mismatch_and_frozen_metadata_mismatch_both_lock_scoring(self):
        self.activate()
        with patch('sme_fraud.company_ml.runtime',return_value={'different_runtime':True}):
            state=self.readiness();self.assertFalse(state['model']['compatible']);self.assertIn('môi trường',state['model']['reason'])
        with self.store.connection() as db:
            row=db.execute('SELECT version_id,metadata FROM company_ml_versions').fetchone()
            meta=json.loads(row['metadata']);meta['threshold']+=1
            db.execute('UPDATE company_ml_versions SET metadata=? WHERE version_id=?',(json.dumps(meta),row['version_id']))
        state=self.readiness();self.assertFalse(state['model']['compatible']);self.assertIn('không khớp',state['model']['reason'])

    def test_compatible_model_without_new_rows_can_be_kept_but_not_scored(self):
        self.activate()
        with self.store.connection() as db:
            _,meta,records,x,labels=self.ml._data(db,'C001')
            indices=[i for i,r in enumerate(records) if r['posted_at']<WINDOWS['calibration_end']]
            records=[records[i] for i in indices];blob=dump(x[indices]);meta=dict(meta,rows=len(records),last_at=records[-1]['posted_at'])
            revision=digest([meta,records,hashlib.sha256(blob).hexdigest(),labels])
            db.execute('UPDATE company_ml_data SET metadata=?,records=?,matrix=?,revision=? WHERE company_id=?',
                       (json.dumps(meta),json.dumps(records),blob,revision,'C001'))
        state=self.readiness();self.assertTrue(state['model']['compatible']);self.assertTrue(state['model']['can_keep']);self.assertFalse(state['model']['can_score'])
        with self.assertRaisesRegex(ValueError,'Không có giao dịch'):self.score()

    def test_scope_snapshot_revision_and_binding_checks(self):
        with self.assertRaises(PermissionError):self.ml.readiness('003','C001',None,**WINDOWS)
        with self.assertRaises(PermissionError):self.ml.readiness('003','C002',ACCOUNTANT,**WINDOWS)
        with self.assertRaises(ValueError):self.ml.readiness('005','C001',CHIEF,**WINDOWS)
        self.assertTrue(self.ml.readiness('003','C001',ACCOUNTANT,**WINDOWS)['evaluation']['eligible'])
        with self.assertRaises(RuntimeError):self.readiness(expected_revision='STALE')
        with self.assertRaises(RuntimeError):self.readiness(expected_active='STALE')


if __name__=='__main__':unittest.main()
