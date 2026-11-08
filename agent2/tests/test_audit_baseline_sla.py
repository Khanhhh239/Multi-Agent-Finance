"""Eligibility clocks, independent capacity limits, inherited SLA and safe diagnostics."""
import copy
from datetime import date,timedelta
import unittest
from test_compare_shadow import case,snapshots
from sme_fraud.audit_baseline_sla import (scenarios,simulate,deadline_status,compare_reference,
                                         comparison,blocking_reason)
from sme_fraud.compare_shadow import simulation


def settings(name='baseline_5_120',**changes):
    return next(a for a in scenarios() if a['name']==name) | changes


def item(name,score=10,**kwargs):
    row=case(name,score,**kwargs)
    row['sla_due_at']='2025-07-08T10:00:00+07:00'
    return row


class BaselineSLATest(unittest.TestCase):
    def test_frozen_baseline_order_cost_and_wait_reproduce(self):
        rows=[item(str(i),20-i,minutes=45 if i<3 else 20) for i in range(7)]
        frames=snapshots([rows]*5);original=copy.deepcopy(frames)
        expected=[r for r in simulation(frames,5)['selections'] if r['arm']=='baseline']
        result=simulate(frames,[],settings())
        self.assertTrue(compare_reference(result,expected)['passed'])
        self.assertEqual(frames,original)

    def test_rereview_clock_does_not_equal_time_actually_eligible(self):
        source=item('LOW',1,kind='source',priority='thap')
        source.update(requires_rereview=1,rereview_due_at='2025-06-01T00:00:00+07:00')
        daily=[]
        for i in range(5):
            daily.append([source]+([item('HIGH'+str(i),20,priority='cao_nhat')] if i<3 else []))
        result=simulate(snapshots(daily),[source],settings(slots=1))
        rereview=next(r for r in result['selected'] if r['work_type']=='scheduled_rereview')
        self.assertEqual(rereview['wait_days'],4)
        self.assertEqual(rereview['pending_wait_days'],0)
        self.assertEqual(rereview['wait_clock_offset_days'],4)
        initial=next(r for r in result['selected'] if r['case_id']=='LOW' and r['work_type']=='initial_review')
        self.assertEqual(initial['pending_wait_days'],3)

    def test_capacity_reasons_distinguish_slots_minutes_and_both(self):
        for slots,minutes,cost,expected in ((1,120,20,'slots_only'),(5,100,60,'minutes_only'),(1,30,20,'both_limits')):
            with self.subTest(expected=expected):
                rows=[item('A',20,minutes=cost),item('B',10,minutes=cost)]
                result=simulate(snapshots([rows]),[],settings(slots=slots,minutes=minutes))
                self.assertEqual(result['blocked'][0]['reason'],expected)

    def test_nonfitting_task_does_not_hide_a_smaller_fitting_task(self):
        rows=[item('A',30,minutes=90),item('B',20,minutes=40),item('C',10,minutes=20)]
        result=simulate(snapshots([rows]),[],settings())
        self.assertEqual([r['case_id'] for r in result['selected']],['A','C'])
        self.assertEqual(result['daily'][0]['unused_minutes'],10)

    def test_sla_daily_interval_does_not_invent_completion_times(self):
        day=date(2025,7,1)
        self.assertEqual(deadline_status('2025-07-01T12:00:00+07:00',day),'same_day_uncertain')
        self.assertEqual(deadline_status('2025-07-02T00:00:00+07:00',day),'definitely_on_time')
        self.assertEqual(deadline_status('2025-06-30T23:59:59+07:00',day),'definitely_late')
        self.assertEqual(deadline_status('',day),'missing')

    def test_inherited_sla_debt_is_not_a_new_queue_breach(self):
        row=item('OLD');row.update(opened_at='2025-01-01T10:00:00+07:00',sla_due_at='2025-01-02T10:00:00+07:00')
        result=simulate(snapshots([[row]]),[row],settings())
        self.assertEqual(result['summary']['selected_deadline_already_due_before_window'],1)
        self.assertEqual(result['summary']['newly_definitely_late_selected'],0)
        self.assertEqual(result['selected'][0]['pending_wait_days'],0)

    def test_deadline_met_on_entry_can_become_newly_late(self):
        low=item('LOW',1);low['sla_due_at']='2025-07-01T12:00:00+07:00'
        high=item('HIGH',20)
        result=simulate(snapshots([[low,high],[low,high]]),[],settings(slots=1))
        self.assertEqual(result['summary']['newly_definitely_late_selected'],1)

    def test_unreviewed_end_work_is_censored_not_deleted(self):
        rows=[item('A',20),item('B',10)]
        result=simulate(snapshots([rows]),[],settings(slots=1))
        self.assertEqual(result['summary']['pending_at_end'],1)
        self.assertEqual(result['censored'][0]['case_id'],'B')
        self.assertEqual(result['censored'][0]['disposition'],'pending_at_end')

    def test_superseded_unselected_work_is_not_counted_reviewed(self):
        old=item('A',1);new=item('A',1,version='two');high=item('HIGH',20)
        result=simulate(snapshots([[old,high],[new,high]]),[],settings(slots=1))
        self.assertEqual(result['summary']['removed_scope_events']['superseded_unreviewed_scope_events'],1)
        self.assertEqual(result['summary']['dispositions']['superseded'],1)

    def test_off_queue_gap_reconciles_without_becoming_capacity_wait(self):
        old=item('LOW',1);new=item('LOW',1,version='two');high=item('H',20)
        result=simulate(snapshots([[old,high],[new,high],[old,high]]),[],settings(slots=1))
        last=next(r for r in result['selected'] if r['work_key']==old['base_work_key'])
        self.assertEqual((last['wait_days'],last['pending_wait_days'],last['off_queue_gap_days']),(2,1,1))

    def test_precleared_opening_includes_already_due_one_time_rereview(self):
        old=item('OLD',kind='source');old.update(requires_rereview=1,rereview_due_at='2025-06-01T00:00:00+07:00')
        result=simulate(snapshots([[old],[old]]),[old],settings('opening_precleared_5_120'))
        self.assertEqual(result['summary']['selected_work'],0)
        self.assertEqual(result['summary']['pending_at_end'],0)

    def test_unbounded_eliminates_resource_wait_not_legacy_rereview_clock_offset(self):
        old=item('OLD',kind='source');old.update(requires_rereview=1,rereview_due_at='2025-06-01T00:00:00+07:00')
        result=simulate(snapshots([[old],[old]]),[],settings('unbounded_diagnostic'))
        self.assertEqual(result['summary']['max_pending_wait_days'],0)
        self.assertEqual(result['summary']['reported_max_wait_days'],1)

    def test_pinned_order_does_not_drop_source_or_hard_work(self):
        hard=item('H',20,priority='cao_nhat');source=item('S',2,kind='source')
        tx=item('T',1);tx['sla_due_at']='2025-01-01T00:00:00+07:00'
        frames=snapshots([[hard,source,tx]]*2)
        baseline=simulate(frames,[],settings(slots=2))
        alternative=simulate(frames,[],settings('edf_priority_mandatory_pinned',slots=2),baseline['selected'])
        diff=comparison(baseline,alternative)
        self.assertEqual(diff['mandatory_reference'],dict(not_selected=0,selected_later=0))

    def test_future_reference_does_not_gate_current_pins(self):
        row=item('A');frames=snapshots([[row]])
        future=dict(day='2025-12-31',company_id='C001',priority='cao_nhat',case_type='transaction',work_key='FUTURE')
        plain=simulate(frames,[],settings('edf_priority_mandatory_pinned'))
        with_future=simulate(frames,[],settings('edf_priority_mandatory_pinned'),[future])
        self.assertEqual(plain,with_future)

    def test_weekend_queue_wait_is_distinct_from_capacity_failure(self):
        frames=snapshots([[item('A')]])
        frames[0]['day']=date(2025,7,5);frames[0]['cutoff']='2025-07-06T00:00:00+07:00'
        result=simulate(frames,[],settings('weekdays_5_120_diagnostic'))
        self.assertEqual(result['blocked'][0]['reason'],'non_working_day')
        self.assertEqual(result['summary']['selected_work'],0)

    def test_missing_evidence_parked_is_not_automatically_unreviewed_work(self):
        row=item('GAP',kind='information_request');row['source_status']='information_gap'
        result=simulate(snapshots([[row],[row]]),[],settings())
        self.assertEqual(result['summary']['pending_at_end'],0)
        self.assertEqual(result['summary']['awaiting_information_without_pending_review'],1)


if __name__=='__main__':unittest.main()
