import numpy as np
import pandas as pd
from .ingest.dates import local_dates


def psi(reference,current,bins=10):
    reference,current=np.asarray(reference,float),np.asarray(current,float)
    reference,current=reference[np.isfinite(reference)],current[np.isfinite(current)]
    if len(reference)<2 or len(current)<2:
        return np.nan
    edges=np.unique(np.r_[-np.inf,np.quantile(reference,np.linspace(0,1,bins+1)[1:-1]),np.inf])
    p=np.histogram(reference,edges)[0]/len(reference)
    q=np.histogram(current,edges)[0]/len(current)
    p,q=np.maximum(p,1e-6),np.maximum(q,1e-6)
    return float(np.sum((q-p)*np.log(q/p)))


def retrain_required(psi_value,rolling_coverage):
    coverage=np.asarray(rolling_coverage,float)
    return bool(psi_value>.1 or (len(coverage)>=4 and np.all((coverage[-4:]<.7)|(coverage[-4:]>.9))))


def realized_coverage(forecasts,balances,cutoff):
    """Chỉ chấm số dư quan sát đúng cuối tuần dự báo, không nội suy tương lai."""
    def day(value):return local_dates(pd.Series([value]),dayfirst=False).iloc[0]
    T=day(cutoff);actual={}
    for row in balances:
        date=day(row['date'])
        if date<=T:actual[date]=float(row['balance'])
    result=[]
    for forecast in sorted(forecasts,key=lambda f:f['cutoff']):
        origin=day(forecast['cutoff'])
        if origin>T:continue
        covered=[]
        for band in forecast['band']:
            end=origin+pd.Timedelta(days=7*int(band['week']))
            if end<=T and end in actual:
                covered.append(band['P10']<=actual[end]<=band['P90'])
        if covered:result.append(dict(cutoff=str(origin.date()),n_observed=len(covered),cov80=float(np.mean(covered))))
    return result


def weekly_report(store,firm,cutoff,current_features=None,reference=None):
    features=[]
    if current_features is not None and reference:
        for name,values in reference.items():
            if name not in current_features:continue
            value=psi(values,current_features[name])
            features.append(dict(feature=name,psi=None if not np.isfinite(value) else value))
    coverage=realized_coverage(store.get(firm,'forecasts'),store.get(firm,'cash_balances'),cutoff)
    finite=[r['psi'] for r in features if r['psi'] is not None]
    maximum=max(finite) if finite else None
    result=dict(id=str(pd.Timestamp(cutoff).date()),cutoff=str(pd.Timestamp(cutoff).date()),features=features,
                psi_max=maximum,coverage=coverage[-12:],n_scored_origins=len(coverage),
                retrain_required=retrain_required(maximum or 0.,[r['cov80'] for r in coverage]),
                diagnostics_only=True,pilot_ready=False,
                missing_inputs=[name for name,missing in [('model_reference',not reference),('realized_week_end_balances',not coverage)] if missing])
    store.put(firm,'monitoring',[result])
    return result
