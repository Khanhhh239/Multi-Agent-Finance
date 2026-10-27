"""Causal reservation of baseline review days under the unchanged IF budget."""
import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from test_compare_shadow import case, task, snapshots
from sme_fraud.compare_shadow import simulation
from sme_fraud.compare_if_discovery import prepare_frames, simulate, select_mixed, delay_guard_limit
from sme_fraud.review_capacity import ReviewCapacity


class IFDelayGuardTest(unittest.TestCase):
    def study(self, *, days=28, slots=5, share=20, cost=20, guard=0, frozen_extra=()):
        transactions, scores, rules = {}, {}, {}

        def add(name, day, risk=10, minutes=20, kind='transaction', priority='trung_binh'):
            at=(date(2025, 7, 1)+timedelta(days=day)).isoformat()+'T10:00:00+07:00'
            transactions[name]=dict(transaction_id=name, company_id='C001', posted_at=at,
                                    invoice_id='', journal_document_id='JD_'+name, txn_type='vendor_payment')
            scores[name]=dict(transactions[name], anomaly_score='.95' if name=='LEAD' else '.5')
            rules[name]=dict(transaction_id=name, rule_score='0', hard_trigger='0', operational_alert='0')
            item=case(name, risk, minutes=minutes, kind=kind, priority=priority)
            item.update(opened_at=at, last_seen_at=at)
            return item

        initial=[add(name, 0, 20-i) for i, name in enumerate('ABCD')]
        initial.append(add('DELAYED', 0, 1))
        add('LEAD', 0)
        rows=list(initial)
        daily=[]
        for day in range(days):
            if 1 <= day <= 25:
                rows += [add(f'D{day}_{i}', day, 20-i) for i in range(5)]
            daily.append(list(rows))
        snaps=snapshots(daily)
        frozen=simulation(snaps,slots)['selections']
        frames,_,first=prepare_frames(snaps,transactions,scores,rules,.8,'001')
        original=copy.deepcopy((frames,frozen,transactions,first))
        result=simulate(frames,[*frozen,*frozen_extra],transactions,first,slots=slots,share=share,
                        if_minutes=cost,max_additional_baseline_days=guard)
        self.assertEqual(original,(frames,frozen,transactions,first))
        return result, frozen

    def test_legacy_control_reproduces_twenty_six_day_delay(self):
        result,_=self.study(guard=None)
        self.assertEqual(result['summary']['max_common_baseline_delay_days'],26)
        self.assertEqual(result['summary']['baseline_common_work_delayed'],1)

    def test_zero_day_guard_removes_delay_and_reduces_if_before_baseline(self):
        result,_=self.study()
        summary=result['summary']
        self.assertEqual(summary['max_common_baseline_delay_days'],0)
        self.assertEqual(summary['baseline_common_work_delayed'],0)
        self.assertEqual(summary['unmatched_frozen_historical_work'],0)
        first=result['daily'][0]
        self.assertEqual((first['selected_baseline'],first['selected_if']),(5,0))
        self.assertEqual(first['if_slot_cap_after_reservation'],0)
        self.assertEqual(first['if_reviews_removed_by_guard'],1)
        selected=next(r for r in result['selections'] if r['case_id']=='DELAYED')
        self.assertEqual(selected['day'],'2025-07-01')
        self.assertEqual(summary['budget_violations'],0)
        self.assertEqual(summary['mandatory_displacements'],0)

    def test_future_reference_rows_do_not_affect_a_finished_prefix(self):
        extra=dict(arm='baseline',day='2025-12-31',company_id='C001',work_key='FUTURE',
                   case_id='FUTURE',case_type='transaction',priority='cao_nhat',rank=1,estimated_minutes=20)
        plain,_=self.study(days=2)
        expanded,_=self.study(days=2,frozen_extra=[extra])
        self.assertEqual(plain,expanded)

    def test_zero_share_still_reproduces_baseline_exactly(self):
        result,frozen=self.study(share=0)
        expected=[(r['day'],r['work_key'],int(r['estimated_minutes'])) for r in frozen if r['arm']=='baseline']
        actual=[(r['day'],r['work_key'],r['estimated_minutes']) for r in result['selections']]
        self.assertEqual(actual,expected)
        self.assertEqual(result['summary']['if_document_reviews'],0)

    def test_five_and_ten_slot_budgets_and_if_costs_remain_unchanged(self):
        for slots in (5,10):
            for cost in (20,30):
                result,_=self.study(slots=slots,cost=cost)
                self.assertEqual(result['summary']['daily_minutes'],{5:120,10:240}[slots])
                for row in result['daily']:
                    self.assertLessEqual(row['selected_total'],slots)
                    self.assertLessEqual(row['estimated_minutes'],{5:120,10:240}[slots])
                self.assertEqual(result['summary']['max_common_baseline_delay_days'],0)

    def test_reservation_releases_if_capacity_when_slots_are_spare(self):
        ordinary=[task(case(name,20-i)) for i,name in enumerate('ABCD')]
        lead=dict(case_id='IF',company_id='C001',if_score=.99,opened_at='2025-07-01T10:00:00+07:00',
                  first_eligible_day='2025-07-01',base_work_key='IF_KEY')
        audit={}
        chosen=select_mixed(ordinary,ReviewCapacity.ui(5),[],[lead],1,20,protected=ordinary,audit=audit)
        self.assertEqual(sum(t['origin']=='if_only' for t in chosen),1)
        self.assertEqual(len(chosen),5)
        self.assertEqual(sum(t['minutes'] for t in chosen),100)
        self.assertEqual(audit['if_slot_cap_after_reservation'],1)

    def test_minutes_can_reduce_if_even_with_unused_case_slots(self):
        ordinary=[task(case(name,20-i,minutes=minutes)) for i,(name,minutes) in enumerate(zip('ABC',(45,45,20)))]
        lead=dict(case_id='IF',company_id='C001',if_score=.99,opened_at='2025-07-01T10:00:00+07:00',
                  first_eligible_day='2025-07-01',base_work_key='IF_KEY')
        audit={}
        chosen=select_mixed(ordinary,ReviewCapacity.ui(5),[],[lead],1,20,protected=ordinary,audit=audit)
        self.assertEqual(sum(t['origin']=='if_only' for t in chosen),0)
        self.assertEqual(audit['if_slot_cap_after_reservation'],0)
        self.assertEqual(sum(t['minutes'] for t in chosen),110)

    def test_reservation_deduplicates_mandatory_pins_and_keeps_every_one(self):
        hard=task(case('H',25,priority='cao_nhat'))
        source=task(case('S',0,kind='source'))
        ordinary=task(case('A',10))
        chosen=select_mixed([hard,source,ordinary],ReviewCapacity.ui(5),[hard,source],[],1,20,
                            protected=[hard,source,ordinary])
        self.assertEqual({t['key'] for t in chosen},{hard['key'],source['key'],ordinary['key']})
        self.assertEqual(len(chosen),3)

    def test_reservation_that_cannot_fit_fails_instead_of_breaking_budget(self):
        rows=[task(case(name,20-i,minutes=45)) for i,name in enumerate('ABC')]
        with self.assertRaisesRegex(ValueError,'reservation'):
            select_mixed(rows,ReviewCapacity.ui(5),[],[],1,20,protected=rows)

    def test_unsupported_delay_limits_are_not_silently_accepted(self):
        for guard in (-1,True,False,1,1.0,'0'):
            with self.subTest(guard=guard),self.assertRaises(ValueError):
                self.study(guard=guard)

    def test_unknown_current_reference_work_fails_closed(self):
        bad=dict(arm='baseline',day='2025-07-01',company_id='C001',work_key='UNKNOWN',
                 case_id='UNKNOWN',case_type='transaction',priority='trung_binh',rank=6,estimated_minutes=20)
        with self.assertRaisesRegex(ValueError,'absent'):
            self.study(days=2,frozen_extra=[bad])

    def test_changed_case_scope_is_reviewed_again_at_its_reference_day(self):
        import test_if_discovery as fixtures
        helper=fixtures.IFDiscoveryTest();helper.setUp()
        first=[case(name,20-i) for i,name in enumerate('ABCDE')]
        second=[case('A',20,version='two'),*first[1:]]
        snaps=snapshots([first,second,second])
        frozen=simulation(snaps,5)['selections']
        frames,_,initial=prepare_frames(snaps,helper.tx,helper.scores,helper.rules,.8,'001')
        result=simulate(frames,frozen,helper.tx,initial,slots=5,share=20,if_minutes=20,max_additional_baseline_days=0)
        reviews=[r for r in result['selections'] if r['case_id']=='A']
        self.assertEqual([r['estimated_minutes'] for r in reviews],[20,10])
        self.assertEqual(len({r['work_key'] for r in reviews}),2)
        self.assertEqual(result['summary']['max_common_baseline_delay_days'],0)

    def test_guarded_protocol_is_explicit_and_old_protocol_stays_legacy(self):
        root=Path(__file__).resolve().parents[1]/'examples/ml_if_discovery_shadow'
        current=json.loads((root/'delay_guard_protocol.json').read_text(encoding='utf-8'))
        old=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
        self.assertEqual(delay_guard_limit(current),0)
        self.assertIsNone(delay_guard_limit(old))
        for value in (False,True,1,-1,'0'):
            broken=copy.deepcopy(current)
            broken['baseline_delay_guard']['max_additional_days']=value
            with self.assertRaises(ValueError):delay_guard_limit(broken)
        old['baseline_delay_guard']=current['baseline_delay_guard']
        with self.assertRaises(ValueError):delay_guard_limit(old)

    def test_missing_or_ambiguous_guard_protocol_is_rejected(self):
        for settings in ({'version':'unknown'}, {'version':'if-discovery-shadow-v2'},
                         {'version':'if-discovery-shadow-v2','baseline_delay_guard':None}):
            with self.assertRaises(ValueError):delay_guard_limit(settings)


if __name__=='__main__':unittest.main()
