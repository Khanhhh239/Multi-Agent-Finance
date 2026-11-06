"""Fresh conditional factors; bounded feature assembly before prediction."""
from __future__ import annotations

import time
import numpy as np
import pandas as pd

from agent1.models import t1
from experiments.t1_competing_v6.features import V6_FEATURES
from .core import OPEN,PathState,advance,origin_view
from .copula import conditional_uniforms
from .randomness import generator


def simulate_receipts(model,frame,*,n=1000,seed=0,case="",rho_firm=.15,rho_customer=.15,
                      max_invoices=2000,batch_rows=50000,return_invoice_cash=False):
    start = time.perf_counter()
    origin = origin_view(frame)
    m = len(origin)
    if m>max_invoices or n<1 or batch_rows<1:
        raise ValueError("Invalid or exceeded simulation budget")
    if m and pd.to_datetime(origin.cutoff).nunique()!=1:
        raise ValueError("Rollout requires one forecast origin")
    inflow = np.zeros((n,13))
    detailed = np.zeros((n,m,13)) if return_invoice_cash else None
    invoice_index = np.arange(m)
    groups = np.broadcast_to(invoice_index,(n,m)).copy()
    state = PathState.start(m)
    firm,_ = pd.factorize(origin.firm_id,sort=True)
    customer,_ = pd.factorize(pd.MultiIndex.from_frame(origin[["firm_id","customer_id"]]),sort=True)
    base = origin[V6_FEATURES].to_numpy(np.float32)
    amounts = origin.amount_open.to_numpy(float)
    vocabulary = model.vocabulary
    cash = np.array([v["cash_fraction"] for v in vocabulary])
    credit = np.array([v["credit_fraction"] for v in vocabulary])
    status = np.array([v["status"] for v in vocabulary])
    if sorted(range(len(vocabulary)),key=lambda j:(cash[j],credit[j],status[j]))!=list(range(len(vocabulary))):
        raise ValueError("Outcome vocabulary must be ordered by cash")
    audit = []
    for week in range(1,14):
        rows,cols = np.nonzero(groups>=0)
        if not len(rows):
            break
        wf = t1._week_feats(origin,week)
        calendar = np.column_stack([wf[c] for c in t1.WEEK_FEATS]).astype(np.float32)
        probability = np.empty((len(invoice_index),len(vocabulary)),dtype=np.float32)
        max_batch = 0
        for left in range(0,len(invoice_index),batch_rows):
            right = min(left+batch_rows,len(invoice_index))
            idx = invoice_index[left:right]
            # Assemble float32 directly. Never build a full-step float64 x.
            x = np.empty((right-left,len(V6_FEATURES)+7+6),dtype=np.float32)
            x[:,:len(V6_FEATURES)] = base[idx]
            x[:,len(V6_FEATURES):len(V6_FEATURES)+7] = calendar[idx]
            x[:,-6:] = state.take(slice(left,right)).matrix()
            probability[left:right] = model.predict(x,week=week)
            max_batch = max(max_batch,len(x))
        previous = groups[rows,cols]
        u = conditional_uniforms(generator(seed,case,f"collection_week_{week}"),n,firm,customer,rho_firm,rho_customer)[rows,cols]
        cdf = np.cumsum(probability,axis=1)
        chosen = np.zeros(len(rows),dtype=np.int16)
        for j in range(len(vocabulary)-1):
            chosen += u>cdf[previous,j]
        received = amounts[cols]*state.remaining[previous]*cash[chosen]
        inflow[:,week-1] = np.bincount(rows,weights=received,minlength=n)
        if detailed is not None:
            detailed[rows,cols,week-1] = received
        code,inverse = np.unique(previous*len(vocabulary)+chosen,return_inverse=True)
        old,outcome = code//len(vocabulary),code%len(vocabulary)
        newstate = state.take(old)
        opening = newstate.remaining.copy()
        rc,cr,wo = advance(newstate,np.arange(len(code)),cash[outcome],credit[outcome],status[outcome])
        error = opening-rc-cr-wo-newstate.remaining
        live = newstate.status==OPEN
        mapping = np.full(len(code),-1,dtype=int)
        mapping[live] = np.arange(live.sum())
        groups[rows,cols] = mapping[inverse]
        audit.append({"week":week,"active_rows":len(rows),"predicted_rows":len(probability),"max_feature_batch_rows":max_batch,
                      "max_accounting_error_vnd":float(np.max(np.abs(error)*amounts[invoice_index[old]],initial=0))})
        invoice_index = invoice_index[old[live]]
        state = newstate.take(np.flatnonzero(live))
    return {"cash":inflow,"invoice_cash":detailed,"audit":audit,"seconds":time.perf_counter()-start,
            "predicted_rows":sum(a["predicted_rows"] for a in audit),"active_rows":sum(a["active_rows"] for a in audit)}
