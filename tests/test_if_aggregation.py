"""Audit the existing max policy without substituting a new ranking score."""
import copy
from datetime import date
import json
import unittest

import numpy as np

from sme_fraud.audit_if_aggregation import (analyze_units, collect_units, describe_case,
    max_reference, rank_average, score_pools, size_bin, size_correlation, stratified_correlation)


class IFAggregationTest(unittest.TestCase):
    def setUp(self):
        self.cutoff='2025-07-02T00:00:00+07:00'
        self.tx={}
        self.scores={}
        for tid,value,kind,day,company in [('a',.1,'vendor_payment','01','C1'),
                ('b',.4,'vendor_payment','01','C1'),('c',.9,'vendor_payment','01','C1'),
                ('p',.3,'payroll','01','C1'),('q',.7,'payroll','01','C1'),
                ('future',100.,'vendor_payment','03','C1'),('other',99.,'vendor_payment','01','C2')]:
            row=dict(transaction_id=tid,company_id=company,txn_type=kind,posted_at='2025-07-'+day+'T10:00:00+07:00')
            self.tx[tid]=row
            self.scores[tid]=dict(row,anomaly_score=str(value))

    def case(self, ids, **kwargs):
        values=[float(self.scores[t]['anomaly_score']) for t in ids if t in self.scores]
        full=len(values)==len(ids)
        case=dict(transaction_ids=json.dumps(ids),company_id='C1',priority='cao',case_id='CASE',
            production_scope_hash='scope',opened_at='2025-07-01T10:00:00+07:00',
            case_type='transaction',if_score=max(values) if full else None,
            if_coverage='full' if full else 'missing_or_partial')
        case.update(kwargs)
        return case

    def unit(self, ids, **kwargs):
        return describe_case(self.case(ids,**kwargs),self.cutoff,'001',self.tx,self.scores)

    def test_member_count_bins_and_exact_max(self):
        self.assertEqual([size_bin(n) for n in (1,2,3,4,5,8,9,24)],['1','2','3-4','3-4','5-8','5-8','9+','9+'])
        row=self.unit(['a','b','c'])
        self.assertEqual(row['member_count'],3)
        self.assertEqual(row['if_max'],.9)
        self.assertAlmostEqual(row['member_median'],.4)
        self.assertAlmostEqual(row['max_minus_member_median'],.5)

    def test_mixed_types_retain_exact_composition_and_winner_type(self):
        row=self.unit(['a','b','p'])
        self.assertEqual(row['txn_group'],'mixed')
        self.assertEqual(json.loads(row['txn_type_counts']),dict(payroll=1,vendor_payment=2))
        self.assertEqual(row['winner_type_signature'],'vendor_payment')

    def test_member_order_does_not_change_analysis_unit(self):
        self.assertEqual(self.unit(['a','b'])['unit_id'],self.unit(['b','a'])['unit_id'])
        self.assertNotEqual(self.unit(['a'])['unit_id'],self.unit(['a','b'])['unit_id'])

    def test_unknown_cross_company_future_duplicate_and_nonfinite_fail(self):
        for ids in (['unknown'],['other'],['future'],['a','a']):
            with self.subTest(ids=ids),self.assertRaises((ValueError,KeyError)):
                self.unit(ids)
        self.scores['a']['anomaly_score']='nan'
        with self.assertRaises(ValueError):
            self.unit(['a'])

    def test_existing_full_max_and_partial_policy_cannot_be_changed(self):
        with self.assertRaises(ValueError):
            self.unit(['a','b'],if_score=.25)
        self.scores.pop('b')
        row=self.unit(['a','b'])
        self.assertIsNone(row['if_max'])
        self.assertEqual(row['scored_members'],1)
        with self.assertRaises(ValueError):
            self.unit(['a','b'],if_score=.1)

    def test_no_duplicate_days_or_scope_variants_in_primary_population(self):
        c1=self.case(['a','b'])
        c2=self.case(['b','a'],production_scope_hash='scope2',priority='cao_nhat')
        snapshots=[dict(day=date(2025,7,1),cutoff=self.cutoff,cases=[c1]),
            dict(day=date(2025,7,2),cutoff='2025-07-03T00:00:00+07:00',cases=[c2])]
        units,selected=collect_units(snapshots,'001',self.tx,self.scores,[])
        self.assertEqual(len(units),1)
        self.assertEqual(units[0]['snapshot_occurrences'],2)
        self.assertEqual(units[0]['scope_variants'],2)
        self.assertEqual(units[0]['first_priority'],'cao')
        self.assertEqual(units[0]['first_cutoff_exclusive'],self.cutoff)
        self.assertEqual(selected,[])

    def test_reference_never_uses_future_or_other_company_scores(self):
        unit=self.unit(['a','b'])
        ref=max_reference(unit,score_pools(self.tx,self.scores),repetitions=5000,seed=1)
        self.assertEqual(json.loads(ref['reference_pool_sizes']),dict(vendor_payment=3))
        self.assertAlmostEqual(ref['reference_max_mean'],(.4+.9+.9)/3,delta=.012)
        self.assertGreater(ref['reference_max_uplift'],0)

    def test_reference_preserves_type_counts_and_samples_without_replacement(self):
        unit=self.unit(['a','b','c','p','q'])
        ref=max_reference(unit,score_pools(self.tx,self.scores),repetitions=100,seed=1)
        self.assertAlmostEqual(ref['reference_max_mean'],.9)
        self.assertAlmostEqual(ref['reference_max_simulation_se'],0)
        self.assertTrue(ref['reference_all_pools_exhausted'])

    def test_single_member_has_exactly_zero_mechanical_max_uplift(self):
        ref=max_reference(self.unit(['a']),score_pools(self.tx,self.scores),repetitions=100,seed=1)
        self.assertAlmostEqual(ref['reference_single_mean'],(.1+.4+.9)/3)
        self.assertEqual(ref['reference_max_uplift'],0)
        self.assertEqual(ref['reference_max_simulation_se'],0)

    def test_reference_is_deterministic_and_does_not_mutate_source(self):
        before=copy.deepcopy((self.tx,self.scores))
        args=dict(repetitions=100,seed=7)
        a=max_reference(self.unit(['a','p']),score_pools(self.tx,self.scores),**args)
        b=max_reference(self.unit(['p','a']),score_pools(self.tx,self.scores),**args)
        self.assertEqual(a,b)
        self.assertEqual(before,(self.tx,self.scores))

    def test_reference_cutoff_is_exclusive_and_sparse_pools_fail(self):
        unit=self.unit(['a'])
        unit['first_cutoff_exclusive']=self.tx['a']['posted_at']
        with self.assertRaises(ValueError):
            max_reference(unit,score_pools(self.tx,self.scores),repetitions=100,seed=1)
        with self.assertRaises(ValueError):
            max_reference(self.unit(['a']),score_pools(self.tx,self.scores),repetitions=10,seed=1)

    def test_average_tied_ranks_and_constant_size_are_explicit(self):
        np.testing.assert_array_equal(rank_average([2,1,2,4]),[2.5,1,2.5,4])
        self.assertIsNone(size_correlation([dict(member_count=1,if_max=v) for v in (1,2,3)]))

    def test_within_company_control_and_sparse_exclusions(self):
        rows=[dict(company=c,member_count=i,if_max=i+offset) for c,offset in [('A',0),('B',100)] for i in (1,2,3)]
        rows.append(dict(company='sparse',member_count=1,if_max=0))
        result=stratified_correlation(rows,('company',))
        self.assertAlmostEqual(result['rho'],1)
        self.assertEqual((result['included_units'],result['excluded_units'],result['included_strata']),(6,1,2))

    def test_analysis_reports_overlap_instead_of_treating_units_independent(self):
        rows=[self.unit(['a']),self.unit(['a','b']),self.unit(['p'])]
        summary,groups=analyze_units(rows,self.tx,self.scores,'001',repetitions=100,seed=1)
        self.assertEqual(summary['full_coverage_member_sets'],3)
        self.assertEqual(summary['member_sets_sharing_transactions'],2)
        self.assertEqual(summary['unique_evaluation_members'],3)
        self.assertTrue(any(r['dimension']=='company_id+txn_group' for r in groups))

    def test_selected_review_scope_must_match_frozen_max(self):
        c=self.case(['a','b'])
        snapshot=dict(day=date(2025,7,1),cutoff=self.cutoff,cases=[c])
        selected=dict(day='2025-07-01',case_id='CASE',case_scope_hash='scope',case_type='transaction',
            company_id='C1',if_coverage='full',member_count='2',if_score='.4',budget=5,arm='baseline',work_key='W',priority='cao')
        units, rows=collect_units([snapshot],'001',self.tx,self.scores,[selected])
        self.assertEqual(len(rows),1)
        selected['if_score']='.3'
        with self.assertRaises(ValueError):
            collect_units([snapshot],'001',self.tx,self.scores,[selected])


if __name__=='__main__':
    unittest.main()
