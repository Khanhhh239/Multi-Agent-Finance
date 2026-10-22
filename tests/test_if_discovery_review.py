import copy
import unittest

from sme_fraud.if_discovery_review import key_for,select_disagreements,scope_for


class DiscoveryReviewTest(unittest.TestCase):
    def row(self,name,day='2025-07-01',**kwargs):
        row=dict(case_id=name,work_key=name,case_scope_hash='scope'+name,company_id='C001',arm='baseline',
            day=day,cutoff_exclusive=day+'T17:00:00+00:00',transaction_ids='["'+name+'"]',
            source_scope='',rule_ids='',case_type='transaction')
        row.update(kwargs)
        return row

    def test_census_both_sides_and_random_common_are_separate(self):
        a,b,c=self.row('A'),self.row('B'),self.row('C',origin='if_only',case_type='if_discovery')
        selected=select_disagreements([a,b],[dict(a,origin='baseline'),c],'001',{},7)
        groups={r['case_id']:r['sample_group'] for r in selected.values()}
        self.assertEqual(groups,dict(A='reference_common_selected',B='baseline_selection_disagreement',C='if_discovery_selected'))

    def test_retimed_baseline_scope_keeps_two_asof_review_units(self):
        before=self.row('A');after=self.row('A','2025-07-02',origin='baseline')
        selected=select_disagreements([before],[after],'001',{},7)
        self.assertEqual(len(selected),2)
        self.assertEqual({r['sample_group'] for r in selected.values()},{'baseline_selection_disagreement'})
        self.assertEqual({r['cutoff_exclusive'] for r in selected.values()},{before['cutoff_exclusive'],after['cutoff_exclusive']})

    def test_seeded_reference_is_order_invariant_and_source_rows_unchanged(self):
        rows=[self.row(n) for n in 'ABCDE']
        before=copy.deepcopy(rows)
        left=select_disagreements(rows,[dict(r,origin='baseline') for r in rows],'001',{},7)
        right=select_disagreements(list(reversed(rows)),[dict(r,origin='baseline') for r in reversed(rows)],'001',{},7)
        self.assertEqual(set(left),set(right))
        self.assertEqual(len(left),1)
        self.assertEqual(next(iter(left.values()))['stratum_population'],5)
        self.assertEqual(before,rows)

    def test_unit_identity_binds_cohort_and_normalizes_utc_offset(self):
        row=self.row('A');same=dict(row,cutoff_exclusive='2025-07-02T00:00:00+07:00')
        self.assertEqual(key_for(row,'001'),key_for(same,'001'))
        self.assertNotEqual(key_for(row,'001'),key_for(row,'003'))

    def test_source_clock_hash_drift_can_only_reuse_fixed_empty_member_object(self):
        row=self.row('S',case_type='source',case_scope_hash='later')
        scope=dict(row,case_scope_hash='earlier',transaction_ids='[]',source_scope='invoice:I',rule_ids='F4')
        mapped=scope_for(row,{('S','earlier'):scope})
        self.assertEqual(mapped['source_scope'],'invoice:I')
        self.assertEqual(row['case_scope_hash'],'later')

    def test_missing_transaction_scope_and_ambiguous_source_object_fail(self):
        with self.assertRaises(ValueError):scope_for(self.row('A'),{})
        row=self.row('S',case_type='source',case_scope_hash='later')
        a=dict(row,transaction_ids='[]',source_scope='invoice:I',rule_ids='F4')
        b=dict(a,source_scope='invoice:OTHER')
        with self.assertRaises(ValueError):scope_for(row,{('S','old'):a,('S','other'):b})


if __name__=='__main__':
    unittest.main()
