"""RR09 policy boundaries and real queue/store/notification integration."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sme_fraud.case_admission import admission
from sme_fraud.case_queue import review_queue
from sme_fraud.cash_limit_priority import POLICY, limit_priority
from sme_fraud.generate import write_csv
from sme_fraud.notifications import Notifications
from sme_fraud.review_store import ReviewStore
import test_cash_controls as cash_tests
from test_review import make_fixture


class RR09PriorityTest(unittest.TestCase):
    def result(self, amount=2_000_001, limit=2_000_000, config=None, **values):
        helper=cash_tests.CashControlsTest()
        c=helper.case(); helper.verified_limit(c)
        c.config['cash_limit_vnd_by_company']['C001']=limit
        c.config['cash_limit_evidence_by_company']['C001']['limit_vnd']=limit
        c.config.update(config or {})
        helper.pay(c,amount,**values)
        r=c.score()
        return c,r,helper.hit(r)

    def test_one_dong_stays_admitted_with_14_points_but_low_handling_priority(self):
        c,r,h=self.result()
        self.assertEqual((h['points'],r['scores'][0]['priority'],r['scores'][0]['operational_alert']),(14,'thap',1))
        q,_=review_queue(r,c.tables)
        self.assertEqual((len(q),q[0]['max_score'],q[0]['priority']),(1,14,'thap'))
        self.assertEqual(h['evidence']['limit_priority']['excess_vnd'],1)
        self.assertIn('invoice_identity',h['evidence']['missing_fields'])
        self.assertEqual(h['evidence']['limit_priority']['version'],POLICY)
        self.assertEqual(datetime.fromisoformat(q[0]['sla_due_at'])-datetime.fromisoformat(q[0]['opened_at']),timedelta(hours=720))

    def test_at_and_below_limit_have_no_verified_breach(self):
        for amount in (1_999_999,2_000_000):
            with self.subTest(amount=amount):
                _,r,h=self.result(amount)
                self.assertIsNone(h)
                self.assertFalse(r['scores'][0]['operational_alert'])

    def test_ratio_boundaries_use_unrounded_integer_arithmetic(self):
        for amount,priority in ((2_019_999,'thap'),(2_020_000,'trung_binh'),(2_199_999,'trung_binh'),(2_200_000,'cao')):
            with self.subTest(amount=amount):
                c,r,h=self.result(amount)
                self.assertEqual(r['scores'][0]['priority'],priority)
                self.assertEqual(h['evidence']['limit_priority']['tier_priority'],priority)
                q,_=review_queue(r,c.tables)
                hours={'thap':720,'trung_binh':168,'cao':48}[priority]
                self.assertEqual(datetime.fromisoformat(q[0]['sla_due_at'])-datetime.fromisoformat(q[0]['opened_at']),timedelta(hours=hours))

    def test_absolute_boundaries_and_or_combination(self):
        for excess,priority in ((99_999,'thap'),(100_000,'trung_binh'),(999_999,'trung_binh'),(1_000_000,'cao')):
            with self.subTest(excess=excess):
                _,r,h=self.result(100_000_000+excess,100_000_000)
                self.assertEqual(h['evidence']['limit_priority']['tier_priority'],priority)
                self.assertEqual(r['scores'][0]['priority'],priority)
        self.assertEqual(limit_priority(11,10)['tier_priority'],'cao')
        self.assertEqual(limit_priority(10**15+1,10**15)['tier_priority'],'thap')

    def test_zero_limit_positive_payment_is_high_and_ratio_not_applicable(self):
        _,r,h=self.result(1,0)
        self.assertEqual(r['scores'][0]['priority'],'cao')
        self.assertIsNone(h['evidence']['limit_priority']['excess_ratio'])

    def test_vat_document_branch_retains_medium_floor_without_adding_eight_points(self):
        c,r,h=self.result(10_000_001,10_000_000,invoice_id='INV',invoice_number='A',
                          invoice_issued_at='2025-08-12T11:00:00+07:00',invoice_gross_vnd=10_000_001)
        self.assertEqual(h['evidence']['limit_priority']['tier_priority'],'thap')
        self.assertEqual((h['points'],h['evidence']['review_priority'],r['scores'][0]['priority']),(14,'trung_binh','trung_binh'))

    def test_non_vnd_is_information_request_without_a_tier(self):
        _,r,h=self.result(currency='USD')
        self.assertEqual(h['points'],0)
        self.assertNotIn('limit_priority',h['evidence'])
        self.assertFalse(r['scores'][0]['operational_alert'])

    def test_limit_requires_same_company_known_verification_and_validity(self):
        changes=[{'verified_at':'2026-01-01T00:00:00+07:00'},
                 {'effective_from':'2026-01-01T00:00:00+07:00'},
                 {'effective_to':'2025-08-12T11:00:00+07:00'}]
        for change in changes:
            c,_,_=self.result()
            c.config['cash_limit_evidence_by_company']['C001'].update(change)
            h=cash_tests.CashControlsTest().hit(c.score())
            self.assertNotIn('limit_priority',h['evidence']);self.assertEqual(h['points'],0)
        _,r,h=self.result(config={'cash_limit_evidence_by_company':{}})
        self.assertNotIn('limit_priority',h['evidence']);self.assertEqual(h['points'],0)
        c,_,_=self.result()
        record=c.config['cash_limit_evidence_by_company'].pop('C001')
        c.config['cash_limit_evidence_by_company']['OTHER']=record
        c.config['cash_limit_vnd_by_company']['OTHER']=2_000_000
        self.assertEqual(cash_tests.CashControlsTest().hit(c.score())['points'],0)

    def hit(self,code,points,**values):
        return dict(rule_id=code,points=points,hard_trigger=0,**values)

    def test_independent_family_scores_and_hard_rules_can_raise_priority(self):
        c,r,p2=self.result()
        for extra,total,hard,expected in (([self.hit('B2',8)],22,False,'trung_binh'),
                    ([self.hit('B2',8),self.hit('F2',8)],30,False,'cao'),
                    ([self.hit('P1',20)],20,True,'cao_nhat')):
            with self.subTest(expected=expected):
                result=admission([p2,*extra],total,hard,c.config)
                self.assertEqual(result['priority'],expected)

    def test_recurrence_is_preserved_without_restoring_p2_fourteen_points(self):
        c,r,p2=self.result()
        out=admission([p2],17,False,c.config)
        self.assertEqual((out['priority'],out['independent_rule_score']),('thap',3))
        out=admission([p2,self.hit('B2',8),self.hit('F2',3)],28,False,c.config)
        self.assertEqual((out['priority'],out['independent_rule_score']),('cao',14))

    def test_verified_breach_admission_survives_custom_numeric_threshold(self):
        _,r,_=self.result(config={'operational_score':100})
        self.assertEqual((r['scores'][0]['operational_alert'],r['scores'][0]['priority']),(1,'thap'))

    def test_legacy_replay_and_invalid_policy(self):
        _,r,h=self.result(config={'cash_limit_priority_policy':'legacy_high_v1'})
        self.assertEqual(r['scores'][0]['priority'],'cao')
        self.assertNotIn('limit_priority',h['evidence'])
        with self.assertRaises(ValueError):self.result(config={'cash_limit_priority_policy':'guess'})

    def test_approved_recurring_pattern_does_not_waive_verified_cash_breach(self):
        c,_,_=self.result()
        c.tables['recurring_payments'].append(dict(pattern_id='RR09_RECUR',company_id='C001',
            vendor_id=c.rows[0]['vendor_id'],employee_id='',txn_type='cash_expense',contract_id='',invoice_number='',
            frequency='monthly',expected_amount_vnd=2_000_001,tolerance_vnd=0,
            effective_from='2025-01-01',effective_to='2025-12-31',status='approved',evidence_on_file=1,
            evidence_id='RR09_RECUR_EVIDENCE',approver_id=c.director['employee_id'],
            approved_at='2025-01-01T09:00:00+07:00',observed_at='2025-01-01T10:00:00+07:00'))
        result=c.score();p2=cash_tests.CashControlsTest().hit(result)
        self.assertEqual((p2['points'],result['scores'][0]['operational_alert'],result['scores'][0]['priority']),(14,1,'thap'))

    def test_oct18_control_declarations_pin_their_historical_priority_policy(self):
        from sme_fraud.p2_control_cases import build_control, declarations
        spec=next(r for r in declarations() if r['control_id']=='LIMIT_VERIFIED')
        _,config=build_control(spec)
        self.assertEqual(config['cash_limit_priority_policy'],'legacy_high_v1')

    def test_current_queue_escalation_uses_priority_not_the_unchanged_score(self):
        c,r,h=self.result()
        c.pay(c.at+timedelta(days=1),2_200_000,kind='cash_expense')
        q,events=review_queue(c.score(),c.tables)
        self.assertEqual(len(q),1);self.assertEqual(q[0]['priority'],'cao')
        self.assertTrue(any(e['event']=='escalated' and e['priority']=='cao' for e in events))
        self.assertEqual(datetime.fromisoformat(q[0]['sla_due_at'])-datetime.fromisoformat(q[0]['opened_at']),timedelta(hours=48))

    def test_store_selector_and_notifications_use_the_computed_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data,report=make_fixture(root)
            with (report/'case_queue.csv').open(encoding='utf-8-sig',newline='') as stream:templates=list(csv.DictReader(stream))
            cases=[]
            for index,(amount,score,priority) in enumerate(((2_000_001,14,'thap'),(2_020_000,14,'trung_binh'),(2_200_000,14,'cao')),1):
                c,r,h=self.result(amount);q,_=review_queue(r,c.tables)
                cases.append(dict(templates[index-1],priority=q[0]['priority'],max_score=q[0]['max_score'],rule_ids='P2'))
            write_csv(report/'case_queue.csv',cases)
            store=ReviewStore(root/'data',root/'reports',root/'review.sqlite3',clock=lambda:datetime.fromisoformat('2026-10-18T09:00:00+07:00'))
            store.prepare()
            self.assertEqual([r['case_id'] for r in store.list_cases('003',company='C001',daily=True)['items']],['RC_3','RC_2','RC_1'])
            service=Notifications(store,dict(dry_run=True,replay_existing=True))
            service.plan('003')
            jobs=[j for j in service.status('003')['items'] if j['kind']=='high_priority']
            self.assertEqual({r['case_id'] for j in jobs for r in j['case_refs']},{'RC_3'})
            self.assertEqual(store.list_cases('003',priority='thap')['items'][0]['max_score'],14)


if __name__=='__main__':unittest.main()
