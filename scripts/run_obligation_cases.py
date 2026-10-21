"""Xuất bằng chứng phép tính T5 mở rộng từ tình huống hồ sơ, không xác nhận luật."""
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT
from agent1.rules.obligations import extended_schedule,rent_events,loan_events,weekly_extended_cash


def main():
    rows=[]
    def record(case,actual,expected):
        rows.append(dict(case=case,actual=float(actual),expected=float(expected),passed=abs(actual-expected)<1e-6,
            evidence_type='configured_contract_arithmetic_not_legal_validation',expert_verified=False))
    base=dict(known_at='2025-01-01',source='Hồ sơ thử cấu hình',due_date='2025-02-08',amount=100.)
    kwargs=dict(asof='2025-02-01',start='2025-02-01',end='2025-03-31')
    for category in ['pit_withholding','foreign_contractor_tax','salary_bonus','rent_contract','loan_interest','loan_principal']:
        frame=extended_schedule([dict(base,obligation_id=category,category=category)],**kwargs)
        record(category+'_declared_amount',frame.amount.sum(),100.)
    for approval,expected in [(None,0),('2025-03-01',0),('2025-01-15',100)]:
        frame=extended_schedule([dict(base,obligation_id='refund',category='vat_refund',refund_approved_at=approval)],**kwargs)
        record('refund_approval_'+str(approval),frame.amount.sum(),expected)
    steps=[dict(effective_from='2025-01-01',effective_to='2025-02-28',amount=100),dict(effective_from='2025-03-01',amount=150)]
    events=rent_events('rent',steps,months=['2025-02','2025-03'],due_day=31,known_at='2025-01-01',source='HĐ thử',business_day='none')
    for month,row,amount,day in zip(['feb','mar'],events,[100.,150.],[28,31]):
        record('rent_'+month+'_amount',row['amount'],amount);record('rent_'+month+'_day',row['due_date'].day,day)
    loans=loan_events('loan',[dict(date='2025-02-08',principal=1000,interest=70)],known_at='2025-01-01',source='Lịch tín dụng thử')
    frame=extended_schedule(loans,**kwargs)
    record('loan_principal_separate',frame.loc[frame.category=='loan_principal','amount'].sum(),1000)
    record('loan_interest_separate',frame.loc[frame.category=='loan_interest','amount'].sum(),70)
    refund=dict(base,obligation_id='refund',category='vat_refund',refund_approved_at='2025-01-15',amount=300)
    frame=extended_schedule([*loans,refund],**kwargs);inflow,outflow=weekly_extended_cash(frame,'2025-02-01')
    record('week1_refund_inflow',inflow[0],300);record('week1_principal_plus_interest_outflow',outflow[0],1070)
    future=dict(base,obligation_id='future',category='salary_bonus',known_at='2025-02-10',amount=999)
    record('future_agreement_excluded',extended_schedule([future],**kwargs).amount.sum(),0)
    directory=OUT/'rules';directory.mkdir(exist_ok=True)
    result=pd.DataFrame(rows);result.to_csv(directory/'extended_obligation_cases.csv',index=False)
    (directory/'extended_obligation_protocol.json').write_text(json.dumps(dict(complete=True,n_cases=len(result),
        all_passed=bool(result.passed.all()),scope='configured events and contract cash schedules; no tax amount or refund processing-time inference',
        integration='standalone schedule plus weekly cash arrays; does not alter existing research forecasts',expert_verified=False),indent=2),encoding='utf-8')
    print(f'{int(result.passed.sum())}/{len(result)} configured obligation cases passed')
    if not result.passed.all():raise ValueError('Tình huống nghĩa vụ không khớp')


if __name__=='__main__':main()
