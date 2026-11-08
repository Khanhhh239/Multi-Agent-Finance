import copy
import json
import unittest

from test_compare_shadow import case,task,snapshots
from sme_fraud.compare_shadow import simulation
from sme_fraud.compare_if_discovery import (case_document_keys,document_key,lead_case,prepare_frames,
    select_mixed,simulate)
from sme_fraud.review_capacity import ReviewCapacity


class IFDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.tx={};self.scores={};self.rules={}
        for name in 'ABCDEFGHL':self.add(name)
        self.scores['L']['anomaly_score']='.95'

    def add(self,name,*,invoice='',at='2025-07-01T10:00:00+07:00',company='C001',score=.5,points=0):
        self.tx[name]=dict(transaction_id=name,company_id=company,posted_at=at,invoice_id=invoice,
            journal_document_id='JD_'+name,txn_type='vendor_payment')
        self.scores[name]=dict(self.tx[name],anomaly_score=str(score))
        self.rules[name]=dict(transaction_id=name,rule_score=str(points),hard_trigger='0',operational_alert='0')

    def frames(self,days,**kwargs):
        return prepare_frames(snapshots(days),self.tx,self.scores,self.rules,.8,'001',**kwargs)

    def run_trial(self,days,share=20,cost=20):
        snaps=snapshots(days)
        frozen=simulation(snaps,5)['selections']
        frames,audit,first=self.frames(days)
        return simulate(frames,frozen,self.tx,first,slots=5,share=share,if_minutes=cost),audit

    def lead(self,name='L'):
        lead=lead_case(self.tx[name],self.scores[name],self.rules[name],'001',0)
        lead['first_eligible_day']='2025-07-01'
        return lead

    def test_zero_allocation_exactly_reproduces_frozen_baseline(self):
        rows=[case(n,20-i) for i,n in enumerate('ABCDEFG')]
        result,_=self.run_trial([rows,rows,rows],share=0)
        self.assertTrue(result['summary']['zero_share_reproduces_frozen_baseline'])
        self.assertEqual(result['summary']['baseline_reviews'],7)
        self.assertEqual(result['summary']['if_document_reviews'],0)

    def test_if_opens_outside_baseline_and_charges_same_budget(self):
        rows=[case(n,20-i) for i,n in enumerate('ABCDEFG')]
        result,_=self.run_trial([rows,rows,rows])
        self.assertEqual(result['summary']['if_document_reviews'],1)
        first=result['daily'][0]
        self.assertEqual((first['selected_total'],first['selected_if'],first['selected_baseline']),(5,1,4))
        self.assertEqual(first['baseline_deferred_same_day'],1)
        self.assertLessEqual(first['estimated_minutes'],120)
        self.assertGreater(result['summary']['baseline_common_work_delayed'],0)
        self.assertIsNone(result['summary']['actionable_gain'])

    def test_hard_and_nontransaction_pins_survive_discovery(self):
        self.add('S')
        rows=[case('H',25,priority='cao_nhat'),case('S',0,kind='source',priority='cao')]+[case(n,15-i) for i,n in enumerate('ABCDEF')]
        result,_=self.run_trial([rows,rows])
        day=[r for r in result['selections'] if r['day']=='2025-07-01']
        self.assertTrue({'H','S'}<={r['case_id'] for r in day})
        self.assertEqual(result['summary']['mandatory_displacements'],0)

    def test_extra_pending_hard_work_precedes_if(self):
        hard=[task(case(n,25-i,priority='cao_nhat')) for i,n in enumerate('ABCDEF')]
        chosen=select_mixed(hard,ReviewCapacity.ui(5),[],[self.lead()],1,20)
        self.assertEqual(len(chosen),5)
        self.assertTrue(all(t['origin']=='baseline' for t in chosen))

    def test_if_does_not_fit_minutes_unused_quota_returns_to_baseline(self):
        pins=[task(case('A',25,priority='cao_nhat',minutes=80)),task(case('B',0,kind='source',minutes=25))]
        ordinary=task(case('C',10,minutes=15))
        chosen=select_mixed(pins+[ordinary],ReviewCapacity.ui(5),pins,[self.lead()],1,20)
        self.assertEqual(sum(t['minutes'] for t in chosen),120)
        self.assertEqual({t['case']['case_id'] for t in chosen},{'A','B','C'})

    def test_threshold_is_inclusive_with_no_below_threshold_fallback(self):
        self.scores['L']['anomaly_score']='.8'
        frames,audit,_=self.frames([[]])
        self.assertEqual(len(frames[0]['leads']),1)
        self.scores['L']['anomaly_score']='.79999'
        self.assertEqual(self.frames([[]])[0][0]['leads'],[])

    def test_future_transaction_is_not_visible_before_cutoff(self):
        self.tx['L']['posted_at']='2025-07-02T00:00:00+07:00'
        self.scores['L']['posted_at']=self.tx['L']['posted_at']
        frames,_,_=self.frames([[],[]])
        self.assertEqual(len(frames[0]['leads']),0)
        self.assertEqual(len(frames[1]['leads']),1)

    def test_existing_case_member_and_same_document_are_not_novel(self):
        self.tx['A']['invoice_id']='INVOICE'
        self.tx['L']['invoice_id']='INVOICE'
        frames,audit,_=self.frames([[case('A')]])
        self.assertEqual(frames[0]['leads'],[])
        self.assertFalse(next(r for r in audit if r['transaction_id']=='L')['first_eligible_cutoff'])

    def test_pattern_context_and_invoice_source_scope_block_rediscovery(self):
        self.tx['L']['invoice_id']='INVOICE'
        context=case('A',kind='pattern');context['pattern_context_ids']='["L"]'
        self.assertEqual(self.frames([[context]])[0][0]['leads'],[])
        source=case('SRC',kind='source');source['source_scope']='invoice:INVOICE'
        self.assertEqual(self.frames([[source]])[0][0]['leads'],[])

    def test_historical_positive_invoice_finding_blocks_even_resolved_scope(self):
        self.tx['L']['invoice_id']='INVOICE'
        finding=dict(scope='invoice:INVOICE',company_id='C001',signal=True,status='evaluated',cutoff_at='2025-06-01T00:00:00+07:00')
        self.assertEqual(self.frames([[]],findings=[finding])[0][0]['leads'],[])

    def test_one_highest_transaction_per_document_and_no_repeated_review(self):
        self.tx['L']['invoice_id']='INVOICE'
        self.add('M',invoice='INVOICE',score=.99)
        result,_=self.run_trial([[],[],[]])
        selected=[r for r in result['selections'] if r['origin']=='if_only']
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['lead_transaction_id'],'M')

    def test_later_baseline_admission_is_annotated_without_lookahead_or_free_completion(self):
        later=case('L',15,if_score=.95)
        result,audit=self.run_trial([[],[later],[later]])
        rows=result['selections']
        self.assertEqual(rows[0]['origin'],'if_only')
        self.assertEqual(rows[0]['day'],'2025-07-01')
        self.assertEqual(result['summary']['if_later_admitted_by_baseline'],1)
        self.assertEqual(result['summary']['baseline_reviews_with_earlier_if_documents'],1)
        self.assertEqual(result['summary']['baseline_reviews'],1)
        self.assertEqual(result['summary']['estimated_minutes'],40)

    def test_weak_transaction_points_are_not_claimed_as_zero_signal(self):
        self.rules['L']['rule_score']='3'
        result,_=self.run_trial([[]])
        self.assertEqual(result['summary']['if_weak_transaction_signal_reviews'],1)
        self.assertEqual(result['summary']['if_zero_transaction_point_reviews'],0)

    def test_zero_point_context_is_disclosed_and_future_context_not_used(self):
        hits=[dict(transaction_id='L',detected_at='2025-07-01T11:00:00+07:00',points=0),
              dict(transaction_id='L',detected_at='2025-07-03T11:00:00+07:00',points=0)]
        frames,_,_=self.frames([[]],hits=hits)
        self.assertEqual(frames[0]['leads'][0]['context_only_hits'],1)
        self.assertEqual(frames[0]['leads'][0]['baseline_signal_class'],'zero_transaction_points')

    def test_score_mismatch_nonfinite_and_future_context_case_fail(self):
        for value in ('nan','inf'):
            self.scores['L']['anomaly_score']=value
            with self.assertRaises(ValueError):self.frames([[]])
        self.scores['L']['anomaly_score']='.95';self.scores['L']['company_id']='C002'
        with self.assertRaises(ValueError):self.frames([[]])
        self.scores['L']['company_id']='C001'
        self.tx['L']['posted_at']='2025-07-03T00:00:00+07:00';self.scores['L']['posted_at']=self.tx['L']['posted_at']
        c=case('A',kind='pattern');c['pattern_context_ids']='["L"]'
        with self.assertRaises(ValueError):self.frames([[c]])

    def test_document_key_order_company_scope_and_inputs_not_mutated(self):
        self.tx['L']['invoice_id']='I'
        self.assertEqual(document_key(self.tx['L']),('C001','invoice_id:I'))
        before=copy.deepcopy((self.tx,self.scores,self.rules))
        self.run_trial([[],[]])
        self.assertEqual(before,(self.tx,self.scores,self.rules))


if __name__=='__main__':
    unittest.main()
