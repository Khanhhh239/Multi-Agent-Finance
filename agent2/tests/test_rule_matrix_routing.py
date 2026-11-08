"""Current default policy: predicates -> score -> admission -> real queue/SLA."""
import copy
import json
import unittest
from datetime import datetime, timedelta

from sme_fraud.case_queue import review_queue
from sme_fraud.evidence_cases import prepare, decision
from sme_fraud.features import build_features
from sme_fraud.generate import stamp
from sme_fraud.rules import score_rules
from rule_matrix_cases import ROUTING, positive_case, negative_case, target_hits


class RuleRoutingMatrixTest(unittest.TestCase):
    def test_source_information_gaps_keep_low_priority_rereview_and_sla(self):
        for code, variant in (('F3', 'missing_cancel_coverage'), ('F4', 'missing_coverage')):
            case, row, expected, scope = prepare(code, variant, 20261027)
            self.assertIsNone(expected)
            result = case.score()
            self.assertIsNone(decision(result, code, row, scope))
            queue, _ = review_queue(result, case.tables)
            bound = [q for q in queue if q.get('source_scope') == scope]
            self.assertEqual(len(bound), 1)
            item = bound[0]
            self.assertEqual((item['priority'], item['max_score'], item['requires_rereview']), ('thap', 0, 1))
            self.assertEqual(datetime.fromisoformat(item['sla_due_at']) - datetime.fromisoformat(item['opened_at']),
                             timedelta(hours=336))
            self.assertEqual(datetime.fromisoformat(item['rereview_due_at']) - datetime.fromisoformat(item['opened_at']),
                             timedelta(days=7))

    def test_p2_information_gap_keeps_zero_risk_and_low_priority_sla(self):
        from test_cash_controls import CashControlsTest
        helper = CashControlsTest()
        case = helper.case()
        row = helper.pay(case, 6_000_000)
        result = case.score()
        hit, = target_hits(result, row, 'P2')
        self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0))
        self.assertEqual(result['scores'][0]['operational_alert'], 0)
        queue, _ = review_queue(result, case.tables)
        item, = [q for q in queue if row['transaction_id'] in json.loads(q['transaction_ids'])]
        self.assertEqual((item['case_type'], item['priority'], item['max_score']), ('information_request', 'thap', 0))
        self.assertEqual(datetime.fromisoformat(item['sla_due_at']) - datetime.fromisoformat(item['opened_at']),
                         timedelta(hours=720))

    def check_transferred_maker(self, code):
        case, row, _ = positive_case(code)
        case.score()
        expanded = copy.deepcopy(case.tables)
        maker = next(e for e in expanded['employees'] if e['employee_id'] == row['creator_id'])
        expanded['employees'].append({**maker, 'recorded_at': row['posted_at'], 'company_id': 'C_OTHER'})
        with self.assertRaisesRegex(ValueError, 'cross-company maker'):
            score_rules(expanded, config=case.config, features=build_features(expanded))

    def check_negative(self, code):
        case, row, scope = negative_case(code)
        result = case.score()
        if scope == 'transaction':
            self.assertFalse(any(h.get('intrinsic_points', h['points']) > 0 and not h['suppressed_reason']
                                 for h in target_hits(result, row, code)), code)
        else:
            self.assertIs(decision(result, code, row, scope), False)
        queue, _ = review_queue(result, case.tables)
        self.assertFalse(any(code in q['rule_ids'].split('|') and
                             (row['transaction_id'] in json.loads(q['transaction_ids']) if scope == 'transaction'
                              else q.get('source_scope') == scope) for q in queue))

    def check_positive(self, code):
        case, row, scope = positive_case(code)
        result = case.score()
        if scope == 'transaction':
            hits = target_hits(result, row, code)
            self.assertTrue(hits, code)
            self.assertTrue(any(h.get('intrinsic_points', h['points']) > 0 for h in hits), code)
        else:
            self.assertIs(decision(result, code, row, scope), True)
        queue, events = review_queue(result, case.tables)
        expected_priority, expected_hours = ROUTING[code]
        bound = [q for q in queue if (scope == 'transaction' and row['transaction_id'] in json.loads(q['transaction_ids']))
                 or (scope != 'transaction' and q.get('source_scope') == scope and code in q['rule_ids'].split('|'))]
        score = next(s for s in result['scores'] if s['transaction_id'] == row['transaction_id'])
        if expected_priority is None:
            self.assertEqual(bound, [], code)
            self.assertEqual((score['operational_alert'], score['hard_trigger'], score['rule_score']), (0, 0, 0))
            self.assertTrue(all(h['points'] == 0 for h in hits))
        else:
            self.assertEqual(len(bound), 1, code)
            queued = bound[0]
            self.assertEqual(queued['priority'], expected_priority)
            self.assertEqual(datetime.fromisoformat(queued['sla_due_at']) - datetime.fromisoformat(queued['opened_at']),
                             timedelta(hours=expected_hours))
            self.assertEqual(sum(e['event'] == 'opened' and e['case_id'] == queued['case_id'] for e in events), 1)
            self.assertIn(code, queued['rule_ids'].split('|'))
            if scope == 'transaction':
                self.assertEqual(score['operational_alert'], 1)
                self.assertEqual(score['priority'], expected_priority)
            else:
                self.assertEqual((score['operational_alert'], score['rule_score']), (0, 0))
                self.assertEqual(queued['case_type'], 'source')
        all_members = [tid for q in queue for tid in json.loads(q['transaction_ids'])]
        self.assertEqual(len(all_members), len(set(all_members)), 'A transaction cannot occupy two queue cases')
        # Queue construction is read-only and repeatable.
        self.assertEqual((queue, events), review_queue(result, case.tables))

    def check_future_master(self, code):
        case, row, _ = positive_case(code)
        result = case.score()
        expanded = copy.deepcopy(case.tables)
        future = stamp(case.at + timedelta(days=40))
        for name, id_field in (('employees', 'employee_id'), ('vendors', 'vendor_id')):
            for record in list(expanded[name]):
                expanded[name].append({**record, 'recorded_at': future,
                    'phone': 'PHONE_SYN_MATRIX_FUTURE_' + record[id_field],
                    'address': 'MATRIX_FUTURE_ADDRESS_' + record[id_field],
                    'bank_account': 'BANK_SYN_MATRIX_FUTURE_' + record[id_field]})
        for record in list(expanded['advances']):
            expanded['advances'].append({**record, 'recorded_at': future, 'original_due_at': future})
        after = score_rules(expanded, config=case.config, features=build_features(expanded))
        self.assertEqual(result['scores'], after['scores'])
        self.assertEqual(result['hits'], after['hits'])
        self.assertEqual(review_queue(result, case.tables), review_queue(after, expanded))


def _positive(code):
    def test(self):
        self.check_positive(code)
    return test


def _future(code):
    def test(self):
        self.check_future_master(code)
    return test


def _negative(code):
    def test(self):
        self.check_negative(code)
    return test


def _transferred(code):
    def test(self):
        self.check_transferred_maker(code)
    return test


for _code in ROUTING:
    setattr(RuleRoutingMatrixTest, f'test_{_code}_negative_no_rule_admission', _negative(_code))
    setattr(RuleRoutingMatrixTest, f'test_{_code}_positive_priority_queue_sla', _positive(_code))
    setattr(RuleRoutingMatrixTest, f'test_{_code}_future_master_keeps_historical_results', _future(_code))
    setattr(RuleRoutingMatrixTest, f'test_{_code}_current_cross_company_maker_is_rejected', _transferred(_code))


if __name__ == '__main__':
    unittest.main()
