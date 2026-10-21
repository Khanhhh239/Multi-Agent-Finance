"""Acceptance examples for the requested hard-rule library, independent of ML."""
from datetime import datetime, timedelta
import unittest

from sme_fraud.generate import TZ
from sme_fraud.rule_audit_cases import Case


class CoreRuleRequirementsTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        return case

    def hits(self, result, rule):
        return [h for h in result['hits'] if h['rule_id'] == rule]

    def test_after_hours_weekend_and_holiday_each_produce_c1_evidence(self):
        cases = (('after_hours', datetime(2025, 8, 12, 23, tzinfo=TZ)),
                 ('weekend', datetime(2025, 8, 17, 11, tzinfo=TZ)),
                 ('holiday', datetime(2025, 9, 2, 11, tzinfo=TZ)))
        for label, at in cases:
            with self.subTest(label=label):
                case = self.case()
                case.pay(at, 100_000, created_at=at.isoformat())
                hits = self.hits(case.score(), 'C1')
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]['evidence']['created_outside'], 1)
                self.assertEqual(hits[0]['evidence']['approved_outside'], 1)
                # C1 is an independently detected context signal under the
                # established production scoring policy, not a fraud verdict.
                self.assertEqual(hits[0]['scoring_role'], 'context')

    def test_working_hours_and_authorized_saturday_do_not_produce_c1(self):
        for at in (datetime(2025, 8, 12, 11, tzinfo=TZ), datetime(2025, 8, 16, 11, tzinfo=TZ)):
            case = self.case()
            case.tables['companies'][0]['saturday_operations'] = 1
            case.pay(at, 100_000, created_at=at.isoformat())
            self.assertFalse(self.hits(case.score(), 'C1'))

    def test_custom_calendar_marks_a_2026_holiday_without_code_changes(self):
        case = self.case()
        at = datetime(2026, 9, 2, 11, tzinfo=TZ)
        case.tables['calendar'].append(dict(date='2026-09-02', is_holiday=1, source='synthetic_acceptance_calendar'))
        case.pay(at, 100_000, created_at=at.isoformat())
        self.assertTrue(self.hits(case.score(), 'C1'))

    def test_unauthorized_self_approval_triggers_c2_independently(self):
        case = self.case()
        case.pay(amount=int(case.maker['self_approval_limit_vnd'])+1,
                 approver_id=case.maker['employee_id'])
        result = case.score()
        hit = self.hits(result, 'C2')[0]
        self.assertEqual((hit['points'], hit['hard_trigger']), (20, 1))
        self.assertEqual(result['scores'][0]['operational_alert'], 1)

    def test_approved_self_approval_keeps_auditable_exception(self):
        case = self.case()
        case.pay(amount=int(case.maker['self_approval_limit_vnd']),
                 approver_id=case.maker['employee_id'])
        hit = self.hits(case.score(), 'C2')[0]
        self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0))
        self.assertTrue(hit['suppressed_reason'])

    def test_near_authority_chain_across_vendors_is_reviewed_without_ml(self):
        case = self.case()
        for index, vendor in enumerate(case.tables['vendors'][12:15]):
            case.pay(case.at+timedelta(days=7*index), 17_000_000, vendor=vendor,
                     invoice_number=f'INDEPENDENT_{index}')
        result = case.score()
        hits = self.hits(result, 'A4')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['evidence']['count'], 3)
        self.assertEqual(result['scores'][-1]['operational_alert'], 1)
