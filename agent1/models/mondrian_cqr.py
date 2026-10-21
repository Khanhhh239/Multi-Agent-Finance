"""CQR hai phía theo kỳ đáo hạn; chỉ fit trên cửa sổ hiệu chỉnh nguồn."""
import numpy as np
from . import t1


def maturity_groups(days_to_due):
    days=np.asarray(days_to_due,float)
    return np.select([~np.isfinite(days),days<0,days<=14,days<=42],
        ['unknown','overdue','weeks_1_2','weeks_3_6'],default='after_week_6')


class MondrianCQR:
    def __init__(self,min_group=100):self.min_group=min_group

    def fit(self,y,quantiles,days_to_due):
        groups=maturity_groups(days_to_due)
        if len(groups)!=len(y) or len(quantiles)!=len(y):raise ValueError('Cohort calibration khác độ dài')
        self.fallback=t1.cqr_fit_asym(y,quantiles,allow_shrink=True)
        self.offsets={};self.counts={}
        for group in np.unique(groups):
            mask=groups==group;self.counts[group]=int(mask.sum())
            self.offsets[group]=t1.cqr_fit_asym(np.asarray(y)[mask],quantiles[mask],allow_shrink=True) if mask.sum()>=self.min_group else self.fallback
        return self

    def apply(self,quantiles,days_to_due):
        if not hasattr(self,'fallback'):raise ValueError('Chưa fit calibration nguồn')
        groups=maturity_groups(days_to_due);result=np.asarray(quantiles,float).copy()
        if len(groups)!=len(result):raise ValueError('Cohort khác độ dài')
        for group in np.unique(groups):
            mask=groups==group
            result[mask]=t1.cqr_apply_asym(result[mask],self.offsets.get(group,self.fallback))
        return result
