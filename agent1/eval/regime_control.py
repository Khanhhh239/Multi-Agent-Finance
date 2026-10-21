"""T7→T6: chỉ cập nhật bằng quan sát đã đến hạn; ngưỡng chọn trên nguồn trước test."""
import numpy as np
import pandas as pd
from agent1.models.t6_cash import ACI


def payment_residual(snapshot,probabilities,reveal_at):
    cuts=snapshot.cutoff.unique()
    if len(cuts)!=1:raise ValueError('Cần một cutoff duy nhất')
    cutoff=pd.Timestamp(cuts[0]);reveal_at=pd.Timestamp(reveal_at)
    if reveal_at<cutoff+pd.Timedelta(days=7):raise ValueError('Kết quả tuần chưa đến hạn quan sát')
    p=np.asarray(probabilities,float)
    actual=((snapshot.label_date>cutoff)&(snapshot.label_date<=cutoff+pd.Timedelta(days=7))).to_numpy(float)
    return float((p.sum()-actual.sum())/np.sqrt(np.sum(p*(1-p))+1.))


class PortfolioCUSUM:
    def __init__(self,h=6.,k=.5,cooldown_days=28):
        self.h,self.k,self.cooldown=h,k,cooldown_days;self.total=0.;self.last=None

    def update(self,date,residual):
        date=pd.Timestamp(date);self.total=max(0.,self.total+float(residual)-self.k)
        alarm=self.total>self.h and (self.last is None or (date-self.last).days>=self.cooldown)
        if alarm:self.total=0.;self.last=date
        return bool(alarm)


def calibrate_portfolio(streams,max_false_per_year=.5):
    rows=[]
    for h in [2.,3.,4.,6.,8.,12.]:
        count=0;years=0.
        for _,part in streams.groupby('firm_id'):
            part=part.sort_values('date');detector=PortfolioCUSUM(h)
            count+=sum(detector.update(row.date,row.residual) for row in part.itertuples(index=False))
            years+=((part.date.max()-part.date.min()).days+7)/365.25
        rate=count/max(years,1e-12)
        rows.append(dict(h=h,false_alarms_per_firm_year=rate,exposure_firm_years=years,n_alarms=count))
    frame=pd.DataFrame(rows);valid=frame[frame.false_alarms_per_firm_year<=max_false_per_year]
    chosen=float(valid.h.iloc[0]) if len(valid) else None
    frame['chosen']=frame.h.eq(chosen) if chosen is not None else False
    return chosen,frame


class DelayedACI:
    def __init__(self,gamma=.01):
        self.aci=ACI(gamma=gamma);self.pending=[]

    def add(self,cutoff,k,lo,hi,truth):
        self.pending.append((pd.Timestamp(cutoff)+pd.Timedelta(days=7*(k+1)),k,lo,hi,truth))

    def reveal(self,date):
        date=pd.Timestamp(date);future=[]
        for end,k,lo,hi,truth in self.pending:
            if end<=date:self.aci.update(k,not lo<=truth<=hi)
            else:future.append((end,k,lo,hi,truth))
        self.pending=future


def remove_common_customer_residual(frame):
    result=frame.copy()
    grouped=result.groupby(['firm_id','date'])
    result['_weighted']=result.residual*result.weight
    total=result.groupby(['firm_id','date'])._weighted.transform('sum')
    weights=grouped.weight.transform('sum')-result.weight
    common=(total-result._weighted)/weights.where(weights>0)
    result['common_from_other_customers']=common.fillna(0.)
    result['conditional_residual']=result.residual-result.common_from_other_customers
    return result.drop(columns='_weighted')
