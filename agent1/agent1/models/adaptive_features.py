"""Đặc trưng phản ứng nhanh cho ablation; không đổi bộ đặc trưng mặc định."""
import numpy as np
import pandas as pd
from .features import SnapshotBuilder


class AdaptiveSnapshotBuilder(SnapshotBuilder):
    def __init__(self,*args,**kwargs):
        kwargs['ewm_halflife']=30.
        super().__init__(*args,**kwargs)

    def snapshot(self,T,visible_from=None,firms=None):
        snapshot=super().snapshot(T,visible_from=visible_from,firms=firms)
        if snapshot.empty:return snapshot
        T=pd.Timestamp(T);history=self.inv[(self.inv.issue_date<=T)&(self.inv.label_date<=T)]
        if visible_from is not None:history=history[history.issue_date>=pd.Timestamp(visible_from)]
        if firms is not None:history=history[history.firm_id.isin(firms)]
        delay=history.delay.clip(-60,240)
        prior=delay.groupby(history.customer_id).transform('mean')
        recent=history.label_date>T-pd.Timedelta(days=7)
        residual=(delay-prior)[recent].groupby(history.loc[recent,'firm_id']).mean()
        snapshot['f_resid_7d']=snapshot.firm_id.map(residual).astype(float)
        return snapshot
