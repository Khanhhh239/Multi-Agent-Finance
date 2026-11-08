"""Separate AR-applied distributions, full bank paths and conditional diagnostics."""
import numpy as np
import pandas as pd

from .scoring import crps,score_paths,paired_summary,research_decision
from .core import PathState,advance,encode


def score_ar(cash,actual,origin_amount):
    samples = np.cumsum(cash,axis=1)
    truth = np.cumsum(actual)
    lo,mid,hi = np.quantile(samples,[.1,.5,.9],axis=0)
    scale = max(float(origin_amount),1.)
    return {"ar_crps_normalized":float(crps(samples,truth).mean()/scale),
            "ar_coverage80":float(((truth>=lo)&(truth<=hi)).mean()),
            "ar_width_normalized":float((hi-lo).mean()/scale),
            "ar_cash_bias13":float((cash.sum(1).mean()-actual.sum())/max(actual.sum(),1)),
            "ar_p50_mae_normalized":float(np.abs(mid-truth).mean()/scale)}


def replay_classes(frame,keys,detail,vocabulary):
    y = encode(keys,vocabulary,allow_unknown=True)
    if (y<0).any():
        return {"unsupported":int((y<0).sum()),"cash_wape":None}
    state = PathState.start(len(frame))
    id_columns = [c for c in ("world","invoice_id","cutoff") if c in frame and c in detail]
    index = pd.Series(np.arange(len(frame)),index=pd.MultiIndex.from_frame(frame[id_columns]))
    if not index.index.is_unique:
        raise ValueError("Class replay needs unique World/invoice/origin anchors")
    amount = frame.amount_open.to_numpy()
    reps = np.array([[v["cash_fraction"],v["credit_fraction"],v["status"]] for v in vocabulary])
    predicted,actual = [],[]
    for week in range(1,14):
        keep = detail.week.eq(week).to_numpy()
        ids = index.reindex(pd.MultiIndex.from_frame(detail.loc[keep,id_columns])).to_numpy(int)
        if not len(ids):
            continue
        values = reps[y[keep]]
        rc,_,_ = advance(state,ids,values[:,0],values[:,1],values[:,2].astype(int))
        predicted.append(float((rc*amount[ids]).sum()))
        actual.append(float(detail.loc[keep,"cash_actual"].sum()))
    return {"unsupported":0,"cash_wape":float(np.abs(np.array(predicted)-actual).sum()/max(sum(actual),1)),
            "cumulative_cash_bias":float((sum(predicted)-sum(actual))/max(sum(actual),1))}
