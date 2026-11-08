"""ML-II của mô hình Normal–Normal trên lịch sử đã tất toán tại nguồn."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from .features import SnapshotBuilder


def estimate_k(history):
    grouped=history.groupby(['firm_id','customer_id']).delay.agg(['count','mean','var'])
    if len(grouped)<5 or (grouped['count']-1).sum()<5:
        return dict(k=4.,status='insufficient_history',n_customers=len(grouped))
    n=grouped['count'].to_numpy();mean=grouped['mean'].to_numpy()
    within=(grouped['var'].fillna(0)*(grouped['count']-1)).to_numpy()
    sigma=max(within.sum()/max((n-1).sum(),1),.01)
    tau=max(mean.var()-sigma*np.mean(1/n),.01)
    def objective(logvar):
        s,t=np.exp(logvar);variance=t+s/n;mu=np.sum(mean/variance)/np.sum(1/variance)
        return .5*np.sum((n-1)*np.log(s)+within/s+np.log(variance)+(mean-mu)**2/variance)
    result=minimize(objective,np.log([sigma,tau]),method='L-BFGS-B',bounds=[(-10,20)]*2)
    if not result.success:raise ValueError('ML-II chưa hội tụ: '+result.message)
    sigma,tau=np.exp(result.x)
    return dict(k=float(np.clip(sigma/tau,.1,100)),sigma2=float(sigma),tau2=float(tau),
                n_customers=len(grouped),n_observations=int(n.sum()),status='fit_source_only')


def learn_industry_k(invoices,firms,label_end):
    end=pd.Timestamp(label_end)
    history=invoices[(invoices.issue_date<=end)&(invoices.paid_date_true<=end)].copy()
    history['delay']=(history.paid_date_true-history.due_date).dt.days.clip(-60,240)
    history['delay']-=history.groupby('firm_id').delay.transform('mean')
    industries=firms.set_index('firm_id').industry
    history['industry']=history.firm_id.map(industries)
    result={'global':estimate_k(history)}
    for industry,group in history.groupby('industry'):result[industry]=estimate_k(group)
    return result


def apply_learned_eb(frame,learned,firm_industries):
    frame=frame.copy()
    if frame.empty:return frame
    industry=frame.firm_id.map(firm_industries)
    k=industry.map({name:value['k'] for name,value in learned.items()}).fillna(learned['global']['k'])
    n=frame.c_n_hist.fillna(0)
    frame['c_delay_eb']=(n*frame.c_delay_mean.fillna(0)+k*frame.f_delay_mean.fillna(0))/(n+k)
    return frame


class EBSnapshotBuilder(SnapshotBuilder):
    def __init__(self,*args,learned,firm_industries,**kwargs):
        super().__init__(*args,**kwargs);self.learned=learned;self.firm_industries=firm_industries

    def snapshot(self,T,visible_from=None,firms=None):
        frame=super().snapshot(T,visible_from=visible_from,firms=firms)
        return apply_learned_eb(frame,self.learned,self.firm_industries)
