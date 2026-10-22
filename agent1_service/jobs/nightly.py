"""Pipeline vận hành từ bảng quan sát được; mô hình thử nghiệm khi chưa đủ cổng."""
import time
import numpy as np
import pandas as pd
from agent1 import api_surface as api
from agent1.models.t4_revenue import GlobalQuantileLGBM, make_rows
from agent1.models.t1 import b1_dist
from agent1.models.t6_cash import K


def run(invoices,bank,customers,promises,outflows,cutoff,balance, *, seed=7,model_cache=None,evaluation_label_mode='reconciled',
        aci_state=None):
    """aci_state: trạng thái ACI của doanh nghiệp (dict, {} cho lần đầu). Có thì dải công bố là copula-t + ACI và
    result['aci_state'] là trạng thái mới cần lưu; None giữ dải copula-t gốc (cho script nghiên cứu cũ)."""
    start=time.monotonic(); T=pd.Timestamp(cutoff)
    inv=invoices[invoices.issue_date<=T].copy()
    observed_bank=bank[bank.value_date<=T].copy()
    rec=api.Reconciler()
    if model_cache is not None and 'offline_links' in model_cache:
        links=model_cache['offline_links']
        links=links[links.est_pay_date<=T]
        queue=model_cache['offline_queue']
        queue=queue[queue.txn_id.isin(observed_bank.txn_id)]
    else:
        links,queue=rec.reconcile(observed_bank,inv,customers)
    labelled=api.build_bank_labels(inv,links)
    if evaluation_label_mode=='truth':
        labelled['paid_date_est']=inv['paid_date_true']
    elif evaluation_label_mode=='ledger':
        labelled['paid_date_est']=inv['ledger_clear_date']
    elif evaluation_label_mode!='reconciled':
        raise ValueError('evaluation_label_mode không hợp lệ')
    labelled['writeoff_date']=pd.NaT
    builder=api.SnapshotBuilder(labelled,links,promises,label_col='paid_date_est')
    cal_start=T-pd.Timedelta(days=183)
    cuts=pd.date_range(max(inv.issue_date.min()+pd.Timedelta(days=60),T-pd.Timedelta(days=730)),cal_start-pd.Timedelta(days=1),freq='14D')
    cached=model_cache is not None and 't1' in model_cache
    train=builder.build(cuts,label_end=cal_start) if not cached else pd.DataFrame()
    snapshot=builder.snapshot(T)
    if snapshot.empty:
        raise ValueError('Không có hoá đơn mở tại cutoff')
    snapshot['amount_open']=snapshot.amount_gross*(1-snapshot.paid_frac_so_far.fillna(0))
    trained=cached and model_cache['t1'] is not None
    if trained:
        model=model_cache['t1'];P,_=api.pmf_from_hazard(model.hazards(snapshot))
    elif not cached and len(train)>=100 and train.event.nunique()>1:
        model=api.HazardGBM(dict(min_data_in_leaf=30,num_leaves=31),rounds=200).fit(train)
        P,_=api.pmf_from_hazard(model.hazards(snapshot)); trained=True
    else:
        from agent1.models.t1 import cdf_from_quantiles
        F=cdf_from_quantiles(b1_dist(snapshot)); P=np.diff(np.c_[np.zeros(len(F)),F],axis=1)
    if model_cache is not None and not cached:model_cache['t1']=model if trained else None
    weekly=inv.assign(week=inv.issue_date.dt.to_period('W-MON').dt.start_time).groupby('week').amount_gross.sum()
    if len(weekly):
        weekly=weekly.reindex(pd.date_range(weekly.index.min(),weekly.index.max(),freq='7D'),fill_value=0.)
    completed=weekly[weekly.index+pd.Timedelta(days=6)<=T]
    rq=None
    if len(completed)>=40:
        X,y,_=make_rows(completed.to_numpy(),completed.index,True,list(range(20,len(completed)-13)))
        if len(X):
            if model_cache is not None and model_cache.get('t4') is not None:model4=model_cache['t4']
            else:
                model4=GlobalQuantileLGBM(rounds=200).fit(X,y)
                if model_cache is not None:model_cache['t4']=model4
            weeks=pd.date_range(completed.index[0],periods=len(completed)+13,freq='7D')
            Xf,_,meta=make_rows(completed.to_numpy(),weeks,True,[len(completed)-1],with_target=False)
            rq=model4.predict(Xf)*meta[:,2:3]
    ko=np.zeros(K)
    if len(outflows):
        history=outflows[(outflows.date<=T)&(outflows.date>T-pd.Timedelta(days=91))]
        ko[:]=history.amount.sum()/13
        # Chỉ các khoản có ngày nhận biết rõ ràng mới được thay lịch chi dự báo.
        if 'known_at' in outflows:
            known=outflows[(outflows.known_at<=T)&(outflows.date>T)]
            for k in range(K):
                vals=known[(known.date>T+pd.Timedelta(days=7*k))&(known.date<=T+pd.Timedelta(days=7*(k+1)))].amount
                ko[k]=max(ko[k],vals.sum())
    kernel=api.collection_kernel(labelled,T,label_col='paid_date_est')
    args=dict(open_df=snapshot,P=P,B0=float(balance),known_out=ko,rev_q=rq,kernel=kernel,
              capex_rate=0.,capex_sizes=[],n=1000,rho=.15,seed=seed)
    samples,_=api.simulate(**args)
    band=np.quantile(samples,[.1,.5,.9],axis=0).T
    rows=[dict(week=k+1,P10=float(band[k,0]),P50=float(band[k,1]),P90=float(band[k,2])) for k in range(K)]
    band_extra={}
    if aci_state is not None:
        from .aci_band import update as aci_update,band as aci_band
        state,aci=aci_update(aci_state,T,balance)
        raw_rows=rows;rows,meta=aci_band(state,aci,T,samples)
        band_extra=dict(meta,band_raw=raw_rows,aci_state=state)
    ranked=api.rank_collections(snapshot,P,args,top_n=10)
    if len(ranked):ranked['customer_id']=ranked.invoice_id.map(snapshot.set_index('invoice_id').customer_id)
    result=dict(cutoff=str(T.date()),band=rows,shortfall_4w=float((samples[:,:4].min(1)<0).mean()),
        shortfall_13w=float((samples.min(1)<0).mean()),collections=ranked.to_dict('records'),
        auto_txn_coverage=links.txn_id.nunique()/max(len(observed_bank),1),review_count=len(queue),
        model='tenant-HazardGBM' if trained else 'B1d-fallback',seconds=time.monotonic()-start,
        evidence_type='experimental_observed_data_pipeline',seed=seed,**band_extra)
    return result,args
