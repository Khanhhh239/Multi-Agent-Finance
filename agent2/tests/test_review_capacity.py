"""Slot/minute and working-day parity through the real admission transaction."""
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.evidence_evaluation import budget_review
from sme_fraud.generate import parse
from sme_fraud.review_capacity import ReviewCalendar, ReviewCapacity, workload_scenarios
from sme_fraud.review_store import ReviewStore


def case(identity, minutes=45, company='C001', day='2025-09-01'):
    return dict(case_id=identity, company_id=company, case_type='transaction',
                opened_at=day+'T10:00:00+07:00', priority='cao_nhat', max_score=20,
                transaction_ids=[], estimated_minutes=minutes)


def history(cases):
    return [dict(case_id=row['case_id'], event='opened', event_at=row['opened_at'],
                 rule_score=row['max_score'], priority=row['priority']) for row in cases]


def simulate(cases, slots=5, minutes=120, **kwargs):
    return budget_review(cases, history(cases), {}, {}, slots, capacity_minutes=minutes, **kwargs)


class ReviewCapacityTest(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).resolve().parents[1]
        self.temp = tempfile.TemporaryDirectory(dir=self.workspace/'.runtime')
        self.root = Path(self.temp.name)
        self.when = [parse('2025-09-01T17:00:00+07:00')]
        self.counter = 0

    def tearDown(self):
        assert self.root.resolve().is_relative_to(self.workspace.resolve())
        self.temp.cleanup()

    def store(self, cases, slots=5, calendar=None):
        self.counter += 1
        store = ReviewStore(self.root/'data', self.root/'reports', self.root/f'probe_{self.counter}.sqlite3',
                            scenarios=['003'], clock=lambda: self.when[0], calendar=calendar)
        # Capacity fixture: empty feedback/aliases, actual schema/SQL/admit logic.
        store.feedback_state = lambda scenario: ({}, [])
        store.identity_state = lambda scenario: dict(aliases={})
        store.set_budget(slots)
        with store.connection() as db:
            for row in cases:
                db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?)',
                    ('003', row['case_id'], row['company_id'], 3, row['max_score'], row['opened_at'], json.dumps(row)))
        return store

    def actual_initial_admissions(self, store, cases, start, days):
        output, done = [], set()
        for offset in range(days):
            self.when[0] = parse(start+'T17:00:00+07:00')+timedelta(days=offset)
            for row in sorted(cases, key=lambda row: row['case_id']):
                if row['case_id'] in done or row['opened_at'] > self.when[0].isoformat():
                    continue
                try:
                    item = store.admit('003', row['case_id'])
                except OverflowError:
                    continue
                done.add(row['case_id'])
                output.append((row['case_id'], item['day'], item['work_minutes']))
        return output

    def assert_api_parity(self, cases, slots, calendar=None, period_end='2025-09-01', days=4):
        limits = ReviewCapacity.ui(slots)
        store = self.store(cases, slots, calendar)
        result = simulate(cases, slots, limits.minutes, calendar=calendar, period_end=period_end)
        expected = [(row['case_id'], row['day'], row['estimated_minutes']) for row in result['admissions']]
        actual = self.actual_initial_admissions(store, cases, cases[0]['opened_at'][:10], days)
        self.assertEqual(actual, expected)
        return result

    def test_five_45_minute_cases_match_ui_120_minutes_over_three_days(self):
        result = self.assert_api_parity([case(f'A{i}') for i in range(5)], 5)
        self.assertEqual(Counter(row['day'] for row in result['admissions']),
                         {'2025-09-01': 2, '2025-09-02': 2, '2025-09-03': 1})
        self.assertEqual(result['backlog_at_period_end_work_items'], 3)
        self.assertEqual(result['backlog_at_period_end_minutes'], 135)
        self.assertEqual(result['drain_calendar_days'], 2)
        self.assertEqual(result['backlog_end_work_items'], 0)

    def test_ten_slot_ui_profile_uses_240_minutes(self):
        result = self.assert_api_parity([case(f'A{i}') for i in range(7)], 10)
        self.assertEqual(result['reviewed_within_period'], 5)
        self.assertEqual(result['reviewed_after_period'], 2)
        self.assertEqual(result['capacity_minutes_per_company_day'], 240)

    def test_small_later_item_can_fill_remaining_minutes_like_api(self):
        cases = [case(letter, minutes) for letter, minutes in zip('ABCDE', (35, 45, 45, 20, 15))]
        result = self.assert_api_parity(cases, 5)
        self.assertEqual([row['case_id'] for row in result['admissions'][:4]], ['A', 'B', 'D', 'E'])

    def test_limits_reset_independently_per_company_and_day(self):
        cases = [case(f'{company}_{i}', company=company) for company in ('C001', 'C002') for i in range(3)]
        result = self.assert_api_parity(cases, 5)
        self.assertEqual(result['backlog_at_period_end_work_items'], 2)

    def test_case_slots_can_bind_before_minutes(self):
        result = simulate([case(str(i), 10) for i in range(4)], slots=1, minutes=120)
        self.assertEqual(max(Counter(row['day'] for row in result['admissions']).values()), 1)

    def test_weekend_and_explicit_closure_match_api_and_drain_date(self):
        calendar = ReviewCalendar(tuple(range(5)), ('2025-09-08',))
        cases = [case(f'A{i}', day='2025-09-05') for i in range(5)]
        result = self.assert_api_parity(cases, 5, calendar, period_end='2025-09-05', days=6)
        self.assertEqual(result['drain_completion_date'], '2025-09-10')
        self.assertEqual(result['drain_calendar_days'], 5)
        self.assertEqual({row['day'] for row in result['admissions']},
                         {'2025-09-05', '2025-09-09', '2025-09-10'})

    def test_nonworking_period_end_retains_backlog(self):
        result = simulate([case('A', day='2025-09-06')], calendar=ReviewCalendar(tuple(range(5))),
                          period_end='2025-09-07')
        self.assertEqual(result['backlog_at_period_end_work_items'], 1)
        self.assertEqual(result['reviewed_within_period'], 0)
        self.assertEqual(result['drain_completion_date'], '2025-09-08')

    def test_future_initial_and_scheduled_work_are_excluded_from_period_demand(self):
        earlier = case('A', 20)
        earlier.update(requires_rereview=1, rereview_due_at='2025-09-03T10:00:00+07:00')
        result = simulate([earlier, case('B', day='2025-09-02')], period_end='2025-09-01')
        self.assertEqual(result['total_cases'], 1)
        self.assertEqual(result['total_demand_work_items'], 1)
        self.assertEqual(result['excluded_cases_after_period'], 1)
        self.assertEqual(result['excluded_rereviews_after_period'], 1)
        self.assertEqual(result['total_demand_minutes'], 20)

    def test_oversized_work_stays_visible_without_infinite_drain(self):
        result = simulate([case('A', 60), case('B', 20)], minutes=30, period_end='2025-09-01')
        self.assertEqual(result['total_demand_minutes'], 80)
        self.assertEqual(result['backlog_at_period_end_work_items'], 1)
        self.assertEqual(result['backlog_end_work_items'], 1)
        self.assertIsNone(result['drain_completion_date'])
        self.assertEqual(result['unschedulable_work_items'][0]['case_id'], 'A')

    def test_bounded_drain_does_not_claim_empty_backlog(self):
        result = simulate([case(f'A{i}') for i in range(5)], period_end='2025-09-01', max_drain_days=1)
        self.assertTrue(result['drain_limit_reached'])
        self.assertEqual(result['backlog_end_work_items'], 1)
        self.assertIsNone(result['drain_calendar_days'])

    def test_initial_and_scheduled_review_do_not_use_two_same_day_slots(self):
        row = case('A', 20)
        row.update(requires_rereview=1, rereview_due_at='2025-09-01T12:00:00+07:00')
        result = simulate([row], period_end='2025-09-01')
        self.assertEqual([item['day'] for item in result['admissions']], ['2025-09-01', '2025-09-02'])
        self.assertEqual(result['rereview_work_items'], 1)

    def test_empty_period_is_explicit(self):
        result = simulate([], period_end='2025-09-30')
        self.assertEqual(result['backlog_at_period_end_work_items'], 0)
        self.assertEqual(result['drain_completion_date'], '2025-09-30')
        self.assertEqual(result['drain_calendar_days'], 0)

    def test_workload_only_replay_does_not_invent_fraud_precision(self):
        cases = [case('A', 20)]
        result = budget_review(cases, history(cases), {}, None, 5, capacity_minutes=120)
        self.assertFalse(result['diagnostic_labels_provided'])
        self.assertIsNone(result['precision'])
        self.assertIsNone(result['admissions'][0]['observed_fraud'])

    def test_configuration_rejects_invalid_numbers_and_calendar(self):
        for bad in (True, 0, -1, 5.0, '5', float('inf')):
            for args in ((bad, 120), (5, bad)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    ReviewCapacity(*args)
        for weekdays, holidays in (((), ()), ((True,), ()), ((7,), ()), ((0,), ('2025-02-30',))):
            with self.subTest(weekdays=weekdays, holidays=holidays), self.assertRaises(ValueError):
                ReviewCalendar(weekdays, holidays)
        for cutoff in ('20250901', '2025-09-01T00:00:00+07:00', True):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                simulate([], period_end=cutoff)

    def test_estimated_minutes_cannot_silently_truncate_or_be_zero(self):
        for bad in (True, 0, -1, 20.5, '20.5'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                simulate([case('A', bad)])
        self.assertEqual(simulate([case('A', '20')])['total_demand_minutes'], 20)

    def test_research_profiles_are_explicit_and_not_ui_profiles(self):
        scenarios = {name: (kind, limits) for name, kind, limits in workload_scenarios()}
        self.assertEqual(scenarios['ui_5_cases_120_minutes'], ('ui', ReviewCapacity.ui(5)))
        self.assertEqual(scenarios['research_5_cases_225_minutes'], ('research', ReviewCapacity(5, 225)))

    def test_ui_rejects_invalid_profile_and_preserves_idempotent_admission(self):
        row = case('A', 45)
        store = self.store([row])
        for bad in (True, 5.0, '5', 1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                store.set_budget(bad)
        first = store.admit('003', 'A')
        self.assertEqual(store.admit('003', 'A'), first)


if __name__ == '__main__':
    unittest.main()
