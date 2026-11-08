"""Predeclared source controls, randomized independently of detector outputs."""
import random
from datetime import datetime, timedelta

from .generate import Generator, TZ, stamp
from .rule_audit_cases import Case


class EvidenceCase(Case):
    def __init__(self, seed):
        self.g = Generator(0, 0, seed, 1)
        self.tables, self.rows = self.g.tables, []
        self.vendor, self.maker = self.tables['vendors'][12], self.tables['employees'][2]
        self.director, self.worker = self.tables['employees'][0], self.tables['employees'][10]
        self.tables['employees'] = [self.director, self.maker, self.worker]
        self.tables['vendors'] = self.tables['vendors'][12:15]
        ids = {e['employee_id'] for e in self.tables['employees']} | {v['vendor_id'] for v in self.tables['vendors']}
        self.tables['entity_links'] = [e for e in self.tables['entity_links'] if e['source_id'] in ids]
        self.at = datetime(2025, 9, 12, 11, tzinfo=TZ)
        self.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        self.rng = random.Random(seed)

    def approved(self, **values):
        return dict(company_id='C001', status='approved', evidence_on_file=1, evidence_id='CASE_APPROVAL',
            approver_id=self.director['employee_id'], approved_at=stamp(self.at-timedelta(days=7)),
            observed_at=stamp(self.at-timedelta(days=6)), **values)


def prepare(code, variant, seed):
    c = EvidenceCase(seed)
    expected, scope = True, 'transaction'
    if code == 'C4':
        row = c.pay()
        leave = c.approved(leave_id='LEAVE', employee_id=c.maker['employee_id'], starts_at=stamp(c.at-timedelta(days=2)), ends_at=stamp(c.at+timedelta(days=1)))
        c.tables['leave_periods'] = [leave]
        c.tables['system_actions'] = [dict(action_id='ACTION', company_id='C001', employee_id=c.maker['employee_id'],
            transaction_id=row['transaction_id'], action='maker', action_at=row['created_at'], observed_at=row['posted_at'], evidence_id='LOGIN_TRACE')]
        if variant == 'authorized':
            c.tables['leave_activity_authorizations'] = [c.approved(authorization_id='EXCEPTION', employee_id=c.maker['employee_id'], leave_id='LEAVE', action='maker',
                starts_at=leave['starts_at'], ends_at=leave['ends_at'])]
            expected = False
        elif variant == 'late_source':
            leave['observed_at'] = stamp(c.at+timedelta(days=1))
            expected = False
        elif variant == 'cancel_after_action':
            c.tables['leave_periods'].append({**leave, 'status': 'revoked', 'observed_at': row['approved_at']})
        elif variant == 'end_boundary':
            leave['ends_at'] = row['created_at']
            expected = False
    elif code == 'E2':
        row = c.pay(kind='payroll')
        termination = c.approved(employment_event_id='END', employee_id=c.worker['employee_id'], event_type='termination', effective_date='2025-08-31')
        c.tables['employment_events'] = [termination]
        settlement = c.approved(settlement_id='PAY', employee_id=c.worker['employee_id'], transaction_id=row['transaction_id'], payroll_period=row['payroll_period'],
            payment_kind='regular_salary', service_period_start='2025-09-01', service_period_end='2025-09-30', authorized_amount_vnd=row['amount_vnd'])
        c.tables['payroll_settlements'] = [settlement]
        if variant == 'final_payment':
            settlement.update(payment_kind='final_settlement', service_period_start='2025-08-01', service_period_end='2025-08-31')
            expected = False
        elif variant == 'missing_period':
            c.tables['payroll_settlements'] = []
            expected = None
        elif variant == 'rehire':
            c.tables['employment_events'].append(c.approved(employment_event_id='REHIRE', employee_id=c.worker['employee_id'], event_type='rehire', effective_date='2025-09-01'))
            expected = False
        elif variant == 'late_source':
            termination['observed_at'] = stamp(c.at+timedelta(days=1))
            expected = False
    elif code == 'F2':
        row = c.pay(amount=7_000_000+c.rng.randrange(100000), kind='cash_expense')
        policy = c.approved(workflow_policy_id='WF', control_id='SECOND_REVIEW', txn_type='cash_expense', required=1, allow_override=0,
            authorized_override_roles='director', override_max_vnd=20_000_000, effective_from='2025-01-01T00:00:00+07:00', effective_to='2025-12-31T23:59:59+07:00')
        c.tables['workflow_policies'] = [policy]
        c.tables['override_events'] = [dict(override_id='BYPASS', company_id='C001', transaction_id=row['transaction_id'], actor_id=c.maker['employee_id'],
            operation_at=row['created_at'], observed_at=row['posted_at'], control_id='SECOND_REVIEW', status='executed', normal_workflow_completed=0, evidence_id='WORKFLOW_TRACE')]
        if variant == 'authorized':
            policy.update(allow_override=1, authorized_override_roles=c.maker['role'])
            expected = False
        elif variant == 'completed':
            c.tables['override_events'][0]['normal_workflow_completed'] = 1
            expected = False
        elif variant == 'missing_policy':
            c.tables['workflow_policies'] = []
            expected = None
    elif code == 'F3':
        row = c.pay(kind='cash_expense', amount=1_000_000)
        c.tables['document_series'] = [c.approved(series_id='PAY_2025', fiscal_year=2025, document_type='payment', start_number=1, closed_through_number=3,
            closed_at=row['posted_at'], cancellation_log_complete=1)]
        docs = [dict(register_id=f'REG{i}', company_id='C001', series_id='PAY_2025', document_id=f'DOC{i}', document_number=i,
            transaction_id=row['transaction_id'] if i == 3 else f'EXTERNAL_{i}', issued_at=stamp(c.at-timedelta(days=2)), observed_at=stamp(c.at-timedelta(days=1)), state='issued', evidence_id=f'DOCUMENT_{i}') for i in (1, 3)]
        c.tables['document_register'] = docs
        scope = 'series:PAY_2025'
        if variant == 'duplicate':
            c.tables['document_register'].append({**docs[-1], 'register_id': 'ANOTHER', 'document_id': 'DISTINCT_DOC', 'transaction_id': 'EXTERNAL_OTHER'})
            scope = 'transaction'
        elif variant == 'cancelled_gap':
            c.tables['document_cancellations'] = [c.approved(cancellation_id='VOID2', series_id='PAY_2025', document_id='VOID_DOC2', document_number=2)]
            expected = False
        elif variant == 'not_closed':
            c.tables['document_series'][0]['closed_at'] = stamp(c.at+timedelta(days=1))
            expected = None
        elif variant == 'late_cancel':
            cancellation = c.approved(cancellation_id='VOID2', series_id='PAY_2025', document_id='VOID_DOC2', document_number=2)
            cancellation['observed_at'] = stamp(c.at+timedelta(days=1))
            c.tables['document_cancellations'] = [cancellation]
        elif variant == 'missing_cancel_coverage':
            c.tables['document_series'][0]['cancellation_log_complete'] = 0
            expected = None
    elif code == 'F4':
        customer = c.tables['customers'][0]
        invoice = dict(invoice_id='AR1', company_id='C001', customer_id=customer['customer_id'], gross_vnd=20_000_000,
            issued_at='2025-05-01T11:00:00+07:00', observed_at='2025-05-01T11:00:00+07:00', due_at='2025-06-01T11:00:00+07:00', status='issued', evidence_id='AR_INVOICE')
        c.tables['receivable_invoices'] = [invoice]
        c.tables['receipt_coverage'] = [c.approved(coverage_id='BANK_SYNC', covered_from=invoice['issued_at'], covered_through=stamp(c.at))]
        c.tables['receipt_coverage'][0]['observed_at'] = stamp(c.at)
        if variant in {'fully_paid', 'partial', 'overallocated', 'future_receipt'}:
            receipt = c.pay(c.at-timedelta(days=1), amount=20_000_000 if variant != 'partial' else 5_000_000, kind='customer_receipt')
            receipt['customer_id'] = customer['customer_id']
            receipt['amount_vnd'] = 20_000_000 if variant != 'partial' else 5_000_000
            allocation = dict(allocation_id='ALLOC', company_id='C001', invoice_id='AR1', customer_id=customer['customer_id'], receipt_transaction_id=receipt['transaction_id'],
                amount_vnd=receipt['amount_vnd'], observed_at=stamp(c.at-timedelta(days=1)+timedelta(minutes=10)), status='verified', evidence_id='BANK_ALLOCATION',
                verified_at=stamp(c.at-timedelta(days=1)+timedelta(minutes=5)), verifier_id=c.director['employee_id'])
            c.tables['receipt_allocations'] = [allocation]
            if variant == 'fully_paid':
                expected = False
            elif variant == 'overallocated':
                c.tables['receipt_allocations'].append({**allocation, 'allocation_id': 'ALLOC2'})
                expected = None
            elif variant == 'future_receipt':
                receipt['posted_at'] = allocation['observed_at'] = stamp(c.at+timedelta(days=1))
        row = c.pay(kind='cash_expense', amount=1_000_000)
        scope = 'invoice:AR1'
        if variant == 'explanation':
            c.tables['receivable_explanations'] = [c.approved(explanation_id='PLAN', invoice_id='AR1', reason='payment_plan', effective_from='2025-09-01T00:00:00+07:00', expires_at='2025-10-01T00:00:00+07:00')]
            expected = False
        elif variant == 'missing_coverage':
            c.tables['receipt_coverage'] = []
            expected = None
    elif code == 'A5':
        c.sequence([1_000_000+c.rng.randrange(-20000,20000) for _ in range(25)], kind='cash_expense', start=c.at-timedelta(days=30))
        row = c.pay(amount=3_000_000 if variant == 'positive' else 100_000 if variant == 'low_tail' else 1_000_000, kind='cash_expense')
        expected = variant == 'positive'
    elif code == 'A6':
        gross = 1_000_001+c.rng.randrange(1,500000)
        if gross % 1000 == 0:
            gross += 1
        amount = ((gross+999)//1000)*1000 if variant == 'positive' else gross//1000*1000
        row = c.pay(amount=amount, invoice_gross_vnd=gross)
        expected = variant == 'positive'
    elif code == 'B6':
        c.sequence([1_000_000+c.rng.randrange(10000) for _ in range(25)], start=datetime(2024,1,10,11,tzinfo=TZ))
        row = c.pay(amount=5_000_000 if variant == 'positive' else 900_000)
        expected = variant == 'positive'
    elif code == 'B7':
        row = c.change(verified=variant == 'verified', scheduled=True)
        expected = variant != 'verified'
    elif code == 'C1':
        row = c.pay(at=c.at.replace(hour=23))
        if variant == 'approved_shift':
            c.tables['operating_schedules'] = [c.approved(schedule_id='NIGHT', employee_id='', action='all', weekdays='4', start_time='22:00', end_time='06:00',
                effective_from='2025-01-01T00:00:00+07:00', effective_to='2025-12-31T23:59:59+07:00')]
            expected = False
    elif code == 'C3':
        row = c.pay(amount=100_000_000, created_at=stamp(c.at-timedelta(seconds=c.rng.randint(10,30) if variant == 'positive' else 600)))
        expected = variant == 'positive'
    elif code == 'E3':
        c.vendor['name'] = 'Công ty ABC'
        c.tables['vendors'][1]['name'] = 'A.B.C Co Ltd' if variant in {'positive', 'legitimate_affiliate'} else 'Gốm Hải Đăng'
        row = c.pay()
        expected = variant != 'distinct'
    else:
        raise ValueError(code)
    return c, row, expected, scope


SCENARIOS = {
    'C4': ('positive', 'authorized', 'late_source', 'cancel_after_action', 'end_boundary'),
    'E2': ('positive', 'final_payment', 'missing_period', 'rehire', 'late_source'),
    'F2': ('positive', 'authorized', 'completed', 'missing_policy'),
    'F3': ('positive', 'duplicate', 'cancelled_gap', 'not_closed', 'late_cancel', 'missing_cancel_coverage'),
    'F4': ('positive', 'fully_paid', 'partial', 'explanation', 'missing_coverage', 'overallocated', 'future_receipt'),
    'A5': ('positive', 'low_tail', 'normal'), 'A6': ('positive', 'under_invoice'),
    'B6': ('positive', 'below_p90'), 'B7': ('positive', 'verified'),
    'C1': ('positive', 'approved_shift'), 'C3': ('positive', 'normal_delay'),
    'E3': ('positive', 'legitimate_affiliate', 'distinct'),
}


def decision(result, code, row, scope):
    if scope != 'transaction':
        finding = next((f for f in reversed(result['evidence_findings']) if f['rule_id'] == code and f['scope'] == scope and f['cutoff_at'] == row['posted_at']), None)
        return finding.get('signal') if finding else None
    hits = [h for h in result['hits'] if h['transaction_id'] == row['transaction_id'] and h['rule_id'] == code]
    if any(h['evidence'].get('evidence_status') == 'information_gap' for h in hits):
        return None
    return any(not h['suppressed_reason'] for h in hits)
