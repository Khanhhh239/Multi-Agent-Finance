"""Nhánh nghiên cứu không có hạn: prior 30 ngày, cờ rõ ràng và tuổi HĐ."""
import pandas as pd
from .features import SnapshotBuilder


class NoDueSnapshotBuilder(SnapshotBuilder):
    def __init__(self,invoices,*args,**kwargs):
        inv=invoices.copy()
        if 'due_date' not in inv:inv['due_date']=pd.NaT
        self.missing=set(inv.loc[inv.due_date.isna(),'invoice_id'])
        inv['due_date']=inv.due_date.fillna(inv.issue_date+pd.Timedelta(days=30))
        super().__init__(inv,*args,**kwargs)

    def snapshot(self,T,visible_from=None,firms=None):
        result=super().snapshot(T,visible_from=visible_from,firms=firms)
        if result.empty:return result
        absent=result.invoice_id.isin(self.missing)
        result['no_due']=absent.astype(int)
        result.loc[absent,'has_due']=0
        result.loc[absent,'days_to_due']=result.loc[absent,'age_days']
        return result
