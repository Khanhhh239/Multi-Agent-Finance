import numpy as np
import pandas as pd
from agent1.models.features import FEATURES
from agent1.models import t1
from agent1.models.t1_variants import expand_daily,DailyEarlyHazard,DueMixture,due_component_labels
from agent1.models.eb_ml2 import learn_industry_k


def frame(n=300):
    rng=np.random.default_rng(7)
    out=pd.DataFrame(rng.normal(size=(n,len(FEATURES))),columns=FEATURES)
    out['cutoff']=pd.Timestamp('2024-07-01');out['days_to_due']=rng.integers(-10,50,n)
    out['has_due']=1;out['top1']=10.;out['top2']=25.;out['days_to_promised']=np.nan
    out['remaining']=rng.integers(1,90,n);out['event']=1
    out['time_obs']=out.remaining
    return out


def test_daily_expansion_has_no_negative_rows_after_event_or_partial_censor():
    data=frame(2);data['remaining']=[1.,np.inf];data['event']=[1,0];data['time_obs']=[1.,2.5]
    X,y=expand_daily(data)
    assert len(y)==3 and y.sum()==1
    assert sorted(X[:,len(FEATURES)].tolist())==[1.,1.,2.]


def test_daily_composite_preserves_mass_and_order():
    data=frame();base=t1.HazardGBM(dict(min_data_in_leaf=5,num_leaves=7),rounds=5).fit(data)
    result=DailyEarlyHazard(base,rounds=5).fit(data).predict(data.iloc[:20],batch_size=7)
    assert (np.diff(result['Q'],axis=1)>=-1e-9).all()
    assert (np.diff(result['cdf'],axis=1)>=0).all()
    np.testing.assert_allclose(result['P'].sum(1)+1-result['cdf'][:,-1],1.)


def test_mixture_component_labels_do_not_use_censored_future_payment():
    data=frame(3);data['days_to_due']=[10,10,10];data['event']=[0,0,1];data['time_obs']=[3,20,11];data['remaining']=[11,25,11]
    known,y=due_component_labels(data)
    assert known.tolist()==[False,True,True] and y.tolist()==[0,0,1]
    data.loc[0:1,'remaining']=[12,999]
    other,target=due_component_labels(data)
    np.testing.assert_array_equal(known,other);np.testing.assert_array_equal(y,target)


def test_mixture_mass_and_overdue_component_guard():
    data=frame(500);data.loc[:160,'remaining']=data.loc[:160,'days_to_due'].clip(lower=1)
    data['time_obs']=data.remaining
    base=t1.HazardGBM(dict(min_data_in_leaf=5,num_leaves=7),rounds=5).fit(data)
    mixture=DueMixture(base,rounds=5).fit(data)
    H=mixture.hazards(data);P,S=t1.pmf_from_hazard(H)
    assert np.isfinite(H).all() and ((H>=0)&(H<=1)).all()
    np.testing.assert_allclose(P.sum(1)+S[:,-1],1)
    on=mixture.on_time_pmf(data)
    assert np.all(on.sum(1)<=1+1e-10)


def test_ml2_uses_only_observed_source_history():
    rng=np.random.default_rng(9);customers=np.repeat(np.arange(40),30)
    delay=np.repeat(rng.normal(10,2,40),30)+rng.normal(0,3,len(customers))
    invoices=pd.DataFrame(dict(firm_id='f',customer_id=customers,issue_date=pd.Timestamp('2020-01-01'),due_date=pd.Timestamp('2020-02-01')))
    invoices['paid_date_true']=invoices.due_date+pd.to_timedelta(delay.round(),unit='D')
    firms=pd.DataFrame(dict(firm_id=['f'],industry=['steel']))
    fit=learn_industry_k(invoices,firms,'2021-01-01')
    assert .8<fit['steel']['k']<6
    future=invoices.iloc[:10].copy();future['paid_date_true']=pd.Timestamp('2025-01-01')
    other=learn_industry_k(pd.concat([invoices,future]),firms,'2021-01-01')
    assert fit==other
