"""Các nhánh T1 thử nghiệm, giữ mô hình mặc định và bộ đặc trưng gốc."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from scipy.stats import spearmanr

from . import t1
from .features import FEATURES

DAILY_FEATS=['d','dtd_d','business_day_d','tet_d','payrun_d','promise_d']


def expand_daily(frame,train=True,days=28):
    if not 1<=days<=28:raise ValueError('Số ngày phải trong 1–28')
    static=frame[FEATURES].to_numpy(dtype='float32');parts=[];labels=[]
    remaining=frame.remaining.to_numpy() if 'remaining' in frame else np.full(len(frame),np.inf)
    observed=frame.time_obs.to_numpy() if 'time_obs' in frame else np.full(len(frame),np.inf)
    event=frame.event.to_numpy() if 'event' in frame else np.zeros(len(frame))
    origin=(frame.cutoff.to_numpy().astype('datetime64[D]')-t1._DAY0).astype(int)
    for day in range(1,days+1):
        paid=(event==1)&(np.ceil(remaining)==day)
        mask=(observed>day-1)&(paid|(observed>=day)) if train else np.ones(len(frame),bool)
        if not mask.any():continue
        index=origin[mask]+day
        if index.min()<0 or index.max()>=len(t1._isbd):raise ValueError('Ngày dự báo ngoài lịch đã cấu hình')
        dtd=frame.days_to_due.to_numpy()[mask]-day
        dom=t1._DOM[index]
        top1=frame.top1.to_numpy()[mask] if 'top1' in frame else np.full(mask.sum(),np.nan)
        top2=frame.top2.to_numpy()[mask] if 'top2' in frame else np.full(mask.sum(),np.nan)
        payrun=np.where(np.isnan(top1),np.nan,(dom==top1)|(dom==top2))
        promise=frame.days_to_promised.to_numpy()[mask]
        extras=np.column_stack([np.full(mask.sum(),day),dtd,t1._isbd[index],t1._tet[index],payrun,
                                np.where(np.isnan(promise),np.nan,np.abs(promise-day)<=3)])
        parts.append(np.column_stack([static[mask],extras]).astype('float32'))
        if train:labels.append(paid[mask].astype('int8'))
    if not parts:raise ValueError('Không có ngày rủi ro quan sát được')
    return np.concatenate(parts),np.concatenate(labels) if train else None


class DailyEarlyHazard:
    def __init__(self,weekly,rounds=200):
        self.weekly,self.rounds=weekly,rounds

    def fit(self,train):
        X,y=expand_daily(train)
        self.booster=lgb.train(self.weekly.p,lgb.Dataset(X,y,feature_name=FEATURES+DAILY_FEATS),num_boost_round=self.rounds)
        return self

    def predict(self,frame,batch_size=2048):
        daily=[]
        for start in range(0,len(frame),batch_size):
            batch=frame.iloc[start:start+batch_size];X,_=expand_daily(batch,False)
            daily.append(self.booster.predict(X).reshape(28,len(batch)).T)
        D=np.clip(np.concatenate(daily),1e-7,1-1e-7)
        H=self.weekly.hazards(frame).copy()
        H[:,:4]=1-np.prod(1-D.reshape(len(frame),4,7),axis=2)
        Q=t1.quantiles_from_hazard(H);cdf=1-np.cumprod(1-D,axis=1)
        for i,row in enumerate(cdf):
            for j,alpha in enumerate(t1.QS):
                if alpha<=row[-1]:Q[i,j]=np.interp(alpha,np.r_[0.,row],np.arange(29))
        P,S=t1.pmf_from_hazard(H)
        return dict(Q=Q,P=P,cdf=1-S)


def due_component_labels(frame):
    end=frame.days_to_due.to_numpy()+3
    known=(frame.event.to_numpy()==1)|(frame.time_obs.to_numpy()>=np.maximum(end,0))
    positive=(frame.event.to_numpy()==1)&(np.abs(frame.remaining.to_numpy()-frame.days_to_due.to_numpy())<=3)
    return known,positive.astype(int)


class DueMixture:
    def __init__(self,weekly,rounds=300):
        self.weekly,self.rounds=weekly,rounds;self.calibrator=None

    def fit(self,train,calibration=None):
        known,y=due_component_labels(train)
        if known.sum()<100 or len(np.unique(y[known]))<2:raise ValueError('Chưa đủ nhãn thành phần đã quan sát')
        params=dict(self.weekly.p);params['num_leaves']=31
        self.gate=lgb.train(params,lgb.Dataset(train.loc[known,FEATURES].astype('float32'),y[known]),num_boost_round=self.rounds)
        rest=train[known&(y==0)]
        self.rest=t1.HazardGBM(rounds=self.rounds).fit(rest) if len(rest)>=100 and rest.event.nunique()>1 else self.weekly
        offset=(train.remaining-train.days_to_due)[known&(y==1)].round().astype(int)
        counts=offset.value_counts().reindex(range(-3,4),fill_value=0).to_numpy()+1
        self.offset_prob=counts/counts.sum()
        if calibration is not None:
            eligible,target=due_component_labels(calibration)
            if eligible.sum()>=100 and len(np.unique(target[eligible]))==2:
                p=self.gate.predict(calibration.loc[eligible,FEATURES].astype('float32'))
                self.calibrator=IsotonicRegression(out_of_bounds='clip').fit(p,target[eligible])
        return self

    def on_time_pmf(self,frame):
        result=np.zeros((len(frame),13));denominator=np.zeros(len(frame))
        due=frame.days_to_due.to_numpy()
        for offset,weight in zip(range(-3,4),self.offset_prob):
            day=due+offset;future=day>0;denominator+=weight*future
            week=np.ceil(day/7).astype(int)-1;inside=future&(week<13)
            result[np.flatnonzero(inside),week[inside]]+=weight
        return result/np.maximum(denominator[:,None],1e-12)

    def hazards(self,frame):
        pi=self.gate.predict(frame[FEATURES].astype('float32'))
        if self.calibrator is not None:pi=self.calibrator.predict(pi)
        pi=np.where((frame.days_to_due.to_numpy()+3>0)&(frame.has_due.to_numpy()==1),np.clip(pi,0,1),0.)
        rest,_=t1.pmf_from_hazard(self.rest.hazards(frame))
        P=pi[:,None]*self.on_time_pmf(frame)+(1-pi[:,None])*rest
        survival=1-np.column_stack([np.zeros(len(frame)),P.cumsum(1)[:,:-1]])
        return np.clip(P/np.maximum(survival,1e-12),0,1-1e-9)


def source_pdp_constraints(model,calibration,n_sample=300):
    expected={'c_late_share':-1,'c_delay_eb':-1,'c_delay_ewm':-1,'c_max_dpd':-1,'c_promise_rel':1}
    base=calibration.sample(min(n_sample,len(calibration)),random_state=7);rows=[];constraints={}
    for feature,sign in expected.items():
        values=calibration[feature].dropna().to_numpy()
        grid=np.unique(np.quantile(values,np.linspace(.1,.9,9))) if len(values) else []
        predictions=[]
        for value in grid:
            modified=base.copy();modified[feature]=value
            predictions.append(float(model.hazards(modified).mean()))
        rho=float(spearmanr(grid,predictions).statistic) if len(grid)>=3 and np.ptp(predictions)>1e-12 else 0.
        matches=float(np.mean(sign*np.diff(predictions)>=-1e-8)) if len(grid)>=3 else 0.
        selected=sign*rho>=.7 and matches>=.75
        if selected:constraints[feature]=sign
        for value,pred in zip(grid,predictions):
            rows.append(dict(feature=feature,value=value,mean_hazard=pred,expected_sign=sign,source_spearman=rho,
                             monotonic_step_share=matches,constraint_selected=selected))
    ordered=[constraints.get(feature,0) for feature in FEATURES+t1.WEEK_FEATS]
    return ordered,pd.DataFrame(rows)
