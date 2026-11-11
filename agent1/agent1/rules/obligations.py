"""Lịch nghĩa vụ bổ sung từ hồ sơ/hợp đồng được biết tại thời điểm dự báo.

Không suy ra số thuế, mức thưởng hay ngày hoàn tiền từ luật; nhập số đã duyệt.
Không đưa hoàn VAT chưa có quyết định vào khoản thu chắc chắn.
"""
from decimal import Decimal,ROUND_HALF_UP
import numpy as np
import pandas as pd
from agent1.calendar_vn import next_business_day,prev_business_day

CATEGORIES={'pit_withholding','foreign_contractor_tax','vat_refund','salary_bonus',
    'rent_contract','loan_interest','loan_principal','cit_final'}
COLUMNS=['obligation_id','date','category','amount','direction','known_at','source','verified']


def money(value):
    amount=Decimal(str(value))
    if not amount.is_finite() or amount<0:raise ValueError('Số tiền phải hữu hạn và không âm')
    return float(amount.quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def _verified(value):
    if not isinstance(value,(bool,np.bool_)):raise ValueError('verified phải là bool')
    return bool(value)


def _versions(events,asof):
    """Select the latest known version; reject ambiguous same-day versions."""
    selected={};seen=set()
    for event in events:
        identifier=event.get('obligation_id')
        if identifier is None or not str(identifier).strip():raise ValueError('Mã nghĩa vụ rỗng hoặc trùng')
        identifier=str(identifier)
        known=pd.Timestamp(event.get('known_at'))
        if pd.isna(known):raise ValueError('Thiếu ngày biết hồ sơ')
        if known>asof:continue
        key=(identifier,known)
        if key in seen:raise ValueError('Mã nghĩa vụ trùng cùng ngày ghi nhận')
        seen.add(key)
        if identifier not in selected or known>pd.Timestamp(selected[identifier]['known_at']):
            selected[identifier]=event
    return selected.values()


def extended_schedule(events,*,asof,start,end,strict=False):
    """Một hồ sơ/một kỳ có mã duy nhất; người dùng cung cấp hạn và số tiền.

    known_at và refund_approved_at là ngày hồ sơ được ghi nhận; thay hồ sơ phải
    giữ bản lịch sử riêng, không ghi đè ngày biết. Không dùng ngày chi thực tế tương lai.
    """
    now=pd.Timestamp(asof);start=pd.Timestamp(start);end=pd.Timestamp(end)
    if any(pd.isna(v) for v in [now,start,end]) or end<start:raise ValueError('Khoảng ngày không hợp lệ')
    rows=[]
    for event in _versions(events,now):
        identifier=str(event['obligation_id']);category=event['category']
        if category not in CATEGORIES:raise ValueError('Loại nghĩa vụ không hỗ trợ')
        known=pd.Timestamp(event['known_at'])
        status=event.get('status','open')
        if status not in {'open','cancelled'}:raise ValueError('Trạng thái nghĩa vụ không hợp lệ')
        if status=='cancelled':continue
        due=pd.Timestamp(event['due_date'])
        if pd.isna(due):raise ValueError('Thiếu ngày theo hợp đồng/hồ sơ')
        source=str(event.get('source','')).strip()
        if not source:raise ValueError('Cần nguồn hồ sơ/hợp đồng')
        verified=_verified(event.get('verified',False))
        if strict and not verified:raise ValueError('Hồ sơ chưa xác minh')
        if category=='vat_refund':
            approval=event.get('refund_approved_at')
            if not approval or pd.isna(pd.Timestamp(approval)) or pd.Timestamp(approval)>now:continue
            if due<pd.Timestamp(approval):raise ValueError('Ngày nhận hoàn trước quyết định')
            known=max(known,pd.Timestamp(approval))
        convention=event.get('business_day','none')
        if convention not in {'none','following','preceding'}:raise ValueError('Quy ước ngày làm việc không hợp lệ')
        due=next_business_day(due) if convention=='following' else prev_business_day(due) if convention=='preceding' else due
        if category=='vat_refund' and due<pd.Timestamp(approval):raise ValueError('Ngày nhận hoàn trước quyết định')
        if start<=due<=end:
            rows.append(dict(obligation_id=identifier,date=due,category=category,amount=money(event['amount']),
                direction='inflow' if category=='vat_refund' else 'outflow',known_at=known,source=source,verified=bool(verified)))
    return pd.DataFrame(rows,columns=COLUMNS).sort_values(['date','obligation_id']).reset_index(drop=True)


def rent_events(contract_id,steps,*,months,due_day,known_at,source,business_day='following',asof=None):
    """Bậc giá có ngày hiệu lực; kỳ giao nhau/không có giá phải sửa hồ sơ trước khi dự báo."""
    if isinstance(due_day,(bool,np.bool_)) or not isinstance(due_day,(int,np.integer)) or not 1<=due_day<=31:
        raise ValueError('Ngày thuê phải từ 1..31')
    base=pd.Timestamp(known_at)
    if pd.isna(base):raise ValueError('Thiếu ngày biết hợp đồng')
    steps=list(steps)
    if not steps:raise ValueError('Bậc giá thuê thiếu tại đầu kỳ')
    step_dates=[pd.Timestamp(s.get('known_at',known_at)) for s in steps]
    if any(pd.isna(c) for c in step_dates):raise ValueError('Thiếu ngày biết bậc giá')
    clocks=sorted({max(base,c) for c in step_dates})
    if asof is not None:
        cutoff=pd.Timestamp(asof)
        if pd.isna(cutoff):raise ValueError('Ngày dự báo không hợp lệ')
        clocks=sorted({c for c in clocks if c<=cutoff} | ({cutoff} if base<=cutoff else set()))
    rows=[]
    for period in pd.PeriodIndex(months,freq='M'):
        due=pd.Timestamp(period.year,period.month,min(due_day,period.days_in_month))
        previous=None
        for clock in clocks:
            matches=[s for s in steps if max(base,pd.Timestamp(s.get('known_at',known_at)))<=clock and
                pd.Timestamp(s['effective_from'])<=period.start_time and
                (not s.get('effective_to') or pd.Timestamp(s['effective_to'])>=period.start_time)]
            if not matches:
                if clock==clocks[-1]:raise ValueError('Bậc giá thuê thiếu tại đầu kỳ')
                continue
            latest=max(max(base,pd.Timestamp(s.get('known_at',known_at))) for s in matches)
            matches=[s for s in matches if max(base,pd.Timestamp(s.get('known_at',known_at)))==latest]
            if len(matches)!=1:raise ValueError('Bậc giá thuê chồng lấn cùng ngày ghi nhận')
            step=matches[0]
            if previous==step:continue
            previous=step
            rows.append(dict(obligation_id=f'{contract_id}:{period}',category='rent_contract',due_date=due,
                amount=money(step['amount']),known_at=latest,source=source,
                verified=_verified(step.get('verified',False)),business_day=business_day))
    return rows


def loan_events(contract_id,installments,*,known_at,source):
    """Gốc/lãi theo hợp đồng. Giữ installment_id khi sửa ngày/số tiền một kỳ;
    nếu không khai mã kỳ, ngày trả làm định danh (không phụ thuộc thứ tự danh sách).
    """
    rows=[]
    for installment in installments:
        identifier=installment.get('installment_id',installment['date'])
        for field,category in [('principal','loan_principal'),('interest','loan_interest')]:
            rows.append(dict(obligation_id=f'{contract_id}:{identifier}:{field}',category=category,
                due_date=installment['date'],amount=money(installment[field]),
                known_at=installment.get('known_at',known_at),source=source,
                verified=_verified(installment.get('verified',False)),business_day=installment.get('business_day','none')))
    return rows


def weekly_extended_cash(schedule,cutoff,k=13):
    """Trả hai mảng thu/chi riêng, không coi hoàn VAT là chi âm."""
    inflows=np.zeros(k);outflows=np.zeros(k);cutoff=pd.Timestamp(cutoff)
    for index in range(k):
        period=schedule[(schedule.date>cutoff+pd.Timedelta(days=7*index))&
            (schedule.date<=cutoff+pd.Timedelta(days=7*(index+1)))& (schedule.known_at<=cutoff)]
        inflows[index]=period.loc[period.direction=='inflow','amount'].sum()
        outflows[index]=period.loc[period.direction=='outflow','amount'].sum()
    return inflows,outflows
