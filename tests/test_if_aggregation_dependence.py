import copy
import json
import unittest

from sme_fraud.audit_if_aggregation_dependence import dependence_profiles, profile_statistics


class AggregationDependenceTest(unittest.TestCase):
    def row(self, uid, case, members, **kwargs):
        row=dict(unit_id=uid,first_case_id=case,member_ids=json.dumps(members),member_count=len(members),
            cohort='001',company_id='C1',first_cutoff_exclusive='2025-07-02T00:00:00+07:00',
            first_priority='cao',if_coverage='full',size_bin='1' if len(members)==1 else '2',
            if_max=.5,actual_minus_reference=.01,txn_group='cash_expense')
        row.update(kwargs)
        return row

    def test_first_and_largest_sets_per_case_are_distinct_policies(self):
        rows=[self.row('A','case',['t1']),self.row('B','case',['t1','t2'],
            first_cutoff_exclusive='2025-08-02T00:00:00+07:00')]
        p=dependence_profiles(rows)
        self.assertEqual([r['unit_id'] for r in p['first_full_set_per_case']],['A'])
        self.assertEqual([r['unit_id'] for r in p['largest_full_set_per_case']],['B'])

    def test_transitive_overlap_across_case_ids_gets_one_representative(self):
        rows=[self.row('A','c1',['t1','t2']),self.row('B','c2',['t2','t3']),self.row('C','c3',['t3','t4']),
              self.row('D','c4',['t5'])]
        p=dependence_profiles(rows)
        picked=p['largest_full_set_per_transaction_overlap_component']
        self.assertEqual({r['unit_id'] for r in picked},{'C','D'})
        self.assertEqual(profile_statistics('disjoint',picked)['repeated_member_occurrences'],0)

    def test_overlap_namespaces_do_not_cross_cohort_or_company(self):
        rows=[self.row('A','case',['t1']),self.row('B','case',['t1'],cohort='003'),
              self.row('C','case',['t1'],company_id='C2')]
        p=dependence_profiles(rows)
        self.assertEqual(len(p['first_full_set_per_case']),3)
        self.assertEqual(len(p['largest_full_set_per_transaction_overlap_component']),3)

    def test_partial_and_pinned_sets_remain_separate(self):
        rows=[self.row('A','case',['t1'],if_coverage='missing_or_partial'),
              self.row('B','case',['t2'],first_priority='cao_nhat'),self.row('C','other',['t3'])]
        before=copy.deepcopy(rows)
        p=dependence_profiles(rows)
        self.assertEqual(len(p['all_full_member_sets']),2)
        self.assertEqual([r['unit_id'] for r in p['rerankable_first_appearance_sets']],['C'])
        self.assertEqual(before,rows)

    def test_empty_or_constant_size_has_no_invented_correlation(self):
        self.assertIsNone(profile_statistics('empty',[])['size_max_spearman'])
        rows=[self.row(str(i),str(i),[str(i)],if_max=i/10) for i in range(4)]
        self.assertIsNone(profile_statistics('singletons',rows)['size_max_spearman'])


if __name__=='__main__':
    unittest.main()
