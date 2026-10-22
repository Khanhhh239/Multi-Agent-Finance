"""Khai triển tổ hợp bằng NumPy, giữ nguyên đặc trưng của Reconciler nguồn."""
from functools import lru_cache
import itertools
import numpy as np
import pandas as pd
from agent1.models.t9_recon import Reconciler,TOL,norm_name,memo_numbers
from rapidfuzz import fuzz,process
from agent1.models.reconciliation_pipeline import LINK_COLUMNS,choose_subset


@lru_cache(maxsize=24)
def subset_indices(n,size):
    return np.asarray(list(itertools.combinations(range(n),size)),dtype=np.int16)


class FastAmountReconciler(Reconciler):
    def candidates(self,bank,inv,cust):
        rows=[]
        for firm,transactions in bank.groupby('firm_id'):
            customers=cust[cust.firm_id==firm]
            names={cid:norm_name(short) for cid,short in zip(customers.customer_id,customers['short'])}
            keys=list(names.values());ids=list(names.keys())
            invoices=inv[inv.firm_id==firm].sort_values('due_date')
            invoices=invoices.assign(no=invoices.invoice_no.astype(int))
            histories={}
            for cid,part in invoices.groupby('customer_id'):
                histories[cid]=dict(issue=part.issue_date.to_numpy(dtype='datetime64[ns]'),
                    due=part.due_date.to_numpy(dtype='datetime64[ns]'),amount=part.amount_gross.to_numpy(float),
                    clear=part.ledger_clear_date.to_numpy(dtype='datetime64[ns]') if 'ledger_clear_date' in part else None,
                    credit=part.credit_note.to_numpy(float) if 'credit_note_date' in part and 'credit_note' in part else None,
                    credit_date=part.credit_note_date.to_numpy(dtype='datetime64[ns]') if 'credit_note_date' in part and 'credit_note' in part else None)
            no_rows={}
            for number,cid,issued in zip(invoices.no,invoices.customer_id,invoices.issue_date):
                no_rows.setdefault(number,[]).append((cid,issued))
            first=invoices.groupby('customer_id').issue_date.min().reindex(ids).to_numpy()
            for txn in transactions.itertuples(index=False):
                date=np.datetime64(txn.value_date,'ns');known=np.flatnonzero(first<=date)
                active_keys=[keys[ix] for ix in known];active_ids=[ids[ix] for ix in known]
                counterparty=norm_name(txn.counterparty);memo=norm_name(txn.memo);numbers=memo_numbers(txn.memo)
                candidates={}
                if counterparty:
                    for _,score,ix in process.extract(counterparty,active_keys,scorer=fuzz.token_set_ratio,limit=self.top_k):
                        candidates[active_ids[ix]]=max(candidates.get(active_ids[ix],0),score)
                for _,score,ix in process.extract(memo,active_keys,scorer=fuzz.partial_ratio,limit=2):
                    candidates.setdefault(active_ids[ix],0)
                for number in numbers:
                    for cid,issued in no_rows.get(number,[]):
                        if issued<=txn.value_date:candidates.setdefault(cid,0)
                ranked=sorted(candidates.items(),key=lambda pair:-pair[1])
                for rank,(cid,score) in enumerate(ranked):
                    features=self._array_amount_features(histories.get(cid),txn.amount,date)
                    hits=sum(1 for number in numbers if any(c==cid and d<=txn.value_date for c,d in no_rows.get(number,[])))
                    rows.append(dict(txn_id=txn.txn_id,firm_id=firm,customer_id=cid,name_score=score,
                        memo_name_score=fuzz.partial_ratio(names[cid],memo),n_no_hit=hits,is_rank1_name=int(rank==0),
                        cust_hist_txn_share=np.nan,**features,y=int(getattr(txn,'true_customer_id',None)==cid)))
        return pd.DataFrame(rows)

    @staticmethod
    def _array_amount_features(history,amount,date):
        if history is None:
            return dict(amt_exact_single=0,amt_subset_hit=0,amt_rel_gap=1.,cust_open_n=0,days_from_oldest_due=np.nan)
        issued=np.flatnonzero(history['issue']<=date)
        if not len(issued):return FastAmountReconciler._array_amount_features(None,amount,date)
        clear=history['clear']
        opened=issued if clear is None else issued[np.isnat(clear[issued])|(clear[issued]>=date)]
        selected=opened[:12] if len(opened) else issued[-6:]
        amounts=history['amount'][selected]
        if history['credit'] is not None:
            amounts=amounts-np.where(history['credit_date'][selected]<=date,history['credit'][selected],0.)
        exact=int(np.any(np.abs(amounts-amount)<=TOL));best=np.min(np.abs(amounts-amounts.dtype.type(amount)))
        subset=0
        for size in (2,3):
            if len(amounts)<size:continue
            indices=subset_indices(min(len(amounts),10),size)
            if np.any(np.abs(amounts[indices].sum(1)-amount)<=TOL):subset,best=1,0.;break
        days=float((date-history['due'][selected[0]])/np.timedelta64(1,'D'))
        return dict(amt_exact_single=exact,amt_subset_hit=subset,amt_rel_gap=float(min(best/max(amount,1),1.)),
                    cust_open_n=len(selected),days_from_oldest_due=float(np.floor(days)))

    @staticmethod
    def _amount_feats(op,amt,date):
        if op is None or op.empty:
            return dict(amt_exact_single=0,amt_subset_hit=0,amt_rel_gap=1.,cust_open_n=0,days_from_oldest_due=np.nan)
        known=op.ledger_clear_date if 'ledger_clear_date' in op else pd.Series(pd.NaT,index=op.index)
        opened=op[known.isna()|(known>=date)].head(12)
        if opened.empty:opened=op.tail(6)
        adjustment=(opened.credit_note.where(opened.credit_note_date<=date,0.)
                    if 'credit_note_date' in opened and 'credit_note' in opened else 0.)
        amounts=(opened.amount_gross-adjustment).to_numpy()
        exact=int(np.any(np.abs(amounts-amt)<=TOL));best=np.min(np.abs(amounts-amt)) if len(amounts) else amt
        subset=0
        for size in (2,3):
            if len(amounts)<size:continue
            indices=subset_indices(min(len(amounts),10),size)
            if np.any(np.abs(amounts[indices].sum(1)-amt)<=TOL):
                subset,best=1,0.;break
        return dict(amt_exact_single=exact,amt_subset_hit=subset,amt_rel_gap=float(min(best/max(amt,1),1.)),
                    cust_open_n=len(opened),days_from_oldest_due=float((date-opened.due_date.iloc[0]).days))


def fast_source(source):
    result=FastAmountReconciler()
    result.__dict__.update(source.__dict__)
    return result


def concatenate_parts(parts):
    nonempty=[frame for frame in parts if len(frame)]
    return pd.concat(nonempty,ignore_index=True) if nonempty else parts[0].copy()


NAME_CORROBORATION=90.


def corroborated(candidate,memo_hits,chosen_numbers):
    """Bằng chứng độc lập với mô hình khách: số HĐ đã chọn có trong nội dung CK, hoặc tên người chuyển khớp tên khách."""
    return bool(memo_hits&set(chosen_numbers)) or float(candidate.get('name_score',0) or 0)>=NAME_CORROBORATION


def reconcile_arrays(rec,bank,invoices,customers,tau_auto=.9,assignments=None,rules_first=True,
                     rule_mode='both',ledger_policy='asof',allocation_policy=None,corroborate_below=None):
    """Cùng quy tắc/cash state của bản chuẩn; lọc mảng thay sao chép DataFrame mỗi giao dịch.

    corroborate_below: nếu đặt, liên kết qua mô hình khách có độ tin cậy < ngưỡng này chỉ tự động khi có bằng chứng
    độc lập (`corroborated`); không có thì vào hàng chờ. None = hành vi cũ."""
    if not 0<=tau_auto<=1:raise ValueError('tau_auto trong [0,1]')
    if corroborate_below is not None and not tau_auto<=corroborate_below<=1:raise ValueError('corroborate_below trong [tau_auto,1]')
    if rule_mode not in {'both','amount','memo'} or ledger_policy not in {'asof','opening_only'}:
        raise ValueError('Chính sách quy tắc/sổ cái không hợp lệ')
    columns=['invoice_id','firm_id','customer_id','issue_date','due_date','invoice_no','amount_gross',
             'ledger_clear_date','credit_note_date','credit_note']
    inv=invoices[[c for c in columns if c in invoices]].sort_values(['due_date','invoice_id']).reset_index(drop=True)
    ids=inv.invoice_id.to_numpy();positions={iid:i for i,iid in enumerate(ids)}
    firms=inv.firm_id.to_numpy();custs=inv.customer_id.to_numpy()
    issued=inv.issue_date.to_numpy(dtype='datetime64[ns]')
    clear=inv.ledger_clear_date.to_numpy(dtype='datetime64[ns]') if 'ledger_clear_date' in inv else None
    credit_date=inv.credit_note_date.to_numpy(dtype='datetime64[ns]') if 'credit_note_date' in inv and 'credit_note' in inv else None
    credits=inv.credit_note.to_numpy(float) if credit_date is not None else None
    remaining=inv.amount_gross.to_numpy(float,copy=True);applied=np.zeros(len(inv))
    if len(bank) and clear is not None:remaining[clear<np.datetime64(bank.value_date.min(),'ns')]=0.
    if assignments is None and rec.model is not None and len(bank):
        candidates=rec.candidates(bank,invoices,customers)
        assignments=rec.assign_customers(candidates,thr=tau_auto) if len(candidates) else pd.DataFrame()
    assigned=assignments.set_index('txn_id') if assignments is not None and len(assignments) else pd.DataFrame()
    links,reviews=[],[]
    from agent1.models.t9_recon import memo_numbers
    for txn in bank.sort_values(['value_date','txn_id']).itertuples(index=False):
        if getattr(txn,'direction','in')!='in' or txn.amount<=0:
            reviews.append(dict(txn_id=txn.txn_id,reason='not_positive_inflow',amount=txn.amount));continue
        date=np.datetime64(txn.value_date,'ns');firm_mask=firms==txn.firm_id
        if ledger_policy=='asof' and clear is not None:remaining[firm_mask&(clear<date)]=0.
        if credit_date is not None:
            known=firm_mask&(credit_date<=date)
            delta=np.maximum(credits[known]-applied[known],0.)
            remaining[known]=np.maximum(remaining[known]-delta,0.);applied[known]=credits[known]
        opened=np.flatnonzero(firm_mask&(issued<=date)&(remaining>TOL))
        numbers=set(memo_numbers(txn.memo));invoice_numbers=inv.invoice_no.to_numpy()[opened].astype(int)
        hits=np.isin(invoice_numbers,list(numbers));matches=opened[hits]
        chosen=[];method='';confidence=0.
        if rules_first and rule_mode!='amount' and len(matches) and len(np.unique(invoice_numbers[hits]))==len(matches) and len(np.unique(custs[matches]))==1:
            if abs(remaining[matches].sum()-txn.amount)<=TOL:
                chosen=matches.tolist();method='R2_memo';confidence=1.
        if rules_first and rule_mode!='memo' and not chosen:
            exact=opened[np.abs(remaining[opened]-txn.amount)<=TOL]
            if len(exact)==1:chosen=exact.tolist();method='R1_unique_amount';confidence=1.
        reason='no_unambiguous_rule'
        if not chosen and len(assigned) and txn.txn_id in assigned.index:
            candidate=assigned.loc[txn.txn_id];confidence=float(candidate.get('confidence',candidate.get('p',0)))
            if confidence>=tau_auto:
                pool=opened[custs[opened]==candidate.customer_id]
                candidates=pd.DataFrame({'remaining_amount':remaining[pool]},index=ids[pool])
                selected,solutions=choose_subset(candidates,txn.amount)
                chosen=[positions[iid] for iid in selected];method='ML_subset'
                if solutions>1:chosen=[];reason='ambiguous_allocation'
                elif not chosen:reason='no_amount_allocation'
            else:reason='low_customer_confidence'
        if not chosen and allocation_policy is not None and len(assigned) and txn.txn_id in assigned.index:
            candidate=assigned.loc[txn.txn_id]
            confidence=float(candidate.get('confidence',candidate.get('p',0)))
            if confidence>=tau_auto:
                pool=opened[custs[opened]==candidate.customer_id]
                observed=inv.iloc[pool].copy();observed['remaining_amount']=remaining[pool]
                selected,extra_method=allocation_policy(observed,txn)
                if selected:
                    proposed=[positions[iid] for iid in selected]
                    if not set(proposed)<=set(pool) or remaining[proposed].sum()+TOL<txn.amount:
                        raise ValueError('Phân bổ vượt khách/ngày/công nợ đã biết')
                    chosen=proposed;method=extra_method
        if chosen and corroborate_below is not None and method not in ('R1_unique_amount','R2_memo') and confidence<corroborate_below:
            if not corroborated(assigned.loc[txn.txn_id],numbers,inv.invoice_no.to_numpy()[chosen].astype(int).tolist()):
                chosen=[];reason='uncorroborated_low_confidence'
        if not chosen:
            reviews.append(dict(txn_id=txn.txn_id,reason=reason,amount=txn.amount,confidence=confidence));continue
        cash=float(txn.amount)
        for ix in chosen:
            paid=min(float(remaining[ix]),cash);cash-=paid;remaining[ix]-=paid
            links.append(dict(txn_id=txn.txn_id,invoice_id=ids[ix],est_pay_date=txn.value_date,
                kind='full' if remaining[ix]<=TOL else 'partial',amount=paid,method=method,confidence=confidence))
    return pd.DataFrame(links,columns=LINK_COLUMNS),pd.DataFrame(reviews,columns=['txn_id','reason','amount','confidence'])
