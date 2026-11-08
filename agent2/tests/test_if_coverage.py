"""Scope exclusions must never hide a genuine evaluation data/score defect."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.audit_if_coverage import (case_audit, feature_status, member_audit,
    summarize, unique_index, verify_commitment)
from sme_fraud.audit_model_windows import partition_rows
from sme_fraud.feature_contract import sha


class IFCoverageTest(unittest.TestCase):
    def setUp(self):
        self.plan = dict(company_ids=['C1'], source_ref='test',
            train=dict(start_at='2024-01-01T00:00:00+07:00',end_at='2025-01-01T00:00:00+07:00'),
            calibration=dict(start_at='2025-01-01T00:00:00+07:00',end_at='2025-07-01T00:00:00+07:00'),
            evaluation=dict(start_at='2025-07-01T00:00:00+07:00',end_at='2026-01-01T00:00:00+07:00'))
        dates = [('T','2024-01-01'),('C','2025-01-01'),('E','2025-07-01'),('F','2025-07-03'),('O','2026-01-01')]
        self.tx = {t:dict(transaction_id=t, company_id='C1', posted_at=d+'T00:00:00+07:00') for t,d in dates}
        self.parts = unique_index(partition_rows(self.tx.values(),self.plan),'transaction_id')
        self.features = {t:'valid' for t in self.tx}
        self.scores = {t:dict(self.tx[t],run_id='RUN',anomaly_score='0.4') for t in ('E','F')}
        self.cutoff = '2025-07-02T00:00:00+07:00'

    def case(self, members, **kwargs):
        case = dict(transaction_ids=json.dumps(members), company_id='C1', case_type='transaction')
        case.update(kwargs)
        return case_audit(case,self.cutoff,self.tx,self.parts,self.features,self.scores,'RUN')

    def test_boundaries_are_start_inclusive_end_exclusive(self):
        self.assertEqual({t:r['partition'] for t,r in self.parts.items()},
                         dict(T='train',C='calibration',E='evaluation',F='evaluation',O='outside_time_windows'))
        self.assertEqual(self.case(['E'])[0]['coverage_reason'],'full_evaluation_scored')

    def test_history_only_missing_score_is_intentional(self):
        result,members = self.case(['T','C'])
        self.assertEqual(result['coverage_reason'],'historical_only_unscored')
        self.assertEqual(result['partition_signature'],'train+calibration')
        self.assertEqual(result['scored_members'],0)
        self.assertTrue(all(r['member_status']=='historical_exclusion' and not r['errors'] for r in members))

    def test_mixed_history_and_evaluation_is_partial_scope(self):
        result,_ = self.case(['C','E'])
        self.assertEqual(result['coverage_reason'],'mixed_history_evaluation')
        self.assertEqual((result['member_count'],result['scored_members']),(2,1))
        self.assertEqual(result['partition_signature'],'calibration+evaluation')

    def test_missing_evaluation_score_is_data_error(self):
        self.scores.pop('E')
        result,_ = self.case(['C','E'])
        self.assertEqual(result['coverage_reason'],'data_error')
        self.assertIn('evaluation_score_missing',result['errors'])

    def test_missing_feature_is_error_even_when_score_exists(self):
        self.features.pop('E')
        self.assertIn('feature_missing',self.case(['E'])[0]['errors'])

    def test_bad_historical_feature_does_not_hide_behind_scope_exclusion(self):
        self.features['T'] = 'nonfinite'
        result,_ = self.case(['T'])
        self.assertEqual(result['coverage_reason'],'data_error')
        self.assertIn('feature_nonfinite',result['errors'])

    def test_invalid_or_nonfinite_score_is_error(self):
        for value in ('nan','inf','-inf','bad',''):
            with self.subTest(value=value):
                self.scores['E']['anomaly_score'] = value
                self.assertEqual(self.case(['E'])[0]['coverage_reason'],'data_error')

    def test_score_must_bind_same_source_company_time_and_run(self):
        for field,value,expected in [('company_id','C2','score_source_mismatch'),
                ('posted_at','2025-07-01T01:00:00+07:00','score_source_mismatch'),
                ('run_id','OTHER','score_run_mismatch')]:
            original = copy.deepcopy(self.scores['E'])
            self.scores['E'][field] = value
            self.assertIn(expected,self.case(['E'])[0]['errors'])
            self.scores['E'] = original

    def test_score_for_train_or_calibration_is_leakage_error(self):
        self.scores['C'] = dict(self.tx['C'],run_id='RUN',anomaly_score='0.5')
        self.assertIn('score_outside_evaluation',self.case(['C','E'])[0]['errors'])

    def test_future_member_at_exact_cutoff_is_rejected(self):
        self.cutoff = self.tx['E']['posted_at']
        self.assertIn('future_member',self.case(['E'])[0]['errors'])

    def test_cross_company_unknown_and_duplicate_member_links_are_errors(self):
        self.assertIn('cross_company_member',self.case(['E'],company_id='C2')[0]['errors'])
        self.assertIn('unknown_transaction',self.case(['UNKNOWN'])[0]['errors'])
        self.assertIn('duplicate_member_link',self.case(['E','E'])[0]['errors'])

    def test_empty_and_malformed_members_cannot_count_as_full(self):
        self.assertIn('empty_transaction_case',self.case([])[0]['errors'])
        for value in ('E',[None],['']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.case(value)

    def test_nontransaction_is_outside_review_denominator(self):
        result, members = self.case([],case_type='source')
        self.assertEqual(result['coverage_reason'],'outside_transaction_scope')
        self.assertEqual(members,[])

    def test_other_scope_is_not_mislabelled_as_train_calibration(self):
        row = member_audit('O','C1',None,self.tx,self.parts,self.features,self.scores,'RUN')
        self.assertEqual(row['member_status'],'other_scope_exclusion')

    def test_denominators_count_review_work_and_separate_eligible_cases(self):
        rows=[]
        for i,members in enumerate((['T'],['C','E'],['E'],['E'])):
            result,_ = self.case(members)
            rows.append(dict(result,case_type='transaction',case_id='same' if i>1 else str(i),work_key=str(i)))
        rows.append(dict(case_type='source',coverage_reason='outside_transaction_scope'))
        s = summarize(rows)
        self.assertEqual((s['selected_work_reviews'],s['transaction_work_reviews'],s['full_if_coverage']),(5,4,2))
        self.assertEqual(s['missing_or_partial'],2)
        self.assertEqual(s['full_fraction'],.5)
        self.assertEqual(s['entirely_evaluation_full_fraction'],1)
        self.assertEqual(s['unique_transaction_case_ids'],3)

    def test_feature_validation_includes_float32_overflow_and_missing_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'features.csv'
            path.write_text('transaction_id,x\nT,0\nC,nan\nE,1e100\nF,text\nO,1,2\n',encoding='utf-8')
            self.assertEqual(feature_status(path,['x'],self.tx),
                dict(T='valid',C='nonfinite',E='nonfinite',F='nonnumeric',O='invalid_width'))
            path.write_text('transaction_id,x\nT,0\n',encoding='utf-8')
            statuses=feature_status(path,['x'],self.tx)
            self.assertEqual(statuses.get('E','missing'),'missing')

    def test_duplicate_or_orphan_features_and_wrong_header_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'features.csv'
            for text in ('transaction_id,y\nT,0\n','transaction_id,x\nT,0\nT,1\n',
                         'transaction_id,x\nORPHAN,0\n'):
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):
                    feature_status(path,['x'],self.tx)

    def test_duplicate_score_or_source_id_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            unique_index([self.tx['E'],self.tx['E']],'transaction_id')

    def test_frozen_commitment_detects_tampering_and_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'run';root.mkdir()
            path=root/'scores.csv';path.write_text('original')
            commitment=root/'predictions_frozen.json'
            commitment.write_text(json.dumps({'scores.csv':sha(path)}))
            self.assertIn(str(path.resolve()),verify_commitment(root))
            path.write_text('changed')
            with self.assertRaises(ValueError):
                verify_commitment(root)
            commitment.write_text(json.dumps({'../escape.csv':'0'*64}))
            with self.assertRaises(ValueError):
                verify_commitment(root)


if __name__ == '__main__':
    unittest.main()
