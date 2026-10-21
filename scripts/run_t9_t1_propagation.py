"""G18: cùng nguồn/ngân sách, nhãn T9/sổ/NH; chấm tiền thật sau dự báo."""
import gc
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from agent1.paths import OUT,SYNTH
from agent1.models.t1 import HazardGBM,pmf_from_hazard
from agent1.eval.cluster import ratio_ci
from run_t1 import snapshots,censor
from run_e2e_protocol import observed_promises


def prepare_ledger():
    source=SYNTH/'e2e_observed_tgt';target=SYNTH/'e2e_ledger_tgt';target.mkdir(exist_ok=True)
    inv=pd.read_parquet(source/'invoices.parquet')
    original=pd.read_parquet(SYNTH/'tgt/invoices.parquet').set_index('invoice_id')
    inv['paid_date_true']=inv.invoice_id.map(original.ledger_clear_date)
    inv.to_parquet(target/'invoices.parquet',index=False)
    # Phân bổ theo ID trên sổ, không sử dụng ID hoá đơn thật của khoản tiền.
    pay=pd.read_parquet(SYNTH/'tgt/payments.parquet',columns=['ledger_invoice_id','ledger_post_date','amount','kind'])
    pay=pay.rename(columns={'ledger_invoice_id':'invoice_id','ledger_post_date':'pay_date_true'})
    pay=pay[pay.invoice_id.isin(inv.invoice_id)];pay.to_parquet(target/'payments.parquet',index=False)
    prom=pd.read_parquet(source/'promises.parquet')
    observed_promises(prom,inv,pay.rename(columns={'pay_date_true':'est_pay_date'})).to_parquet(target/'promises.parquet',index=False)
    return target.name


def realized_cash(invoices,payments,cutoffs,firms):
    truth=payments[['invoice_id','pay_date_true','amount']].merge(invoices[['invoice_id','firm_id','issue_date']],on='invoice_id')
    fi={firm:i for i,firm in enumerate(firms)};result={}
    for cutoff in cutoffs:
        visible=truth[(truth.issue_date<=cutoff)&(truth.issue_date>=pd.Timestamp('2023-07-01'))&
            (truth.pay_date_true>cutoff)&(truth.pay_date_true<=cutoff+pd.Timedelta(days=91))]
        week=np.ceil((visible.pay_date_true-cutoff).dt.days/7).astype(int)-1
        cash=np.zeros((len(firms),13))
        np.add.at(cash,(visible.firm_id.map(fi).to_numpy(),week.to_numpy()),visible.amount.to_numpy())
        result[cutoff]=cash
    return result


def main():
    origin=pd.Timestamp('2024-07-01');visible=pd.Timestamp('2023-07-01');label_end=origin-pd.Timedelta(days=183)
    protocol=json.loads((OUT/'e2e/protocol/input_protocol.json').read_text(encoding='utf-8'))
    if protocol['n_firms']!=14:raise ValueError('Cần E2E đầy đủ trước thí nghiệm F')
    ledger=prepare_ledger()
    train=censor(snapshots('src',pd.date_range('2019-07-01',label_end-pd.Timedelta(days=7),freq='14D'),tag='variants_training'),label_end)
    train=train.sample(min(len(train),40000),random_state=7)
    base=HazardGBM(rounds=300).fit(train);del train;gc.collect()
    cuts=pd.date_range(origin,periods=52,freq='7D')
    firms=pd.read_parquet(SYNTH/'tgt/firms.parquet').firm_id.tolist()
    inv=pd.read_parquet(SYNTH/'tgt/invoices.parquet');pay=pd.read_parquet(SYNTH/'tgt/payments.parquet')
    truth=realized_cash(inv,pay,cuts,firms);del inv,pay;gc.collect()
    rows=[];company_rows=[]
    for mode,world in [('T9_estimated','e2e_observed_tgt'),('bank_oracle','e2e_oracle_tgt'),('ledger_observed',ledger)]:
        history=censor(snapshots(world,pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='7D'),
            visible_from=visible,tag='propagation_train'),origin)
        history=history.sample(min(len(history),40000),random_state=7)
        model=HazardGBM(dict(learning_rate=.02),rounds=150).fit(history,init_model=base.booster)
        n_train=len(history);del history;gc.collect()
        test=censor(snapshots(world,cuts,visible_from=visible,tag='propagation_test'),'2025-12-31')
        P,_=pmf_from_hazard(model.hazards(test));predicted=P*test.amount_open.to_numpy()[:,None]
        indexes={firm:i for i,firm in enumerate(firms)};errors=[]
        for cutoff in cuts:
            mask=test.cutoff.eq(cutoff).to_numpy();prediction=np.zeros((len(firms),13))
            np.add.at(prediction,test.loc[mask,'firm_id'].map(indexes).to_numpy(),predicted[mask])
            # Công ty/HĐ không được trạng thái nhãn coi còn mở có dự báo thu = 0.
            errors.append((np.abs(prediction-truth[cutoff]),truth[cutoff]))
        error=np.stack([e for e,_ in errors]);actual=np.stack([a for _,a in errors])
        for horizon,section in [('w1-4',slice(0,4)),('w5-13',slice(4,13))]:
            numerator=error[:,:,section].sum((0,2));denominator=actual[:,:,section].sum((0,2))
            ci=ratio_ci(numerator,denominator)
            rows.append(dict(label_mode=mode,horizon=horizon,WAPE=numerator.sum()/denominator.sum(),
                WAPE_ci_low=ci['ci_low'],WAPE_ci_high=ci['ci_high'],bootstrap_n=300,n_firms=len(firms),weeks=52,
                n_target_train=n_train,source_budget=40000,target_budget=40000,truth_used_only_scoring=True,
                measurement_version='T9-T1-observed-cash-equal-budget-v1-fullweek',
                limitation='synthetic;observed_invoice_cohort_since_2023_07;state_and_partial_payment_errors_included'))
            for firm,num,den in zip(firms,numerator,denominator):company_rows.append(dict(label_mode=mode,horizon=horizon,firm_id=firm,error_sum=num,actual_sum=den))
        pd.DataFrame(rows).to_csv(OUT/'t1/T9_T1_error_propagation.csv',index=False)
        pd.DataFrame(company_rows).to_csv(OUT/'t1/T9_T1_company_cash_losses.csv',index=False)
        print(mode,'scored',flush=True);del test,P,predicted,model;gc.collect()
    frame=pd.DataFrame(rows);comparison=[]
    for horizon,group in frame.groupby('horizon'):
        values=group.set_index('label_mode').WAPE
        gap=abs(values.ledger_observed-values.bank_oracle)
        fraction=1-abs(values.T9_estimated-values.bank_oracle)/gap if gap>1e-12 else np.nan
        company=pd.DataFrame(company_rows);company=company[company.horizon==horizon]
        numerator=company.pivot(index='firm_id',columns='label_mode',values='error_sum')
        denominator=company.pivot(index='firm_id',columns='label_mode',values='actual_sum')
        rng=np.random.default_rng(7);index=rng.integers(len(numerator),size=(300,len(numerator)))
        boot={name:numerator[name].to_numpy()[index].sum(1)/denominator[name].to_numpy()[index].sum(1) for name in numerator}
        gaps=np.abs(boot['ledger_observed']-boot['bank_oracle']);valid=gaps>1e-12
        reductions=1-np.abs(boot['T9_estimated'][valid]-boot['bank_oracle'][valid])/gaps[valid]
        comparison.append(dict(horizon=horizon,bank_WAPE=values.bank_oracle,ledger_WAPE=values.ledger_observed,
            T9_WAPE=values.T9_estimated,distance_reduction_fraction=fraction,
            reduction_ci_low=float(np.quantile(reductions,.025)) if len(reductions) else np.nan,
            reduction_ci_high=float(np.quantile(reductions,.975)) if len(reductions) else np.nan,bootstrap_n=300,bootstrap_valid=int(valid.sum()),
            target_met=bool(fraction>=.5),measurement_version='T9-T1-observed-cash-equal-budget-v1-fullweek'))
    pd.DataFrame(comparison).to_csv(OUT/'t1/T9_T1_gap_reduction.csv',index=False)


if __name__=='__main__':main()
