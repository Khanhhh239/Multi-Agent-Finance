"""Seeded ERP/HR process simulation; oracle declarations never read rule output.

Plausibility priors are design assumptions, not fitted Vietnamese SME statistics.
Background operations and deliberately enriched controls are separate cohorts.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import calendar
import hashlib
import math
import random

from .generate import Generator, TZ, stamp, parse, PAIRS
from .accounting import enrich_accounting


START = datetime(2024, 1, 1, tzinfo=TZ)
AS_OF = '2025-12-31T23:59:59+07:00'
SECTORS = ('trading', 'manufacturing', 'services', 'retail', 'logistics')
KINDS = {
    'trading': (('vendor_payment', 'sales_invoice', 'customer_receipt', 'cash_expense', 'selling_expense', 'adjustment'), (35, 22, 22, 10, 8, 3)),
    'manufacturing': (('material_purchase', 'stock_purchase', 'sales_invoice', 'customer_receipt', 'cash_expense', 'adjustment'), (27, 15, 21, 22, 11, 4)),
    'services': (('vendor_payment', 'sales_invoice', 'customer_receipt', 'cash_expense', 'selling_expense', 'adjustment'), (15, 25, 29, 19, 8, 4)),
    'retail': (('stock_purchase', 'sales_invoice', 'customer_receipt', 'cash_expense', 'selling_expense', 'adjustment'), (28, 25, 27, 12, 6, 2)),
    'logistics': (('vendor_payment', 'sales_invoice', 'customer_receipt', 'cash_expense', 'equipment_purchase', 'adjustment'), (29, 20, 22, 21, 5, 3)),
}
VARIANTS = {
    'F1': ('manual_material_close', 'automatic_close', 'below_materiality', 'earlier_entry', 'future_audit', 'revoked_materiality'),
    'C4': ('leave_action', 'authorized_work', 'leave_end_boundary', 'future_leave', 'revoked_after_action', 'revoked_before_action'),
    'E2': ('post_termination_salary', 'final_settlement', 'backpay', 'rehired', 'missing_settlement', 'future_termination'),
    'F2': ('unauthorized_bypass', 'allowed_override', 'completed_workflow', 'missing_policy', 'future_policy', 'cancelled_override'),
    'F3': ('unexplained_gap', 'cancelled_gap', 'missing_cancel_coverage', 'future_cancellation', 'duplicate_number', 'clean_series'),
    'F4': ('overdue_unpaid', 'fully_paid', 'partial_payment', 'approved_plan', 'missing_coverage', 'overallocated_receipt', 'not_due', 'future_receipt'),
}


def month_end(year, month, hour=23, minute=59, second=59):
    return datetime(year, month, calendar.monthrange(year, month)[1], hour, minute, second, tzinfo=TZ)


class World:
    def __init__(self, seed, companies=8, background_rows=12000):
        self.seed, self.rng = seed, random.Random(seed)
        self.g = Generator(0, 0, seed, companies)
        self.tables, self.serial = self.g.tables, Counter()
        self.rows, self.oracle, self.quarantine = [], [], []
        self.background_rows = background_rows
        self.profiles, self.reserved = {}, defaultdict(list)
        self.company_bank = {}
        self.setup_masters()

    def uid(self, kind):
        self.serial[kind] += 1
        return kind+'_'+hashlib.sha256(f'{self.seed}:{kind}:{self.serial[kind]}'.encode()).hexdigest()[:18]

    def person_name(self):
        return ' '.join((self.rng.choice(('Nguyễn', 'Lê', 'Trần', 'Phạm', 'Võ', 'Đặng', 'Bùi', 'Đỗ')),
                         self.rng.choice(('Minh', 'Thanh', 'Ngọc', 'Hoài', 'Quang', 'Gia', 'Bảo', 'Khánh')),
                         self.rng.choice(('An', 'Hà', 'Linh', 'Nam', 'Uyên', 'Thảo', 'Huy', 'Khoa', 'Trang'))))

    def decorate_employee(self, employee):
        employee.update(full_name=self.person_name(), bank_code=self.rng.choice(('SIM_BK01', 'SIM_BK02', 'SIM_BK03', 'SIM_BK04')),
                        bank_account='0'+''.join(str(self.rng.randrange(10)) for _ in range(self.rng.choice((9, 11, 12)))),
                        monthly_salary_vnd=int(min(60_000_000, max(6_000_000, self.rng.lognormvariate(math.log(14_000_000), .4)))/1000)*1000,
                        contract_on_file=1)
        return employee

    def setup_masters(self):
        # Replace contact mirrors together with the masters; no stale token edges.
        self.tables['entity_links'] = []
        for company in self.tables['companies']:
            cid = company['company_id']
            industry = company['industry']
            size = self.rng.uniform(.35, 2.8)
            headcount = self.rng.randint(18, 55)
            staff = self.g.company_staff[cid]
            while len(staff) < headcount:
                self.g.employee(cid, datetime(2023, 1, 1, tzinfo=TZ))
            keep = set(staff[:headcount])
            self.g.company_staff[cid] = staff[:headcount]
            self.tables['employees'] = [e for e in self.tables['employees'] if e['company_id'] != cid or e['employee_id'] in keep]
            self.tables['attendance'] = [e for e in self.tables['attendance'] if e['company_id'] != cid or e['employee_id'] in keep]
            company.update(name=f"{self.rng.choice(('Minh Lộ', 'Vân Hải', 'An Phúc', 'Bình Nguyên', 'Ngọc Vũ'))} {industry.title()} {cid}", amount_scale=size)
            self.company_bank[cid] = 'SIM_BK01'
            self.profiles[cid] = dict(industry=industry, activity_weight=self.rng.lognormvariate(0, .8),
                amount_median=8_000_000*size, amount_sigma=self.rng.uniform(.7, 1.35),
                payroll_headcount=headcount, rent_vnd=self.rng.randrange(12, 65)*1_000_000,
                december_multiplier=self.rng.uniform(1.15, 2.0), batch_posting_fraction=self.rng.uniform(.60, .90))
            for eid in self.g.company_staff[cid]:
                self.decorate_employee(self.g.employees[eid])
            selected = self.g.company_vendors[cid][:self.rng.randint(30, 75)]
            self.g.company_vendors[cid] = selected
            self.tables['vendors'] = [v for v in self.tables['vendors'] if v['company_id'] != cid or v['vendor_id'] in selected]
            self.tables['vendor_status_history'] = [v for v in self.tables['vendor_status_history'] if v['company_id'] != cid or v['vendor_id'] in selected]
            for index, vid in enumerate(selected):
                vendor = self.g.vendors[vid]
                vendor.update(name=f"{self.rng.choice(('Cơ khí', 'Thiết bị', 'Vật tư', 'Dịch vụ', 'Thương mại', 'Vận tải'))} {self.rng.choice(('Sông Lam', 'Hải Âu', 'Tân Lộc', 'Hướng Dương', 'Nam Sơn', 'Lam Sơn', 'Đông Phong', 'Thiên Hà'))} {index+1}",
                    bank_code=self.rng.choice(('SIM_BK01', 'SIM_BK02', 'SIM_BK03', 'SIM_BK04')),
                    bank_account='0'+''.join(str(self.rng.randrange(10)) for _ in range(self.rng.choice((9, 11, 12)))))
            for cuid in self.g.company_customers[cid]:
                self.g.customers[cuid]['name'] = f"{self.rng.choice(('Phân phối', 'Xưởng', 'Cửa hàng', 'Dịch vụ'))} {self.rng.choice(('Thanh Hà', 'Đại Nam', 'Phương Bắc', 'Hòa Bình', 'Trúc Mai'))} {cuid[-3:]}"
        # Generator.employee() may have inserted mirrors while headcount grew.
        # Rebuild after decoration, including every newly added employee.
        self.tables['entity_links'] = []
        for row in [*self.tables['employees'], *self.tables['vendors']]:
            identity = row.get('employee_id') or row['vendor_id']
            for kind in ('bank_account', 'phone'):
                self.tables['entity_links'].append(dict(company_id=row['company_id'], source_id=identity,
                    target_id=row[kind], link_type=kind, observed_at=row['recorded_at'],
                    bank_code=row.get('bank_code', '') if kind == 'bank_account' else ''))

    def approved(self, cid, at, **fields):
        return dict(company_id=cid, status='approved', approver_id=self.g.company_staff[cid][0],
                    approved_at=stamp(at-timedelta(days=3)), observed_at=stamp(at-timedelta(days=2)),
                    evidence_on_file=1, evidence_id=self.uid('EV'), **fields)

    def employee(self, cid, role='accountant'):
        employee = self.g.employee(cid, datetime(2023, 1, 1, tzinfo=TZ), role=role, append_to_background=False)
        self.decorate_employee(employee)
        eid = employee['employee_id']
        self.tables['entity_links'] = [r for r in self.tables['entity_links'] if r['source_id'] != eid]
        for kind in ('bank_account', 'phone'):
            self.tables['entity_links'].append(dict(company_id=cid, source_id=eid,
                target_id=employee[kind], link_type=kind, observed_at=employee['recorded_at'],
                bank_code=employee['bank_code'] if kind == 'bank_account' else ''))
        self.reserved[cid].append(employee['employee_id'])
        return employee

    def payment(self, cid, at, kind='vendor_payment', amount=None, creator=None, employee=None, **fields):
        profile = self.profiles[cid]
        if amount is None:
            amount = max(25_000, int(self.rng.lognormvariate(math.log(profile['amount_median']), profile['amount_sigma'])/1000)*1000)
        maker = creator or self.rng.choice(self.g.company_staff[cid][2:6])
        row = self.g.transaction(cid, 'train' if at.year == 2024 else 'validation' if at.month <= 6 else 'test',
            at, kind, employee=employee, amount=amount, creator=maker,
            approver=self.g.company_staff[cid][0], delay_hours=self.rng.uniform(.25, 8))
        row.update(transaction_id=self.uid('TX'), support_doc_count=self.rng.choices((1, 2, 3, 4), (6, 35, 42, 17))[0],
                   goods_receipt_verified=int(self.rng.random() < .95))
        counterparty = self.g.vendors.get(row['vendor_id']) or self.g.employees.get(row['employee_id'])
        row['recipient_bank_code'] = counterparty.get('bank_code', '') if counterparty else 'SIM_BK01' if row['customer_id'] else ''
        row.update(fields)
        self.rows.append(row)
        return row

    def declare(self, rule, row=None, *, company=None, unit_type='transaction', unit_id=None,
                expected=False, scenario='', at=None):
        self.oracle.append(dict(rule_id=rule, company_id=company or row['company_id'], unit_type=unit_type,
            unit_id=unit_id or row['transaction_id'], event_at=at or (row['posted_at'] if row else AS_OF),
            expected=expected, scenario=scenario, cohort='enriched_process_controls',
            truth_unit='declared_source_condition_not_financial_fraud'))

    def background(self):
        companies = list(self.profiles)
        weights = [self.profiles[cid]['activity_weight'] for cid in companies]
        for _ in range(self.background_rows):
            cid = self.rng.choices(companies, weights)[0]
            profile = self.profiles[cid]
            months = list(range(1, 13))
            month = self.rng.choices(months, [profile['december_multiplier'] if m == 12 else .75 if m == 2 else 1 for m in months])[0]
            year = self.rng.choice((2024, 2025))
            day = self.rng.randint(1, calendar.monthrange(year, month)[1])
            at = datetime(year, month, day, self.rng.choices((10, 14, 18, 21), (30, 31, 35, 4))[0], self.rng.randrange(60), self.rng.randrange(60), tzinfo=TZ)
            if self.rng.random() < profile['batch_posting_fraction']:
                at = at.replace(hour=18, minute=0, second=0)
            kinds, rates = KINDS[profile['industry']]
            self.payment(cid, at, self.rng.choices(kinds, rates)[0])
        for cid, profile in self.profiles.items():
            for year in (2024, 2025):
                for month in range(1, 13):
                    at = datetime(year, month, min(28, calendar.monthrange(year, month)[1]), 16, tzinfo=TZ)
                    for eid in self.g.company_staff[cid]:
                        employee = self.g.employees[eid]
                        row = self.payment(cid, at, 'payroll', employee=employee)
                        self.tables['payroll_entitlements'].append(self.approved(cid, at,
                            entitlement_id=self.uid('ENT'), employee_id=eid, payroll_period=row['payroll_period'],
                            leave_type='regular_payroll', entitled_amount_vnd=row['amount_vnd']))
                    vendor = self.g.vendors[self.g.company_vendors[cid][0]]
                    rent = self.payment(cid, at-timedelta(days=20), 'rent', profile['rent_vnd'])
                    rent.update(vendor_id=vendor['vendor_id'], recipient_account=vendor['bank_account'],
                                recipient_bank_code=vendor['bank_code'], contract_id='RENT_'+cid)
                    self.tables['recurring_payments'].append(self.approved(cid, datetime(2024, 1, 1, tzinfo=TZ),
                        pattern_id='RENT_'+cid, vendor_id=vendor['vendor_id'], employee_id='', txn_type='rent',
                        contract_id='RENT_'+cid, invoice_number='', frequency='monthly',
                        expected_amount_vnd=profile['rent_vnd'], tolerance_vnd=0, allow_partial=0,
                        effective_from='2024-01-01', effective_to='2025-12-31'))
        # Exact duplicate exports are legal idempotency cases; schemas retain revisions.
        self.tables['recurring_payments'] = list({(row['company_id'], row['pattern_id']): row for row in self.tables['recurring_payments']}.values())

    def policies(self):
        for cid, profile in self.profiles.items():
            material = int(max(10_000_000, profile['amount_median']*4)/1000)*1000
            profile['materiality_vnd'] = material
            self.tables['materiality_policies'].append(self.approved(cid, START,
                policy_id=self.uid('MAT'), effective_from='2024-01-01', effective_to='2025-12-31', materiality_vnd=material))
            for year in (2024, 2025):
                for month in range(1, 13):
                    self.tables['closing_periods'].append(self.approved(cid, datetime(year, month, 1, tzinfo=TZ),
                        closing_id=self.uid('CLOSE'), period_start=f'{year}-{month:02}-01',
                        period_end=month_end(year, month).date().isoformat(), closing_at=stamp(month_end(year, month))))

    def controls(self, repetitions=2):
        for cid in self.profiles:
            for rule, variants in VARIANTS.items():
                for variant in variants:
                    for _ in range(repetitions):
                        self.control(cid, rule, variant)

    def control(self, cid, rule, variant):
        at = datetime(2025, self.rng.randint(2, 11), self.rng.randint(8, 20), self.rng.randint(9, 16), self.rng.randrange(60), tzinfo=TZ)
        if rule == 'F1':
            material = self.profiles[cid]['materiality_vnd']
            at = month_end(2025, at.month, 16, self.rng.randrange(60), 0)-timedelta(days=self.rng.randint(0, 2))
            row = self.payment(cid, at, 'adjustment', material+self.rng.randrange(1_000_000, 30_000_000))
            origin, observed = ('automatic' if variant == 'automatic_close' else 'manual'), row['posted_at']
            if variant == 'below_materiality':
                row['amount_vnd'] = material-self.rng.randint(1, 500_000)
            if variant == 'earlier_entry':
                row['created_at'] = stamp(at-timedelta(days=12))
            if variant == 'future_audit':
                observed = stamp(at+timedelta(days=1))
            if variant == 'revoked_materiality':
                # Distinct one-day replacement does not change another month's policy.
                replacement = self.approved(cid, at-timedelta(days=1), policy_id=self.uid('MAT'),
                    effective_from=at.date().isoformat(), effective_to=at.date().isoformat(), materiality_vnd=material)
                replacement.update(status='revoked')
                self.tables['materiality_policies'].append(replacement)
                # An invalid replacement does not revoke the existing approved policy.
                expected = True
            else:
                expected = variant == 'manual_material_close'
            self.tables['journal_audit_log'].append(dict(audit_id=self.uid('AUD'), company_id=cid,
                employee_id=row['creator_id'], transaction_id=row['transaction_id'], entry_origin=origin,
                entered_at=row['created_at'], observed_at=observed, evidence_id=self.uid('EV')))
            self.declare(rule, row, expected=expected, scenario=variant)
        elif rule == 'C4':
            actor = self.employee(cid)
            row = self.payment(cid, at, creator=actor['employee_id'])
            leave = self.approved(cid, at-timedelta(days=10), leave_id=self.uid('LEAVE'), employee_id=actor['employee_id'],
                starts_at=stamp(at-timedelta(days=1)), ends_at=stamp(at+timedelta(days=1)))
            if variant == 'leave_end_boundary':
                leave['ends_at'] = row['created_at']
            if variant == 'future_leave':
                leave['observed_at'] = stamp(at+timedelta(days=2))
            self.tables['leave_periods'].append(leave)
            if variant in {'revoked_after_action', 'revoked_before_action'}:
                self.tables['leave_periods'].append(dict(leave, status='revoked', observed_at=
                    row['posted_at'] if variant == 'revoked_after_action' else stamp(parse(row['created_at'])-timedelta(minutes=5))))
            if variant == 'authorized_work':
                self.tables['leave_activity_authorizations'].append(self.approved(cid, at-timedelta(days=5),
                    authorization_id=self.uid('AUTH'), employee_id=actor['employee_id'], leave_id=leave['leave_id'],
                    action='maker', starts_at=leave['starts_at'], ends_at=leave['ends_at']))
            self.tables['system_actions'].append(dict(action_id=self.uid('ACT'), company_id=cid,
                employee_id=actor['employee_id'], transaction_id=row['transaction_id'], action='maker',
                action_at=row['created_at'], observed_at=row['posted_at'], evidence_id=self.uid('EV')))
            self.declare(rule, row, expected=variant in {'leave_action', 'revoked_after_action'}, scenario=variant)
        elif rule == 'E2':
            worker = self.employee(cid, 'operations')
            row = self.payment(cid, at, 'payroll', employee=worker)
            effective = (at-timedelta(days=self.rng.randint(8, 40))).date()
            event = self.approved(cid, at-timedelta(days=60), employment_event_id=self.uid('EMP'),
                employee_id=worker['employee_id'], event_type='termination', effective_date=effective.isoformat())
            if variant == 'future_termination':
                event['observed_at'] = stamp(at+timedelta(days=3))
            self.tables['employment_events'].append(event)
            if variant == 'rehired':
                self.tables['employment_events'].append(self.approved(cid, at-timedelta(days=3),
                    employment_event_id=self.uid('EMP'), employee_id=worker['employee_id'], event_type='rehire',
                    effective_date=(at-timedelta(days=2)).date().isoformat()))
            if variant != 'missing_settlement':
                prior = variant in {'final_settlement', 'backpay'}
                end = effective if prior else at.date()+timedelta(days=10)
                start = effective-timedelta(days=28) if prior else effective+timedelta(days=1)
                self.tables['payroll_settlements'].append(self.approved(cid, at-timedelta(days=1),
                    settlement_id=self.uid('PAY'), employee_id=worker['employee_id'], transaction_id=row['transaction_id'],
                    payroll_period=row['payroll_period'], payment_kind=variant if prior else 'regular_salary',
                    service_period_start=start.isoformat(), service_period_end=end.isoformat(), authorized_amount_vnd=row['amount_vnd']))
            self.declare(rule, row, expected=None if variant == 'missing_settlement' else variant == 'post_termination_salary', scenario=variant)
        elif rule == 'F2':
            actor = self.employee(cid)
            row = self.payment(cid, at, 'cash_expense', self.rng.randint(1_000_000, 12_000_000), creator=actor['employee_id'])
            control = self.uid('CTL')
            if variant != 'missing_policy':
                policy = self.approved(cid, at-timedelta(days=7), workflow_policy_id=self.uid('WF'), control_id=control,
                    txn_type='cash_expense', required=1, allow_override=int(variant == 'allowed_override'),
                    authorized_override_roles='accountant', override_max_vnd=20_000_000,
                    effective_from='2024-01-01T00:00:00+07:00', effective_to=AS_OF)
                if variant == 'future_policy':
                    policy['observed_at'] = stamp(at+timedelta(days=1))
                self.tables['workflow_policies'].append(policy)
            self.tables['override_events'].append(dict(override_id=self.uid('OVR'), company_id=cid,
                transaction_id=row['transaction_id'], actor_id=actor['employee_id'], operation_at=row['created_at'],
                observed_at=row['posted_at'], control_id=control, status='cancelled' if variant == 'cancelled_override' else 'executed',
                normal_workflow_completed=int(variant == 'completed_workflow'), evidence_id=self.uid('EV')))
            self.declare(rule, row, expected=None if variant in {'missing_policy', 'future_policy'} else variant == 'unauthorized_bypass', scenario=variant)
        elif rule == 'F3':
            scope = self.uid('SER')
            closed = parse(AS_OF)
            size = self.rng.randint(9, 24)
            gap = self.rng.randint(2, size-1)
            series = self.approved(cid, datetime(2025, 1, 1, tzinfo=TZ), series_id=scope, fiscal_year=2025,
                document_type='payment', start_number=1, closed_through_number=size, closed_at=AS_OF,
                cancellation_log_complete=int(variant != 'missing_cancel_coverage'))
            self.tables['document_series'].append(series)
            last = None
            for number in range(1, size+1):
                if number == gap and variant != 'clean_series':
                    continue
                row = self.payment(cid, at+timedelta(minutes=number), 'cash_expense', self.rng.randint(150_000, 8_000_000))
                last = row
                doc = dict(register_id=self.uid('REG'), company_id=cid, series_id=scope, document_id=self.uid('DOC'),
                    document_number=number, transaction_id=row['transaction_id'], issued_at=row['posted_at'],
                    observed_at=row['posted_at'], state='issued', evidence_id=self.uid('EV'))
                self.tables['document_register'].append(doc)
                if variant == 'duplicate_number' and number == size:
                    # Two distinct documents, not an idempotent re-export of one record.
                    extra = self.payment(cid, parse(row['posted_at'])+timedelta(hours=1), 'cash_expense', row['amount_vnd'])
                    self.tables['document_register'].append(dict(doc, register_id=self.uid('REG'),
                        document_id=self.uid('DOC'), transaction_id=extra['transaction_id'], issued_at=extra['posted_at'], observed_at=extra['posted_at']))
                    self.declare(rule, extra, expected=True, scenario=variant)
            if variant in {'cancelled_gap', 'future_cancellation'}:
                cancellation = self.approved(cid, at-timedelta(days=1), cancellation_id=self.uid('VOID'),
                    series_id=scope, document_id=self.uid('DOC'), document_number=gap)
                if variant == 'future_cancellation':
                    cancellation['observed_at'] = stamp(closed+timedelta(days=1))
                self.tables['document_cancellations'].append(cancellation)
            if variant != 'duplicate_number':
                self.declare(rule, company=cid, unit_type='document_series', unit_id=scope, at=AS_OF,
                    expected=None if variant == 'missing_cancel_coverage' else variant not in {'clean_series', 'cancelled_gap'}, scenario=variant)
        elif rule == 'F4':
            customer = self.g.customers[self.rng.choice(self.g.company_customers[cid])]
            # One bank-ledger coverage stream per company; a missing source case
            # uses an invoice issued before its declared coverage start.
            issued = datetime(2025, self.rng.randint(5, 8), self.rng.randint(1, 20), 10, tzinfo=TZ)
            if variant == 'missing_coverage':
                issued = datetime(2023, 12, self.rng.randint(1, 15), 10, tzinfo=TZ)
            if variant == 'not_due':
                issued = datetime(2025, 12, self.rng.randint(10, 22), 10, tzinfo=TZ)
            gross = self.rng.randint(4_000, 90_000)*1000
            invoice_id = self.uid('AR')
            due = issued+timedelta(days=self.rng.choice((15, 30, 45, 60)))
            if variant == 'not_due':
                due = parse(AS_OF)+timedelta(days=self.rng.randint(15, 60))
            self.tables['receivable_invoices'].append(dict(invoice_id=invoice_id, company_id=cid,
                customer_id=customer['customer_id'], gross_vnd=gross, issued_at=stamp(issued),
                due_at=stamp(due), observed_at=stamp(issued+timedelta(hours=self.rng.randint(0, 36))),
                status='issued', evidence_id=self.uid('EV')))
            if variant in {'fully_paid', 'partial_payment', 'overallocated_receipt', 'future_receipt'}:
                amount = gross if variant != 'partial_payment' else int(gross*self.rng.uniform(.15, .75))
                receipt_at = issued+timedelta(days=self.rng.randint(10, 50))
                if variant == 'future_receipt':
                    receipt_at = parse(AS_OF)+timedelta(days=1)
                receipt = self.payment(cid, receipt_at, 'customer_receipt', amount)
                receipt.update(customer_id=customer['customer_id'], amount_vnd=amount)
                record = dict(allocation_id=self.uid('ALLOC'), company_id=cid, invoice_id=invoice_id,
                    customer_id=customer['customer_id'], receipt_transaction_id=receipt['transaction_id'], amount_vnd=amount,
                    observed_at=stamp(receipt_at+timedelta(minutes=10)), status='verified', evidence_id=self.uid('EV'),
                    verified_at=stamp(receipt_at+timedelta(minutes=5)), verifier_id=self.g.company_staff[cid][0])
                self.tables['receipt_allocations'].append(record)
                if variant == 'overallocated_receipt':
                    self.tables['receipt_allocations'].append(dict(record, allocation_id=self.uid('ALLOC')))
            if variant == 'approved_plan':
                self.tables['receivable_explanations'].append(self.approved(cid, datetime(2025, 12, 1, tzinfo=TZ),
                    explanation_id=self.uid('PLAN'), invoice_id=invoice_id, reason='payment_plan',
                    effective_from='2025-12-01T00:00:00+07:00', expires_at='2026-01-31T23:59:59+07:00'))
            self.declare(rule, company=cid, unit_type='receivable_invoice', unit_id=invoice_id, at=AS_OF,
                expected=None if variant in {'missing_coverage', 'overallocated_receipt'} else variant in {'overdue_unpaid', 'partial_payment', 'future_receipt'}, scenario=variant)

    def add_background_sources(self):
        audited = {row['transaction_id'] for row in self.tables['journal_audit_log']}
        actions = {row['transaction_id'] for row in self.tables['system_actions']}
        for row in self.rows:
            if row['posted_at'] > AS_OF:
                continue
            if row['transaction_id'] not in audited:
                self.tables['journal_audit_log'].append(dict(audit_id=self.uid('AUD'), company_id=row['company_id'],
                    employee_id=row['creator_id'], transaction_id=row['transaction_id'],
                    entry_origin='manual' if row['txn_type'] == 'adjustment' and self.rng.random() < .7 else 'automatic',
                    entered_at=row['created_at'], observed_at=row['posted_at'], evidence_id=self.uid('EV')))
            if row['transaction_id'] not in actions and self.rng.random() < .5:
                self.tables['system_actions'].append(dict(action_id=self.uid('ACT'), company_id=row['company_id'],
                    employee_id=row['creator_id'], transaction_id=row['transaction_id'], action='maker',
                    action_at=row['created_at'], observed_at=row['posted_at'], evidence_id=self.uid('EV')))
        for cid in self.profiles:
            self.tables['receipt_coverage'].append(self.approved(cid, parse(AS_OF)-timedelta(days=1),
                coverage_id=self.uid('COV'), covered_from='2024-01-01T00:00:00+07:00', covered_through=AS_OF))
            self.tables['receipt_coverage'][-1]['observed_at'] = AS_OF
        # Harmless later name revision exercises signing-time staff lookup.
        for cid in self.profiles:
            director = self.g.employees[self.g.company_staff[cid][0]]
            self.tables['employees'].append(dict(director, full_name=director['full_name']+' Anh', recorded_at='2026-01-05T09:00:00+07:00'))

    def build(self, repetitions=2):
        self.policies()
        self.background()
        self.controls(repetitions)
        self.add_background_sources()
        # Future settlement records remain in sources; future payments themselves
        # are quarantined from this snapshot, never scored as historical evidence.
        future = [row for row in self.rows if row['posted_at'] > AS_OF]
        self.rows = [row for row in self.rows if row['posted_at'] <= AS_OF]
        for row in future:
            self.quarantine.append(dict(reason='after_snapshot_cutoff', source_record=row))
        self.rows.sort(key=lambda row: (row['posted_at'], row['transaction_id']))
        self.tables['transactions'] = self.rows
        self.tables['splits'] = [dict(transaction_id=row['transaction_id'], split='history' if row['posted_at'].startswith('2024') else 'source_evaluation') for row in self.rows]
        self.tables['labels'] = []  # Deliberately no financial-fraud labels.
        enrich_accounting(self.tables, self.seed)
        return self.tables, self.oracle


def raw_export(row):
    return dict(voucher_uid=row['transaction_id'], org_code=row['company_id'],
        booked_at_utc=parse(row['posted_at']).astimezone(timezone.utc).isoformat(timespec='seconds'),
        value_vnd=f"{row['amount_vnd']:,}", payment_kind=row['txn_type'],
        recipient_number=row['recipient_account'], recipient_bank=row.get('recipient_bank_code', ''),
        maker_ref=row['creator_id'], checker_ref=row['approver_id'])


def map_export(row):
    if row.get('payment_kind') not in PAIRS:
        raise ValueError('Unsupported ERP semantics; preserve raw record for mapping review')
    amount = str(row['value_vnd'])
    groups = amount.split(',')
    if not amount or any(not part.isascii() or not part.isdecimal() for part in groups) or (len(groups)>1 and (not 1 <= len(groups[0]) <= 3 or any(len(part) != 3 for part in groups[1:]))):
        raise ValueError('Invalid VND amount syntax')
    at = parse(row['booked_at_utc'])
    if at.tzinfo is None:
        raise ValueError('ERP timestamp requires timezone')
    return dict(transaction_id=row['voucher_uid'], company_id=row['org_code'], posted_at=stamp(at.astimezone(TZ)),
        amount_vnd=int(''.join(groups)), txn_type=row['payment_kind'], recipient_account=row['recipient_number'],
        recipient_bank_code=row['recipient_bank'], creator_id=row['maker_ref'], approver_id=row['checker_ref'])
