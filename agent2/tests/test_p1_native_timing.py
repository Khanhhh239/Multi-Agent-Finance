"""Regressions for P1-NATIVE-LATE-INVOICE over row and closed-batch paths."""
import copy
from datetime import timedelta,timezone
import unittest

from sme_fraud.rule_audit_cases import Case
from sme_fraud.generate import stamp
from sme_fraud.rules import score_rules
from sme_fraud.p1_timing import unavailable_fields


def prepared(amounts,days,**values):
    case=Case();rows=[]
    for amount,day in zip(amounts,days):
        rows.append(case.pay(case.at+timedelta(days=day),amount,invoice_number='TIMED-P1',invoice_gross_vnd=10_000_000,
            payment_channel='cash',credit_account='111',recipient_account='',
            **values))
    case.score();return case,rows


def p1(result,identity):return [h for h in result['hits'] if h['rule_id']=='P1' and h['transaction_id']==identity]
def score(case):return score_rules(case.tables,features=case.features)
def events(result):return [e for e in result['batch_events'] if e['rule_id']=='P1']


class P1NativeTimingTests(unittest.TestCase):
    def assert_gap(self,result,row):
        hit,=p1(result,row['transaction_id'])
        self.assertEqual((hit['points'],hit['hard_trigger']),(0,0))
        self.assertEqual(hit['status'],'information_gap');self.assertIsNone(hit['signal'])
        self.assertEqual(hit['evidence']['evidence_status'],'information_gap')
        self.assertNotIn('invoice_gross_vnd',hit['evidence'])
        self.assertNotIn('cumulative_paid_vnd',hit['evidence'])

    def test_late_invoice_observation_is_a_gap_not_twenty_points(self):
        case,rows=prepared([4_000_000,7_000_000],[0,1])
        rows[-1]['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        self.assert_gap(score(case),rows[-1])

    def test_future_issue_date_blocks_even_when_observation_is_known(self):
        case,rows=prepared([4_000_000,7_000_000],[0,1])
        rows[-1].update(invoice_observed_at=rows[-1]['posted_at'],invoice_issued_at=stamp(case.at+timedelta(days=2)))
        self.assert_gap(score(case),rows[-1])

    def test_exact_cutoff_is_inclusive_and_one_second_late_is_not(self):
        case,rows=prepared([4_000_000,7_000_000],[0,1]);current=rows[-1]
        for offset,expected in ((0,20),(1,0)):
            current['invoice_observed_at']=stamp(case.at+timedelta(days=1,seconds=offset))
            result=score(case);self.assertEqual(sum(h['points'] for h in p1(result,current['transaction_id'])),expected)
            if offset:self.assert_gap(result,current)

    def test_timestamp_offsets_are_compared_as_instants(self):
        case,rows=prepared([4_000_000,7_000_000],[0,1]);current=rows[-1]
        at=case.at+timedelta(days=1)
        # Native wire schema requires canonical +07:00; exercise the helper's
        # instant comparison directly rather than sending invalid wire records.
        current['invoice_observed_at']=stamp(at.astimezone(timezone(timedelta(hours=14))))
        self.assertFalse(unavailable_fields(current,current['posted_at']))
        current['invoice_observed_at']=stamp((at+timedelta(seconds=1)).astimezone(timezone.utc))
        self.assertEqual(unavailable_fields(current,current['posted_at']),['invoice_observed_at'])

    def test_unavailable_historical_invoice_does_not_enter_current_total(self):
        case,rows=prepared([4_000_000,7_000_000,1_000_000],[0,1,5])
        rows[0]['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        result=score(case);self.assert_gap(result,rows[1])
        hit,=p1(result,rows[2]['transaction_id'])
        self.assertEqual((hit['points'],hit['evidence']['cumulative_paid_vnd']),(20,12_000_000))
        self.assertEqual(hit['related_transaction_ids'],[r['transaction_id'] for r in rows[:2]])

    def test_two_unknown_current_invoices_cannot_create_batch_risk(self):
        case,rows=prepared([6_000_000,6_000_000],[0,0])
        for row in rows:row['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        result=score(case)
        for row in rows:self.assert_gap(result,row)
        self.assertFalse(any(e['points']>0 for e in events(result)))

    def test_unavailable_history_makes_batch_gap_without_partial_risk_total(self):
        case,rows=prepared([4_000_000,4_000_000,4_000_000],[0,1,1])
        rows[0]['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        event,=events(score(case))
        self.assertEqual(event['status'],'information_gap');self.assertIsNone(event['signal']);self.assertEqual(event['points'],0)
        self.assertNotIn('cumulative_paid_vnd',event['evidence'])

    def test_known_batch_still_has_twenty_group_points_and_zero_row_points(self):
        case,rows=prepared([4_000_000,4_000_000,4_000_000],[0,1,1])
        for row in rows:row['invoice_observed_at']=row['posted_at']
        result=score(case);event,=events(result)
        self.assertEqual((event['points'],event['evidence']['cumulative_paid_vnd']),(20,12_000_000))
        self.assertTrue(all(not any(h['points']>0 for h in p1(result,row['transaction_id'])) for row in rows))

    def test_future_invoice_values_do_not_change_prior_P1_outputs(self):
        case,rows=prepared([6_000_000,6_000_000],[0,0])
        for row in rows:row['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        before=score(case)
        for row in rows:row['invoice_gross_vnd']=1
        after=score(case)
        self.assertEqual([h for h in before['hits'] if h['rule_id']=='P1'],[h for h in after['hits'] if h['rule_id']=='P1'])
        self.assertEqual(events(before),events(after))

    def test_later_transaction_does_not_rewrite_old_gap(self):
        case,rows=prepared([6_000_000,6_000_000],[0,1])
        for row in rows:row['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        before=copy.deepcopy(score(case));self.assert_gap(before,rows[-1])
        later=case.pay(case.at+timedelta(days=4),1_000_000,invoice_number='TIMED-P1',invoice_gross_vnd=10_000_000,
            payment_channel='cash',credit_account='111',recipient_account='',invoice_observed_at=stamp(case.at+timedelta(days=3)))
        case.score();after=score(case)
        self.assertEqual(p1(before,rows[-1]['transaction_id']),p1(after,rows[-1]['transaction_id']))
        self.assertEqual(p1(after,later['transaction_id'])[0]['points'],20)


if __name__=='__main__':unittest.main()
