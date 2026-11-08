"""Chính sách giả lập: CRN ΔP và dời chứng từ tương lai, không tạo thêm tiền."""
import hashlib
import numpy as np
import pandas as pd
from scipy.stats import norm,t as student_t
from agent1.models.t6_cash import simulate,K


def rank_delta(snapshot,P,sim_args,top_n=50):
    """Tương đương force_week=0 khi không có cure, capex hoặc rút vốn; một lần mô phỏng."""
    forbidden={'p_bad','force_week','payment_shift','draw_cap','draw_target','draw_weeks'}
    if any(sim_args.get(key) is not None for key in forbidden):raise ValueError('Ranking tuyến tính không nhận cure/rút vốn/dời tiền')
    args=dict(sim_args,open_df=snapshot,P=P)
    base,_=simulate(**args);n=len(base);m=len(snapshot)
    if not m:return pd.DataFrame(columns=['invoice_id','delta_shortfall','amount_open'])
    rho=args.get('rho',.15);nu=args.get('nu',4);seed=args.get('seed',0)
    if args.get('rho_customer',0)!=0:raise ValueError('Chưa hỗ trợ copula phân tầng trong ranking này')
    rng=np.random.default_rng(np.random.SeedSequence(seed).spawn(4)[0])
    g=rng.standard_normal(n);scale=np.sqrt(rng.chisquare(nu,n)/nu);e=rng.standard_normal((n,m))
    uniform=student_t.cdf((np.sqrt(rho)*g[:,None]+np.sqrt(1-rho)*e)/scale[:,None],nu) if rho>0 else norm.cdf(e)
    cdf=np.asarray(P).cumsum(1);weeks=np.empty((n,m),int)
    for column in range(m):weeks[:,column]=np.searchsorted(cdf[column],uniform[:,column],side='left')
    base_risk=float((base.min(1)<0).mean())
    priorities=snapshot.amount_open.to_numpy()*(1-np.asarray(P)[:,:2].sum(1))
    rows=[]
    for ix in np.argsort(-priorities)[:top_n]:
        amount=float(snapshot.iloc[ix].amount_open)
        change=amount*(1-(np.arange(K)[None,:]>=weeks[:,ix:ix+1]))
        risk=float(((base+change).min(1)<0).mean())
        rows.append(dict(invoice_id=snapshot.iloc[ix].invoice_id,delta_shortfall=base_risk-risk,
            baseline_shortfall=base_risk,scenario_shortfall=risk,amount_open=amount))
    return pd.DataFrame(rows).sort_values(['delta_shortfall','amount_open','invoice_id'],ascending=[False,False,True])


def response_uniform(invoice_id,cutoff,seed=7):
    key=f'{seed}|{invoice_id}|{pd.Timestamp(cutoff).date()}'.encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8],'little')/2**64


def move_receipts(payments,invoice_id,cutoff):
    """Chỉ dời tiền sau tuần 1 về cuối tuần 1; tiền trong quá khứ/tuần 1 giữ nguyên."""
    result=payments.copy();receipt=pd.Timestamp(cutoff)+pd.Timedelta(days=7)
    mask=(result.invoice_id==invoice_id)&(result.pay_date_true>receipt)
    moves=result.loc[mask,['invoice_id','pay_date_true','amount']].rename(columns={'pay_date_true':'old_date'}).copy()
    moves['new_date']=receipt
    result.loc[mask,'pay_date_true']=receipt
    return result,moves


def remaining_ar(invoices,payments,cutoff):
    cutoff=pd.Timestamp(cutoff)
    received=payments[payments.pay_date_true<=cutoff].groupby('invoice_id').amount.sum()
    credit=invoices.credit_note.where(invoices.credit_note_date<=cutoff,0.) if 'credit_note_date' in invoices else 0.
    remaining=(invoices.amount_gross-credit-invoices.invoice_id.map(received).fillna(0.)).clip(lower=0.)
    known=(invoices.issue_date<=cutoff)&(invoices.writeoff_date.isna()|(invoices.writeoff_date>cutoff))
    if 'paid_date_true' in invoices:
        settled=invoices.paid_date_true.notna()&(invoices.paid_date_true<=cutoff)
        known &= ~settled
    return pd.Series(remaining.where(known,0.).to_numpy(),index=invoices.invoice_id)


def count_shortfalls(balances):
    negative=np.asarray(balances)<0
    return int((negative&~np.r_[False,negative[:-1]]).sum())
