import json
import unittest
from sme_fraud.evidence_evaluation import boolean_metrics, budget_review


class EvidenceEvaluationTest(unittest.TestCase):
    def test_unknown_evidence_is_not_a_successful_negative(self):
        metric = boolean_metrics([dict(expected=True,actual=None),dict(expected=None,actual=None),dict(expected=False,actual=False)])
        self.assertEqual(metric['evaluable'],1)
        self.assertEqual(metric['missing_prediction'],1)
        self.assertEqual(metric['correct_unknown'],1)
        self.assertIsNone(metric['precision'])

    def test_budget_does_not_rank_by_future_case_priority_or_members(self):
        cases = [dict(case_id='A',company_id='C',max_score=99,transaction_ids=json.dumps(['normal','future'])),
                 dict(case_id='B',company_id='C',max_score=20,transaction_ids=json.dumps(['fraud']))]
        events = [dict(case_id='A',event='opened',event_at='2025-09-01T10:00:00+07:00',priority='trung_binh',rule_score=8),
                  dict(case_id='B',event='opened',event_at='2025-09-01T11:00:00+07:00',priority='cao_nhat',rule_score=20)]
        tx = dict(normal=dict(posted_at=events[0]['event_at']),fraud=dict(posted_at=events[1]['event_at']),future=dict(posted_at='2025-10-01T10:00:00+07:00'))
        labels = dict(normal=dict(is_fraud=0),fraud=dict(is_fraud=1),future=dict(is_fraud=1))
        result = budget_review(cases, events, tx, labels, 1, capacity_minutes=45)
        self.assertEqual(result['admissions'][0]['case_id'],'B')
        self.assertEqual(result['useful_cases'],1)


if __name__ == '__main__':
    unittest.main()
