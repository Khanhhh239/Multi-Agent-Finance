"""Chẩn đoán khác miền bằng công ty giữ lại, không dùng để chọn tham số đích."""
import numpy as np
from sklearn.metrics import roc_auc_score


def split_companies(frame,seed=7):
    rng=np.random.default_rng(seed);groups=sorted(frame.firm_id.unique())
    if len(groups)<2:raise ValueError('Cần ít nhất hai công ty để giữ lại công ty kiểm tra')
    shuffled=rng.permutation(groups);n=max(1,int(.3*len(groups)))
    held=set(shuffled[:n]);test=frame.firm_id.isin(held)
    return frame[~test].copy(),frame[test].copy()


def auc_cluster_ci(labels,predictions,domains,companies,n_boot=300,seed=7):
    labels,predictions,domains,companies=map(np.asarray,[labels,predictions,domains,companies])
    rng=np.random.default_rng(seed);strata=[]
    for domain in np.unique(domains):
        groups=np.unique(companies[domains==domain])
        strata.append([np.flatnonzero((domains==domain)&(companies==group)) for group in groups])
    values=[]
    for _ in range(n_boot):
        indices=np.concatenate([np.concatenate([groups[i] for i in rng.integers(len(groups),size=len(groups))]) for groups in strata])
        values.append(roc_auc_score(labels[indices],predictions[indices]))
    low,high=np.quantile(values,[.025,.975])
    return float(low),float(high)
