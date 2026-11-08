"""Equal-population/capacity, label timing and truthful human-review metrics."""
import copy
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sme_fraud.company_ml import CompanyML, dump
import hashlib
from sme_fraud.company_ml_comparison import compare, collect, read_snapshots, REVIEW_FIELDS, IDENTITY
from sme_fraud.feature_contract import digest, sha
from sme_fraud.ml_estimators import CompanyEstimator, catalog
from sme_fraud.data_import import DataImport
from company_ml_fixture import CHIEF, label_text
from test_data_import import import_fixture, upload_rows, csv_bytes
import base64

WINDOWS=dict(train_start='2024-01-01T00:00:00+07:00',train_end='2024-01-19T12:00:00+07:00',
             calibration_end='2024-01-25T12:00:00+07:00',evaluation_end='2024-01-31T00:00:00+07:00')


class ComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store,_=import_fixture(self.root/'source');self.ml=CompanyML(self.store);self.importer=DataImport(self.ml)
        for company in ('C001','C002'):
            preview=self.importer.preview('003',company,CHIEF,filename='demo.csv',expected_revision=None,
                content_base64=base64.b64encode(csv_bytes(upload_rows(company,count=30))).decode())
            self.importer.commit('003',company,CHIEF,token=preview['token'],acknowledge=True)
        self.database=self.root/'source/review.sqlite3'
        self.counter=0
    def run_comparison(self,**kw):
        self.counter+=1;out=self.root/f'comparison{self.counter}'
        report=compare(self.database,out,companies=kw.pop('companies',['C001','C002']),scenario=kw.pop('scenario','003'),
                       windows=kw.pop('windows',WINDOWS),review_count=kw.pop('review_count',5),source_kind='synthetic_demo',**kw)
        return out,report
    def add_labels(self,company='C001',transform=None):
        with self.store.connection() as db:revision,_,records,_,_=self.ml._data(db,company)
        text=label_text(records,company)
        if transform:
            rows=list(csv.DictReader(io.StringIO(text)));rows=transform(rows)
            stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows);text=stream.getvalue()
        preview=self.ml.preview_labels('003',company,CHIEF,expected_revision=revision,labels_text=text)
        return self.ml.update_labels('003',company,CHIEF,expected_revision=revision,labels_text=text,
            conflict_policy='replace_conflicts',preview_hash=preview['preview_hash'],acknowledge=True,
            reason='SIM: thay nhãn kiểm thử để kiểm tra cổng CatBoost')
    def filled_reviews(self,root,**changes):
        with (root/'human_reviews.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        created=json.loads((root/'private/comparison.json').read_text())['plan']['created_at']
        stamp=(datetime.fromisoformat(created)+timedelta(minutes=1)).isoformat()
        for i,row in enumerate(rows):
            row.update(useful='yes' if i%2==0 else 'unknown',business_action='SIM: đối chiếu và điều chỉnh chứng từ',
                rationale='SIM: dữ liệu kiểm thử, không phải kết luận thực tế',evidence_refs='SIM_RECORD',active_review_minutes='3',
                timing_method='stopwatch',reviewer_id='SIM_HUMAN',reviewed_at=stamp,human_verified='1')
            row.update(changes)
        target=self.root/'SIMULATED_filled_reviews.csv'
        with target.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=REVIEW_FIELDS);writer.writeheader();writer.writerows(rows)
        return target,rows,datetime.fromisoformat(stamp)+timedelta(minutes=1)

    def test_four_models_same_company_populations_capacity_and_source_database_untouched(self):
        before=sha(self.database);out,report=self.run_comparison()
        self.assertEqual(sha(self.database),before);self.assertIsNone(report['business_winner'])
        self.assertEqual(report['completed_human_reviews'],0)
        for company in ('C001','C002'):
            models=[m for m in report['models'] if m['company_id']==company]
            self.assertEqual(len(models),5);evaluated=[m for m in models if m['status']=='evaluated']
            self.assertEqual(len(evaluated),4)
            self.assertEqual(len({digest(m['population_sha256']) for m in evaluated}),1)
            for model in evaluated:
                self.assertEqual((model['train_rows'],model['calibration_rows'],model['evaluation_rows']),(18,6,6))
                self.assertEqual(model['selected_for_review'],5);self.assertEqual(len(model['selected_review_ids']),5)
                self.assertIsNone(model['useful_alerts']);self.assertIsNone(model['actual_review_minutes'])
                self.assertTrue((out/model['artifact_path']).is_file())
            self.assertIn('0/18',models[-1]['reason'])
        public=[json.loads(p.read_text(encoding='utf-8')) for p in (out/'public/evidence').glob('*.json')]
        self.assertEqual(len(public),report['review_units'])
        for unit in public:
            self.assertFalse({'algorithm','rank','score','label','is_fraud'}&unit.keys())
            self.assertFalse({'algorithm','rank','score','label','is_fraud'}&unit['source_record'].keys())
        self.assertNotIn('algorithm',(out/'human_reviews.csv').read_text(encoding='utf-8-sig'))

    def test_fits_only_common_train_and_never_passes_unverified_y(self):
        captured=[];original=CompanyEstimator.fit
        def fit(estimator,x,y=None):
            captured.append((estimator.algorithm,x.copy(),y));return original(estimator,x,y)
        snapshots=read_snapshots(self.database,['C001','C002'],'003')
        with patch.object(CompanyEstimator,'fit',fit):self.run_comparison(algorithms=['ecod'])
        for (_,x,y),company in zip(captured,('C001','C002')):
            np.testing.assert_array_equal(x,snapshots[company]['x'][:18]);self.assertIsNone(y)

    def test_catboost_requires_all_train_labels_both_classes_and_pre_train_cutoff(self):
        with patch.object(CompanyEstimator,'fit',side_effect=AssertionError('CatBoost must not fit')):
            _,report=self.run_comparison(algorithms=['catboost']);self.assertTrue(all(m['status']=='skipped' for m in report['models']))
        self.add_labels(transform=lambda rows:[dict(r,label='0') for r in rows])
        _,report=self.run_comparison(companies=['C001'],algorithms=['catboost'])
        self.assertIn('hai lớp',report['models'][0]['reason'])
        self.add_labels(transform=lambda rows:[dict(r,reviewed_at='2024-02-01T00:00:00+07:00') for r in rows])
        with patch.object(CompanyEstimator,'fit',side_effect=AssertionError('late labels must not fit')):
            _,report=self.run_comparison(companies=['C001'],algorithms=['catboost']);self.assertIn('0/18',report['models'][0]['reason'])
        self.add_labels()
        if next(c for c in catalog() if c['id']=='catboost')['installed']:
            _,report=self.run_comparison(companies=['C001'],algorithms=['catboost'])
            self.assertEqual(report['models'][0]['status'],'evaluated')

    def test_partial_labels_never_enable_catboost(self):
        self.add_labels(transform=lambda rows:rows[:1])
        with patch.object(CompanyEstimator,'fit',side_effect=AssertionError('incomplete labels must not fit')):
            _,report=self.run_comparison(companies=['C001'],algorithms=['catboost'])
        self.assertIn('1/18',report['models'][0]['reason'])

    def test_stale_source_rejected_before_writing_output(self):
        snapshots=read_snapshots(self.database,['C001','C002'],'003');changed=copy.deepcopy(snapshots);changed['C001']['revision']='new'
        with patch('sme_fraud.company_ml_comparison.read_snapshots',side_effect=[snapshots,changed]):
            with self.assertRaises(RuntimeError):self.run_comparison(algorithms=['ecod'])
        self.assertFalse((self.root/'comparison1').exists())

    def test_tied_scores_use_locked_hash_order_and_exact_budget_reproducibly(self):
        with self.store.connection() as db:
            _,meta,records,x,labels=self.ml._data(db,'C001');blob=dump(np.zeros_like(x))
            revision=digest([meta,records,hashlib.sha256(blob).hexdigest(),labels])
            db.execute('UPDATE company_ml_data SET matrix=?,revision=? WHERE company_id=?',(blob,revision,'C001'))
        _,first=self.run_comparison(companies=['C001'],algorithms=['ecod'])
        _,second=self.run_comparison(companies=['C001'],algorithms=['ecod'])
        self.assertEqual(first['models'][0]['selected_review_ids'],second['models'][0]['selected_review_ids'])
        self.assertEqual(first['models'][0]['selected_for_review'],5)
        self.assertEqual(first['models'][0]['calibration_threshold_alerts'],0)

    def test_invalid_budget_windows_existing_output_holdout_and_source_output_overlap(self):
        for count in (0,7,True):
            with self.assertRaises(ValueError):self.run_comparison(review_count=count,algorithms=['ecod'])
        with self.assertRaises(ValueError):self.run_comparison(windows=WINDOWS|dict(train_end=WINDOWS['calibration_end']))
        with self.assertRaises(ValueError):self.run_comparison(scenario='005')
        with self.assertRaises(ValueError):compare(self.database,self.database.parent/'output',companies=['C001'],scenario='003',windows=WINDOWS,review_count=5)
        out,_=self.run_comparison(algorithms=['ecod'])
        with self.assertRaises(ValueError):compare(self.database,out,companies=['C001'],scenario='003',windows=WINDOWS,review_count=5)

    def test_blank_reviews_remain_pending_and_do_not_invent_benefit_or_time(self):
        out,report=self.run_comparison(algorithms=['ecod'])
        result=collect(out,out/'human_reviews.csv',self.root/'blank_results')
        self.assertEqual(result['completed_human_reviews'],0);self.assertIsNone(result['business_winner'])
        for model in result['metrics']:
            self.assertIsNone(model['useful_at_budget']);self.assertIsNone(model['full_budget_review_minutes'])
            self.assertIsNone(model['useful_rate_among_decidable'])

    def test_simulated_review_collection_deduplicates_effort_keeps_unknown_separate(self):
        out,report=self.run_comparison(algorithms=['ecod','lof'])
        reviews,rows,now=self.filled_reviews(out)
        result=collect(out,reviews,self.root/'filled_results',now=now)
        self.assertEqual(result['completed_human_reviews'],len(rows))
        self.assertEqual(result['total_unique_review_minutes'],len(rows)*3)
        for model in result['metrics']:
            self.assertEqual(model['reviewed'],5);self.assertEqual(model['full_budget_review_minutes'],15)
            self.assertEqual(model['unreviewed'],0)
            self.assertEqual(model['unknown']+model['useful'],5)
        self.assertLessEqual(result['total_unique_review_minutes'],sum(m['full_budget_review_minutes'] for m in result['metrics']))
        self.assertIsNone(result['business_winner'])

    def test_partial_reviews_do_not_report_full_budget_benefit(self):
        out,_=self.run_comparison(algorithms=['ecod']);reviews,rows,now=self.filled_reviews(out)
        with reviews.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=REVIEW_FIELDS);writer.writeheader();writer.writerow(rows[0])
        result=collect(out,reviews,self.root/'partial_results',now=now)
        self.assertEqual(result['completed_human_reviews'],1)
        self.assertTrue(all(m['full_budget_review_minutes'] is None and m['useful_at_budget'] is None for m in result['metrics']))

    def test_invalid_or_foreign_or_duplicate_review_and_tampered_evidence_rejected(self):
        out,_=self.run_comparison(algorithms=['ecod'])
        for changes in (dict(human_verified='0'),dict(active_review_minutes='nan'),dict(active_review_minutes='0'),
                        dict(timing_method='estimated'),dict(useful='yes',business_action=''),dict(company_id='C999'),
                        dict(reviewed_at='2024-01-01T00:00:00+07:00')):
            reviews,_,now=self.filled_reviews(out,**changes)
            with self.assertRaises(ValueError):collect(out,reviews,self.root/'invalid_results',now=now)
        reviews,rows,now=self.filled_reviews(out)
        with reviews.open('a',encoding='utf-8',newline='') as stream:csv.DictWriter(stream,fieldnames=REVIEW_FIELDS).writerow(rows[0])
        with self.assertRaises(ValueError):collect(out,reviews,self.root/'invalid_results',now=now)
        next((out/'public/evidence').glob('*.json')).write_text('{}')
        with self.assertRaises(ValueError):collect(out,out/'human_reviews.csv',self.root/'invalid_results')


if __name__=='__main__':unittest.main()
