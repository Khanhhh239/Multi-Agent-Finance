"""Tình huống nghiệp vụ cố định kiểm hồi quy quy ước lịch sử; không xác minh luật."""
import pandas as pd
from agent1 import calendar_vn as cal
from agent1.rules import all_rules
from agent1.rules.provisioning import suggest_provision


def cases():
    rows=[]
    def add(rule,operation,arguments,expected):
        rows.append(dict(case=f'{rule}:{len(rows)+1}',rule=rule,operation=operation,arguments=arguments,expected=expected))
    for date,first,last in [('2019-01-01',4180000,2920000),('2020-01-01',4420000,3070000),
        ('2022-07-01',4680000,3250000),('2024-07-01',4960000,3450000),('2026-01-01',5310000,3700000)]:
        for region,amount in [(1,first),(4,last)]:add('minimum_wage@'+date,'wage',[date,region],amount)
    for start,before,end,prior in [('2022-02-01','2022-01-31','2022-12-31',.1),
        ('2023-07-01','2023-06-30','2023-12-31',.1),('2024-01-01','2023-12-31','2024-06-30',.08),
        ('2024-07-01','2024-06-30','2024-12-31',.08),('2025-01-01','2024-12-31','2025-06-30',.08),
        ('2025-07-01','2025-06-30','2026-12-31',.08)]:
        add('vat_reduction@'+start,'vat',[before,'textile_clothing'],prior)
        add('vat_reduction@'+start,'vat',[end,'textile_clothing'],.08)
    for date in ['2021-06-01','2023-04-01']:add('vat_base@2018-01-01','vat',[date,'textile_clothing'],.1)
    for date in ['2022-06-01','2025-06-01']:add('vat_excluded_industries@2018-01-01','vat',[date,'steel_metals'],.1)
    for gross,employer,net in [(100000000,21500000,89500000),(200000000,43000000,179000000)]:
        add('social_insurance_employer@2018-01-01','employer',[gross],employer)
        add('social_insurance_employee@2018-01-01','net_payroll',[gross],net)
    for revenue,count in [(50000000000,0),(50000000001,1)]:
        add('monthly_vat_threshold@2018-01-01','vat_count',[revenue],count)
    for end,due in [('2024-03-31','2024-04-22'),('2025-01-31','2025-02-20')]:
        add('vat_monthly_day@2018-01-01','vat_due',[end],due)
    for end,due in [('2024-03-31','2024-05-02'),('2024-06-30','2024-07-30')]:
        add('cit_provisional_day@2018-01-01','cit_due',[end],due)
    for year,due in [(2023,'2024-04-01'),(2024,'2025-03-31')]:
        add('cit_final_month@2018-01-01','cit_final',[year],due)
    for year,due in [(2023,'2023-01-30'),(2024,'2024-01-30')]:
        add('license_fee_day@2018-01-01','license_due',[year],due)
    for kind,values in [('license_fee_capital_threshold',[(10000000000,2000000),(10000000001,3000000)]),
        ('license_fee_low',[(0,2000000),(9000000000,2000000)]),
        ('license_fee_high',[(11000000000,3000000),(20000000000,3000000)])]:
        for capital,amount in values:add(kind+'@2018-01-01','license_amount',[2025,capital],amount)
    for year,amount in [(2025,2000000),(2026,0)]:
        add('license_fee_abolished@2018-01-01','license_amount',[year,1000000000],amount)
    for date,days in [('2024-02-09',1),('2025-01-30',-1)]:add('lunar_new_year@2018-01-01','tet_days',[date],days)
    for date,flag in [('2024-02-08',True),('2024-02-15',False)]:add('tet_break@2018-01-01','tet_break',[date],flag)
    for months,amount in [(5,0),(6,30000000)]:add('provisioning_months@2018-01-01','provision',[months],amount)
    return rows


def calculate(case):
    operation=case['operation'];args=case['arguments']
    if operation=='wage':return cal.min_wage(*args)
    if operation=='vat':return cal.vat_rate(*args)
    if operation in {'employer','net_payroll'}:
        gross=args[0]
        schedule=cal.obligation_schedule(dict(payroll_gross=gross,payroll_lag_month=0,payday=15),
            '2024-06-01','2024-06-30')
        net=schedule.loc[schedule.category=='payroll_net','amount'].sum()
        return net if operation=='net_payroll' else schedule.loc[schedule.category=='social_insurance','amount'].sum()-(gross-net)
    if operation=='vat_count':
        schedule=cal.obligation_schedule(dict(revenue_prev_year=args[0]),'2024-06-01','2024-06-30')
        return int(schedule.category.eq('vat').sum())
    if operation in {'license_amount'}:
        year,capital=args
        schedule=cal.obligation_schedule(dict(charter_capital=capital),f'{year}-01-01',f'{year}-02-15')
        return schedule.loc[schedule.category=='license_fee','amount'].sum()
    if operation=='tet_days':return cal.days_to_tet(*args)
    if operation=='tet_break':return cal.in_tet_break(*args)
    if operation=='provision':
        due=pd.Timestamp('2020-02-29')
        invoices=pd.DataFrame(dict(issue_date=[due],due_date=[due],amount_gross=[100000000.]))
        return float(suggest_provision(invoices,due+pd.DateOffset(months=args[0])).provision_floor_amount.iloc[0])
    dates={'vat_due':lambda:cal.vat_deadline(args[0],True),'cit_due':lambda:cal.cit_provisional_deadline(args[0]),
        'cit_final':lambda:cal.cit_final_deadline(args[0]),'license_due':lambda:cal.license_fee_deadline(args[0])}
    if operation not in dates:raise ValueError('Tình huống không hỗ trợ')
    return str(dates[operation]().date())


def coverage():
    frame=pd.DataFrame(cases())
    expected={r['kind']+'@'+r['effective_from'] for r in all_rules()}
    counts=frame.groupby('rule').size().to_dict()
    if set(counts)!=expected or min(counts.values())<2:raise ValueError('Thiếu hai tình huống cho quy tắc cấu hình')
    return counts
