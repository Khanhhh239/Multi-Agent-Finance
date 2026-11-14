"""Independent synthetic source scenarios. Expected signals stay outside input."""
from copy import deepcopy
from datetime import datetime,timedelta
import math,random
from .rule_audit_cases import Case
from .generate import stamp,TZ
from .accounting import enrich_accounting
from .exception_validation import PROFILES
from .native_rule_node import VERSION,TABLES
from .import_files import canonical,digest


def base():
    c=Case();c.at=datetime(2025,8,12,11,tzinfo=TZ)
    c.tables['employees']=[c.director,c.maker,c.worker]
    c.tables['vendors']=[c.vendor];c.tables['customers']=c.tables['customers'][:1]
    c.tables['entity_links']=[];c.tables['attendance']=[]
    c.tables['vendor_status_history']=[r for r in c.tables['vendor_status_history'] if r['vendor_id']==c.vendor['vendor_id']]
    for i,r in enumerate(c.tables['employees']):r.update(bank_account=f'SIM_STAFF_{i}',bank_code='SIMBANK',phone=f'090100000{i}',address=f'SIM_STAFF_ADDRESS_{i}')
    c.vendor.update(name='Orchid marine instruments',bank_account='SIM_VENDOR',bank_code='SIMBANK',phone='0902000000',address='SIM_VENDOR_ADDRESS',national_id='SIM_NATIONAL_VENDOR')
    return c


def approved(c,**values):
    return dict(company_id='C001',status='approved',evidence_on_file=1,evidence_id='SIM_SOURCE',approver_id=c.director['employee_id'],approved_at=stamp(c.at-timedelta(days=4)),observed_at=stamp(c.at-timedelta(days=3)),**values)


def evidence(c,table,**values):
    spec=PROFILES[table];row={f:'' for f in spec['required']}
    row.update(company_id='C001',observed_at=stamp(c.at-timedelta(days=2)))
    if all(f in row for f in ('approved_at','approver_id','evidence_on_file')):row.update(approved(c))
    row.update(values);c.tables[table].append(row);return row


def authorities(c):
    c.tables['approval_authority_coverage']=[approved(c,coverage_id='SIM_AUTH_COVERAGE',covered_actions='self_approve,approve',covered_from='2023-01-01',covered_through='2026-12-31')]
    common=approved(c,subject_role='',txn_type='*',department='',project_id='',min_amount_vnd=0,authority_type='policy',delegated_by_id='',effective_from='2023-01-01',effective_to='2026-12-31')
    c.tables['approval_authorities']=[dict(common,authority_id='SIM_SELF',subject_employee_id=c.maker['employee_id'],action='self_approve',max_amount_vnd=2_000_000,self_approval_allowed=1,authority_level='standard'),
        dict(common,authority_id='SIM_CHECK',subject_employee_id=c.director['employee_id'],approver_id=c.maker['employee_id'],action='approve',max_amount_vnd=1_000_000_000,self_approval_allowed=0,authority_level='high')]


def bind_invoices(c,rows,total):
    request='SIM_REQUEST';po='SIM_PO'
    evidence(c,'payment_requests',request_id=request,vendor_id=c.vendor['vendor_id'],purchase_order_id=po,contract_id='',invoice_number=rows[0]['invoice_number'],txn_type='vendor_payment',total_vnd=total)
    for row in rows:
        evidence(c,'procurement_links',link_id='SIM_LINK_'+row['transaction_id'],vendor_id=row['vendor_id'],transaction_id=row['transaction_id'],request_id=request,purchase_order_id=po,contract_id='',invoice_number=row['invoice_number'],status='verified',evidence_id='SIM_BOUND_REQUEST',verifier_id=c.director['employee_id'],verified_at=stamp(c.at-timedelta(days=4)))
        evidence(c,'transaction_documents',record_id='SIM_DOC_'+row['transaction_id'],vendor_id=row['vendor_id'],transaction_id=row['transaction_id'],document_type='invoice',invoice_number=row['invoice_number'],invoice_gross_vnd=row['invoice_gross_vnd'],status='verified',evidence_id='SIM_INVOICE',verifier_id=c.director['employee_id'],verified_at=stamp(c.at-timedelta(days=4)))


def finish(c,company='C001'):
    c.tables['transactions']=c.rows
    for row in c.rows:
        if row.get('recipient_account'):row.setdefault('recipient_bank_code','SIMBANK')
    enrich_accounting(c.tables,20261114)
    last=max(r['posted_at'] for r in c.rows)
    tables={name:deepcopy(c.tables.get(name,[])) for name in TABLES}
    for name,rows in tables.items():
        for row in rows:
            row['company_id']=company
            # These are explicit synthetic observation facts assigned by this
            # producer, not server defaults for missing real observation times.
            if name=='companies':row.setdefault('recorded_at','2023-01-01T00:00:00+07:00')
            if 'observed_at' not in row:
                row['observed_at']=row.get('recorded_at') or row.get('posted_at') or '2023-01-01T00:00:00+07:00'
    coverage={name:dict(status='complete',observed_at=last,covered_from='2023-01-01T00:00:00+07:00',covered_through=last,history_basis='since_inception',record_count=len(rows),records_sha256=digest(canonical(rows))) for name,rows in tables.items()}
    return dict(version=VERSION,tenant_id='native-demo',company_id=company,as_of=last,source_id='synthetic-native-rule-demo-v1',is_simulated=True,tables=tables,coverage=coverage)


def scenario(rule,positive,company='C001'):
    c=base();target=None
    if rule in ('A1','A2'):
        n=2 if rule=='A1' else 3
        rows=[c.pay(c.at+timedelta(days=i),9_000_000,invoice_number='SIM_INSTALLMENT' if not positive else f'SIM_INV_{i}',invoice_gross_vnd=9_000_000*n if not positive else 9_000_000) for i in range(n)]
        if not positive:bind_invoices(c,rows,9_000_000*n)
        target=rows[-1]
    elif rule=='A3':
        vendors=[c.vendor]
        for i in (1,2):
            v=deepcopy(c.vendor);v.update(vendor_id='SIM_VENDOR_'+str(i),representative_id='SIM_REP_'+str(i),national_id='SIM_NATIONAL_'+str(i),name='Separate supplier '+str(i),bank_account='SIM_OTHER_BANK_'+str(i),phone=c.vendor['phone'] if positive else '090300000'+str(i),address='SIM_OTHER_'+str(i));c.tables['vendors'].append(v);vendors.append(v)
        target=c.sequence([9_000_000]*3,vendors=vendors)
    elif rule=='A4':target=c.sequence([17_000_000 if positive else 1_000_003]*3,kind='cash_expense')
    elif rule=='A5':
        for i in range(45):c.pay(c.at-timedelta(days=60-i),900_001+i*123,kind='cash_expense')
        target=c.pay(amount=50_000_000 if positive else 904_921,kind='cash_expense')
    elif rule=='A6':target=c.pay(amount=2_001_000 if positive else 1_000_000,invoice_gross_vnd=1_990_007)
    elif rule=='B1':
        if positive:c.vendor['bank_account']=c.worker['bank_account']
        target=c.pay()
    elif rule=='B2':
        if positive:c.vendor.update(phone=c.worker['phone'],address=c.worker['address'])
        target=c.pay()
    elif rule=='B3':
        c.vendor['registered_at']=stamp(c.at-timedelta(days=30 if positive else 600));target=c.pay(amount=50_000_000,goods_receipt_verified=0,support_doc_count=0)
    elif rule=='B4':
        since=c.at-timedelta(days=7)
        c.tables['vendor_status_history'].append(dict(vendor_id=c.vendor['vendor_id'],company_id='C001',status='abandoned' if positive else 'active',effective_at=stamp(since),observed_at=stamp(since)))
        target=c.pay(invoice_issued_at=stamp(c.at-timedelta(days=1)))
    elif rule in ('B5','E4'):
        v=deepcopy(c.vendor);v.update(vendor_id='SIM_SECOND_VENDOR',name='Different logistics company',bank_account=c.vendor['bank_account'] if positive else 'SIM_UNIQUE_OTHER',phone=c.vendor['phone'] if positive else '0904000000',address='SIM_OTHER_ADDRESS');c.tables['vendors'].append(v);target=c.pay()
    elif rule=='B6':
        for i in range(25):c.pay(c.at-timedelta(days=240-i),1_000_000+i)
        target=c.pay(amount=50_000_000 if positive else 999_999)
    elif rule=='B7':
        before=c.at-timedelta(days=5)
        evidence(c,'bank_account_changes',change_id='SIM_BANK_CHANGE',vendor_id=c.vendor['vendor_id'],old_account=c.vendor['bank_account'],new_account='SIM_CHANGED_ACCOUNT',new_bank_code='SIMBANK',effective_at=stamp(before),observed_at=stamp(before+timedelta(hours=1)),callback_verified=0 if positive else 1,verified_at='' if positive else stamp(before),approver_id='' if positive else c.director['employee_id'])
        target=c.pay(amount=50_000_000,recipient_account='SIM_CHANGED_ACCOUNT',recipient_bank_code='SIMBANK')
    elif rule=='C1':target=c.pay(c.at.replace(hour=23 if positive else 11))
    elif rule=='C2':target=c.pay(amount=3_000_000 if positive else 1_000_000,approver_id=c.maker['employee_id'])
    elif rule=='C3':target=c.pay(amount=60_000_000,created_at=stamp(c.at-timedelta(seconds=20 if positive else 120)))
    elif rule=='C4':
        target=c.pay(created_at=stamp(c.at-timedelta(hours=1)))
        evidence(c,'leave_periods',leave_id='SIM_LEAVE',employee_id=c.maker['employee_id'],starts_at=stamp(c.at-timedelta(days=1)),ends_at=stamp(c.at+timedelta(days=1)))
        evidence(c,'system_actions',action_id='SIM_ACTION',employee_id=c.maker['employee_id'],transaction_id=target['transaction_id'],action='maker',action_at=target['created_at'],observed_at=target['created_at'],evidence_id='SIM_ACTION_LOG')
        if not positive:evidence(c,'leave_activity_authorizations',authorization_id='SIM_LEAVE_AUTH',employee_id=c.maker['employee_id'],leave_id='SIM_LEAVE',action='maker',starts_at=stamp(c.at-timedelta(days=1)),ends_at=stamp(c.at+timedelta(days=1)))
    elif rule=='E1':
        target=c.pay(kind='payroll');period=target['payroll_period']
        c.tables['attendance'].append(dict(company_id='C001',employee_id=c.worker['employee_id'],payroll_period=period,observed_at=stamp(c.at-timedelta(days=1)),days_worked_observed=0 if positive else 22,approved_leave_days=0,alternative_work_evidence=0))
    elif rule=='E2':
        target=c.pay(kind='payroll')
        evidence(c,'employment_events',employment_event_id='SIM_TERMINATION',employee_id=c.worker['employee_id'],event_type='termination',effective_date='2025-08-01')
        evidence(c,'payroll_settlements',settlement_id='SIM_SETTLEMENT',employee_id=c.worker['employee_id'],transaction_id=target['transaction_id'],payroll_period=target['payroll_period'],payment_kind='regular_salary' if positive else 'backpay',service_period_start='2025-08-02' if positive else '2025-07-01',service_period_end='2025-08-10' if positive else '2025-07-31',authorized_amount_vnd=target['amount_vnd'])
    elif rule=='E3':
        v=deepcopy(c.vendor);v.update(vendor_id='SIM_SIMILAR_NAME',name='Orchid marine instrument' if positive else 'Granite mountain transport',bank_account='SIM_SECOND_BANK',phone='0905000000',address='SIM_SECOND_ADDRESS');c.tables['vendors'].append(v);target=c.pay()
    elif rule=='F1':
        c.at=c.at.replace(day=31);target=c.pay(amount=30_000_000 if positive else 10_000_000,kind='adjustment')
        evidence(c,'journal_audit_log',audit_id='SIM_AUDIT',employee_id=c.maker['employee_id'],transaction_id=target['transaction_id'],entry_origin='manual' if positive else 'automatic',entered_at=stamp(c.at-timedelta(hours=1)),observed_at=stamp(c.at-timedelta(minutes=30)),evidence_id='SIM_JOURNAL_AUDIT')
        evidence(c,'closing_periods',closing_id='SIM_CLOSE',period_start='2025-08-01',period_end='2025-08-31',closing_at=stamp(c.at+timedelta(hours=2)))
        evidence(c,'materiality_policies',policy_id='SIM_MATERIALITY',effective_from='2025-01-01',effective_to='2025-12-31',materiality_vnd=20_000_000)
    elif rule=='F2':
        target=c.pay();evidence(c,'workflow_policies',workflow_policy_id='SIM_WORKFLOW',control_id='SIM_CONTROL',txn_type='vendor_payment',required=1,allow_override=0,authorized_override_roles='',override_max_vnd=0,effective_from='2025-01-01T00:00:00+07:00',effective_to='2025-12-31T23:59:59+07:00')
        evidence(c,'override_events',override_id='SIM_OVERRIDE',transaction_id=target['transaction_id'],actor_id=c.maker['employee_id'],operation_at=target['approved_at'],observed_at=target['approved_at'],control_id='SIM_CONTROL',status='executed',normal_workflow_completed=0 if positive else 1,evidence_id='SIM_OVERRIDE_LOG')
    elif rule=='F3':
        target=c.pay();evidence(c,'document_series',series_id='SIM_SERIES',fiscal_year=2025,document_type='invoice',start_number=1,closed_through_number=2,closed_at=stamp(c.at-timedelta(hours=1)),cancellation_log_complete=1)
        for i in (1,2):evidence(c,'document_register',register_id='SIM_REGISTER_'+str(i),series_id='SIM_SERIES',document_id='SIM_DOCUMENT_'+str(i),document_number=1 if positive else i,transaction_id=target['transaction_id'],issued_at=stamp(c.at-timedelta(days=1)),observed_at=stamp(c.at-timedelta(hours=1)),state='issued',evidence_id='SIM_REGISTER_PROOF')
    elif rule=='F4':
        target=c.pay(kind='sales_invoice');customer=c.tables['customers'][0];target['customer_id']=customer['customer_id']
        evidence(c,'receivable_invoices',invoice_id='SIM_RECEIVABLE',customer_id=customer['customer_id'],gross_vnd=9_000_000,issued_at='2025-04-01T10:00:00+07:00',due_at='2025-05-01T10:00:00+07:00',status='issued',observed_at='2025-04-01T10:00:00+07:00',evidence_id='SIM_RECEIVABLE_PROOF')
        evidence(c,'receipt_coverage',coverage_id='SIM_RECEIPT_HISTORY',covered_from='2025-04-01T00:00:00+07:00',covered_through=stamp(c.at),observed_at=stamp(c.at))
        if not positive:evidence(c,'receivable_explanations',explanation_id='SIM_PAYMENT_PLAN',invoice_id='SIM_RECEIVABLE',reason='payment_plan',effective_from='2025-08-01T00:00:00+07:00',expires_at='2025-09-01T00:00:00+07:00')
    elif rule=='P1':
        c.pay(c.at-timedelta(days=1),6_000_000,invoice_number='SIM_SHARED_INVOICE',invoice_gross_vnd=10_000_000)
        target=c.pay(amount=6_000_000 if positive else 3_000_000,invoice_number='SIM_SHARED_INVOICE',invoice_gross_vnd=10_000_000)
    elif rule=='P2':target=c.pay(amount=6_000_000,kind='cash_expense',payment_channel='cash' if positive else 'bank')
    elif rule in ('T1','T2'):
        advance_id='SIM_ADVANCE';start=c.at-timedelta(days=100)
        c.tables['advances'].append(dict(advance_id=advance_id,company_id='C001',employee_id=c.worker['employee_id'],issued_at=stamp(start),original_amount_vnd=10_000_000,original_due_at=stamp(c.at-timedelta(days=70 if positive else -5)),recorded_at=stamp(start)))
        target=c.pay(amount=10_000_000,kind='advance_review' if rule=='T1' else 'advance_writeoff',advance_id=advance_id,evidence_on_file=0 if positive else 1)
        if rule=='T2':c.tables['advance_events'].append(dict(event_id='SIM_WRITEOFF',advance_id=advance_id,company_id='C001',event_type='writeoff',amount_vnd=10_000_000,due_at='',observed_at=target['posted_at'],evidence_on_file=0 if positive else 1,transaction_id=target['transaction_id']))
    else:raise ValueError(rule)
    authorities(c)
    bundle=finish(c,company)
    return bundle,dict(rule_id=rule,positive=positive,target_transaction_id=target['transaction_id'],expected_signal=positive)


def statistical_scenario(positive,company='C001'):
    c=base();c.at=datetime(2025,8,1,11,tzinfo=TZ);rng=random.Random(20261114)
    c.maker['approval_limit_vnd']=10_000_000
    for month in (5,7):
        for i in range(1500):
            at=datetime(2025,month,1,tzinfo=TZ)+timedelta(minutes=i*20)
            if positive and month==7 and i<100:amount=9_800_000+i*1733
            elif positive and month==7 and i<750:
                scale=(1000,10000,100000,10000000)[i%4];amount=9*scale+(i*11)%scale
            else:amount=int(10**rng.uniform(3,8))
            ending=(999 if positive and month==7 and i%2==0 else (0,500,999)[i%3] if i%30<3 else amount%1000)
            amount=max(1000,amount//1000*1000+ending)
            c.pay(at,amount,kind='cash_expense',payment_channel='bank',support_doc_count=0)
    c.pay(c.at,1000003,kind='cash_expense');authorities(c)
    return finish(c,company),dict(rule_ids=['D1','D2','D3','D4','D5','D6'],positive=positive,expected_signal=positive,cutoff_at='2025-08-01T00:00:00+07:00')
