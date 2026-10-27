"""Đo mục tiêu riêng từng hard case; qua contract chưa đồng nghĩa đúng nghiệp vụ."""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT
from agent1.synth.hard_cases import CASES
from agent1.calendar_vn import roll_forward_np


def main():
    parser=argparse.ArgumentParser()
    version=parser.add_mutually_exclusive_group()
    version.add_argument('--v3-smoke',action='store_true')
    version.add_argument('--v3-full',action='store_true')
    args=parser.parse_args()
    rows=[]
    def record(case,metric,value,low,high,limitation=''):
        rows.append(dict(case=case,metric=metric,value=float(value),target_low=low,target_high=high,
            point_target_met=bool(low<=value<=high),limitation=limitation,measurement_version='hard-case-observed-fidelity-v1'))
    for case in CASES:
        if args.v3_smoke:
            suffix='v3_steel_smoke' if case=='supply_shock' else 'v3_smoke'
            directory=SYNTH/f'hc_{case}_{suffix}'
        elif args.v3_full:
            directory=SYNTH/f'hc_{case}_v3'
        else:
            revised=SYNTH/f'hc_{case}_v2'
            directory=revised if (revised/'hard_case_complete.txt').exists() else SYNTH/f'hc_{case}'
        inv=pd.read_parquet(directory/'invoices.parquet')
        if case=='lumpy_customer':
            cust=pd.read_parquet(directory/'customers.parquet');anchors=set(cust.loc[cust.is_anchor,'customer_id'])
            share=inv[inv.customer_id.isin(anchors)].groupby('firm_id').amount_gross.sum()/inv.groupby('firm_id').amount_gross.sum()
            record(case,'firms_with_anchor_revenue_share_40_60',share.between(.4,.6).mean(),1,1,'Tỷ trọng doanh thu thực hiện, không chỉ trọng số sinh')
        elif case=='group_payer':
            bank=pd.read_parquet(directory/'bank_txns.parquet');known=bank.payer_group_id.notna()&bank.true_customer_id.notna()
            record(case,'different_group_payer_share',bank.loc[known,'payer_group_id'].ne(bank.loc[known,'true_customer_id']).mean(),.01,1,'Chưa đo lại recall T9 trên hard case')
        elif case=='heterogeneity':
            h=inv[inv.paid_date_true.notna()].copy();h['delay']=(h.paid_date_true-h.due_date).dt.days.clip(-60,240)
            firm_mean=h.groupby('firm_id').delay.transform('mean');customer_mean=h.groupby(['firm_id','customer_id']).delay.transform('mean')
            eta=((customer_mean-firm_mean)**2).sum()/max(((h.delay-firm_mean)**2).sum(),1e-9)
            record(case,'customer_between_variance_share',eta,.55,.65,'ANOVA mô tả trên nhãn thật tổng hợp; chưa chứng minh nhân quả')
        elif case=='cod_realistic':record(case,'COD_invoice_count_share',inv.term_days.eq(0).mean(),.2,.3)
        elif case=='discount_early':
            selected=inv.discount_taken.fillna(False)
            record(case,'discounted_invoices_with_net30_terms',inv.loc[selected,'term_days'].eq(30).mean(),1,1)
            expected=roll_forward_np((inv.loc[selected,'issue_date']+pd.Timedelta(days=10)).to_numpy())
            paid=inv.loc[selected,'paid_date_true'].to_numpy().astype('datetime64[D]')
            record(case,'discounted_invoices_paid_on_business_day_10',np.mean(paid==expected.astype('datetime64[D]')),1,1)
            paid_fraction=inv.loc[selected,'paid_amount']/inv.loc[selected,'amount_gross']
            record(case,'discounted_paid_fraction_mean',paid_fraction.mean(),.9799,.9801,'Làm tròn nghìn VND')
        elif case=='retention':
            held=inv[inv.retention_amount>0]
            record(case,'retained_fraction_mean',(held.retention_amount/held.amount_gross).mean(),.0499,.0501,'Kịch bản tổng hợp; cần lịch hợp đồng thật')
        elif case=='fx':
            record(case,'USD_invoice_count_share',inv.original_currency.eq('USD').mean(),.12,.18,'Tỷ giá tổng hợp, sổ quy về VND')
            error=np.max(np.abs(inv.amount_foreign*inv.fx_rate_at_issue-inv.amount_gross)/inv.amount_gross)
            record(case,'relative_currency_conversion_error',error,0,1e-10)
        elif case=='credit_note':
            refs=inv.adjusts_invoice_id.dropna()
            record(case,'adjustment_references_present_in_invoice_chain',refs.isin(inv.invoice_id).mean(),1,1,'Hiện chỉ đổi mã/tham chiếu thay thế; chưa giữ đủ bản gốc, huỷ, điều chỉnh')
        elif case=='verbal':
            shares=inv.groupby('customer_id').verbal_extension_days.max().gt(0)
            record(case,'customers_with_verbal_extension',shares.mean(),.12,.18)
            promises=pd.read_parquet(directory/'promises.parquet')
            record(case,'unrecorded_extension_invoices_with_recorded_promise',promises.invoice_id.isin(inv.loc[inv.verbal_extension_days>0,'invoice_id']).mean(),0,0)
        elif case=='supply_shock':
            events=pd.read_parquet(directory/'events.parquet');events=events[events.type=='sector_supply_disruption']
            firms=pd.read_parquet(directory/'firms.parquet').set_index('firm_id')
            localized=len(events)>0 and firms.loc[events.firm_id,'industry'].eq('steel_metals').all()
            record(case,'sector_localization_implemented',int(localized),1,1,'Cần thêm đánh giá tác động T6/T7')
            if args.v3_smoke or args.v3_full:
                stock=pd.read_parquet(directory/'inventory_weekly.parquet')
                steel=stock[stock.firm_id.isin(firms[firms.industry.eq('steel_metals')].index)]
                active=steel[steel.week.between('2022-10-03','2022-11-21')]
                affected=active.groupby('firm_id').agg(
                    capacity_weeks=('supply_capacity',lambda x:x.lt(1).sum()),
                    cost_weeks=('input_cost_index',lambda x:x.gt(1).sum()))
                record(case,'min_active_weeks_with_capacity_loss',affected.capacity_weeks.min(),8,8)
                record(case,'min_active_weeks_with_input_cost_increase',affected.cost_weeks.min(),8,8)
                record(case,'active_booked_to_demand_ratio',active.booked_orders.sum()/active.demand_orders.sum(),0,.999)
        elif case=='seasonal_extreme':
            focus=inv.issue_date.dt.month.isin([1,8,11,12])
            record(case,'revenue_in_four_focus_months',inv.loc[focus,'amount_gross'].sum()/inv.amount_gross.sum(),.57,.63)
        elif case=='new_company':
            spans=inv.groupby('firm_id').issue_date.agg(['min','max'])
            record(case,'max_observed_history_days',(spans['max']-spans['min']).dt.days.max(),0,365)
        for row in rows:
            if row['case']==case:row['world']=directory.name
    output=('hard_case_fidelity_v3_smoke.csv' if args.v3_smoke else
            'hard_case_fidelity_v3_full.csv' if args.v3_full else 'hard_case_fidelity.csv')
    pd.DataFrame(rows).to_csv(OUT/'data'/output,index=False)


if __name__=='__main__':main()
