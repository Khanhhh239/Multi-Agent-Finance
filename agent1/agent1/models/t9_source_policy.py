"""Ứng viên phân bổ P5 từ hồ sơ đã biết; không đọc loại hard-case hoặc ngày trả thật."""
import numpy as np
import pandas as pd
from .t9_recon import TOL,memo_numbers
from .reconciliation_pipeline import _subsets


def retention_components(invoices,contracts,asof):
    """Chỉ tách giữ lại khi có điều khoản/ngày biết; không dùng annotation kết quả tương lai."""
    now=pd.Timestamp(asof);rows=[];by_id=invoices.set_index('invoice_id')
    if pd.isna(now):raise ValueError('Thiếu ngày as-of')
    seen=set()
    for event in contracts:
        known=pd.Timestamp(event['known_at'])
        if pd.isna(known):raise ValueError('Thiếu ngày biết điều khoản giữ lại')
        if known>now:continue
        iid=event['invoice_id']
        if iid in seen:raise ValueError('Trùng hợp đồng giữ lại')
        seen.add(iid)
        if iid not in by_id.index:raise ValueError('Hợp đồng không có hoá đơn')
        invoice=by_id.loc[iid]
        if invoice.issue_date>now:continue
        if not str(event.get('source','')).strip():raise ValueError('Thiếu nguồn điều khoản')
        held=float(event['amount']);total=float(invoice.amount_gross)
        if not np.isfinite(held) or not 0<held<total:raise ValueError('Khoản giữ lại không hợp lệ')
        due=pd.Timestamp(event['due_date'])
        if pd.isna(due) or due<invoice.issue_date:raise ValueError('Ngày nghĩa vụ không hợp lệ')
        for component,amount,date in [('base',total-held,invoice.due_date),('retention',held,due)]:
            rows.append(dict(obligation_id=f'{iid}:{component}',invoice_id=iid,component=component,
                amount=amount,due_date=date,known_at=pd.Timestamp(event['known_at']),source=event['source']))
    return pd.DataFrame(rows)


def hazard_subset(pool,amount,probabilities,min_odds=3.):
    """So nghiệm khả thi bằng prior T1; chênh lệch không đủ thì vẫn giữ hàng chờ."""
    pool=pool.head(15)
    if pool.empty:return []
    matrix=_subsets(len(pool));feasible=np.flatnonzero(np.abs(matrix@pool.remaining_amount.to_numpy()-amount)<=TOL)
    if len(feasible)<2:return []
    probabilities=np.asarray(probabilities,float)[:len(pool)]
    if probabilities.shape!=(len(pool),) or not np.isfinite(probabilities).all():raise ValueError('Prior T1 không hợp lệ')
    costs=matrix[feasible]@(-np.log(np.clip(probabilities,1e-6,1-1e-6)))
    order=np.argsort(costs,kind='stable')
    if costs[order[1]]-costs[order[0]]<np.log(min_odds):return []
    return pool.invoice_id.to_numpy()[matrix[feasible[order[0]]].astype(bool)].tolist()


class ObservedAllocationPolicy:
    def __init__(self,prior=None):self.prior=prior

    def __call__(self,pool,transaction):
        # pool đã được giới hạn đúng khách + công ty + ngày phát hành <= giao dịch.
        matches=pool[pool.invoice_no.astype(int).isin(set(memo_numbers(transaction.memo)))]
        if len(matches)==1 and TOL<transaction.amount<float(matches.remaining_amount.iloc[0])-TOL:
            return matches.invoice_id.tolist(),'memo_partial_residual'
        cod=pool[(pool.due_date==pool.issue_date)&
            ((transaction.value_date-pool.issue_date).dt.days.between(0,3))&
            ((pool.remaining_amount-transaction.amount).abs()<=TOL)]
        if len(cod)==1:return cod.invoice_id.tolist(),'COD_recent_unique'
        if self.prior is not None:
            subset=pool.head(15)
            if subset.empty:return [],''
            feasible=np.abs(_subsets(len(subset))@subset.remaining_amount.to_numpy()-transaction.amount)<=TOL
            if feasible.sum()<2:return [],''
            probabilities=self.prior(pool,transaction.value_date)
            chosen=hazard_subset(pool,transaction.amount,probabilities)
            if chosen:return chosen,'hazard_weighted_subset'
        return [],''


class LedgerHazardPrior:
    """Prior T1 đóng băng; snapshot từ ngày sổ đã biết trước giao dịch, không dùng paid_date_true."""
    def __init__(self,invoices,model,training_label_end):
        from .features import SnapshotBuilder
        self.builder=SnapshotBuilder(invoices,label_col='ledger_clear_date')
        self.model=model;self.available=pd.Timestamp(training_label_end);self.cache={}

    def __call__(self,pool,date):
        now=pd.Timestamp(date)
        if self.available>=now:raise ValueError('Prior T1 chưa tồn tại trước giao dịch')
        key=now.normalize()
        if key not in self.cache:
            frame=self.builder.snapshot(key-pd.Timedelta(days=1))
            self.cache[key]=pd.Series(dtype=float) if frame.empty else pd.Series(self.model.hazards(frame)[:,0],index=frame.invoice_id)
            if len(self.cache)>512:self.cache.pop(next(iter(self.cache)))
        return pool.invoice_id.map(self.cache[key]).fillna(.5).to_numpy()
