"""Phân tích pilot từ số quan sát; không thay số thật bằng giả định kinh tế."""
import numpy as np
import pandas as pd
from agent1.eval.cluster import mean_ci


def economic_metrics(invoices,cash,*,period_start,period_end,annual_credit_sales=None,
                     finance_cost=None,accounting_hours=None,auto_matched_share=None,
                     optimal_buffer=None,interest_rate=None):
    start,end=pd.Timestamp(period_start),pd.Timestamp(period_end)
    inv=invoices[invoices.issue_date.between(start,end)&(invoices.term_days>0)].copy()
    paid=inv[inv.paid_date.notna()&(inv.paid_date<=end)]
    weight=paid.amount_gross.to_numpy()
    delay=(paid.paid_date-paid.due_date).dt.days.clip(lower=0).to_numpy()
    k1=float(np.average(delay,weights=weight)) if weight.sum()>0 else np.nan
    c=cash[cash.date.between(start,end)].sort_values('date')
    negative=c.balance<0
    n_events=int((negative&~negative.shift(fill_value=False)).sum())
    writeoffs=inv.loc[inv.writeoff_date.notna()&(inv.writeoff_date<=end),'amount_gross'].sum() if 'writeoff_date' in inv else np.nan
    result={'K1_value_weighted_delay_days':k1,'K2_receivables_held':annual_credit_sales/365*k1 if annual_credit_sales is not None else np.nan,
            'K3_minimum_buffer':np.nan,'K4_shortfall_events':n_events,'K5_finance_cost':finance_cost,
            'K6_bad_debt_rate':writeoffs/inv.amount_gross.sum() if inv.amount_gross.sum()>0 else np.nan,
            'K7_accounting_hours':accounting_hours,'K8_auto_match_share':auto_matched_share,
            'K9_idle_cash_opportunity_cost':max(0,c.balance.mean()-optimal_buffer)*interest_rate if
                len(c) and optimal_buffer is not None and interest_rate is not None else np.nan,
            'days_observed':(end-start).days+1,'n_paid_invoices':len(paid),'n_credit_invoices':len(inv),
            'evidence_type':'observational_pilot_not_causal'}
    return result


def difference_in_differences(panel,metric,*,bootstrap_n=300,seed=7):
    required={'firm_id','treated','period',metric}
    if not required<=set(panel):raise ValueError('Thiếu cột panel DiD')
    table=panel.pivot_table(index=['firm_id','treated'],columns='period',values=metric,aggfunc='mean')
    if not {'pre','post'}<=set(table):raise ValueError('Cần đủ kỳ pre/post')
    table=table.dropna(subset=['pre','post']).reset_index()
    delta=(table.post-table.pre).to_numpy();treated=table.treated.astype(bool).to_numpy()
    if not treated.any() or treated.all():raise ValueError('Cần cả nhóm dùng và nhóm đối chứng')
    rng=np.random.default_rng(seed);values=[]
    a,b=delta[treated],delta[~treated]
    for _ in range(bootstrap_n):values.append(rng.choice(a,len(a)).mean()-rng.choice(b,len(b)).mean())
    return dict(metric=metric,DiD=float(a.mean()-b.mean()),ci_low=float(np.quantile(values,.025)),
                ci_high=float(np.quantile(values,.975)),bootstrap_n=bootstrap_n,n_firms=len(table),
                meets_six_firm_design=len(table)>=6,causal_claim=False)
