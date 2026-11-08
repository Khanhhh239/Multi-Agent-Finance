"""Đếm xoá nợ cohort trước bằng lịch sự kiện; không đọc trạng thái cuối kỳ."""
import numpy as np
import pandas as pd


def prior_cohort_features(history, queries, publication_lag_days=90):
    """Cohort [T-2 năm,T-1 năm), chỉ charge-off có ngày công bố giả định <=T.

    90 ngày là giả định độ trễ công bố để thử độ nhạy, không phải vintage SBA thật.
    Mẫu số gồm mọi phê duyệt có ngày hợp lệ, không lọc LoanStatus nhìn từ tương lai.
    """
    if publication_lag_days < 0:
        raise ValueError('Độ trễ công bố phải không âm')
    approved=pd.to_datetime(history.ApprovalDate,errors='coerce')
    charged=pd.to_datetime(history.ChargeOffDate,errors='coerce')
    valid=approved.notna();approved=approved[valid].reset_index(drop=True)
    charged=charged[valid].reset_index(drop=True)
    dates=approved.to_numpy(dtype='datetime64[ns]');coordinates=np.sort(np.unique(dates))
    known=(charged+pd.Timedelta(days=publication_lag_days)).to_numpy(dtype='datetime64[ns]')
    event_mask=charged.notna().to_numpy() & (charged>=approved).to_numpy()
    events=np.flatnonzero(event_mask);events=events[np.argsort(known[events],kind='stable')]
    ranks=np.searchsorted(coordinates,dates)+1;tree=np.zeros(len(coordinates)+1,dtype=np.int64)
    approvals=np.sort(dates);query=pd.to_datetime(queries)
    if query.isna().any():raise ValueError('Ngày truy vấn không hợp lệ')
    result=np.zeros((len(query),3),dtype=float);cursor=0

    def prefix(end):
        value=0
        while end>0:value+=tree[end];end-=end & -end
        return value

    for index in np.argsort(query.to_numpy(),kind='stable'):
        now=pd.Timestamp(query.iloc[index] if hasattr(query,'iloc') else query[index])
        while cursor<len(events) and known[events[cursor]]<=now.to_datetime64():
            pos=ranks[events[cursor]]
            while pos<len(tree):tree[pos]+=1;pos+=pos & -pos
            cursor+=1
        left=(now-pd.DateOffset(years=2)).to_datetime64();right=(now-pd.DateOffset(years=1)).to_datetime64()
        n=np.searchsorted(approvals,right)-np.searchsorted(approvals,left)
        count=prefix(int(np.searchsorted(coordinates,right)))-prefix(int(np.searchsorted(coordinates,left)))
        result[index]=[count/max(n,1),n,float(n==0)]
    return pd.DataFrame(result,columns=['prior_cohort_chgoff_rate','prior_cohort_n','prior_cohort_missing'],index=getattr(queries,'index',None))
