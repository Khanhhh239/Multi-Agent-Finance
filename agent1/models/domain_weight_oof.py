"""Ablation tỷ lệ mật độ: dự đoán ngoài công ty, không chấm lại mẫu đã fit."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score
from agent1.threads import NT
from .features import FEATURES


def company_folds(source,target,n_splits=4,seed=7):
    keys=np.r_['src/'+source.firm_id.astype(str).to_numpy(),'tgt/'+target.firm_id.astype(str).to_numpy()]
    rng=np.random.default_rng(seed);mapping={}
    for prefix,frame in [('src/',source),('tgt/',target)]:
        firms=np.sort(frame.firm_id.astype(str).unique())
        if len(firms)<n_splits:raise ValueError('Không đủ DN cho fold ngoài công ty')
        for index,firm in enumerate(rng.permutation(firms)):mapping[prefix+firm]=index%n_splits
    assigned=np.array([mapping[key] for key in keys])
    return [(np.flatnonzero(assigned!=fold),np.flatnonzero(assigned==fold)) for fold in range(n_splits)]


def oof_domain_weights(source,target,*,origin,feats=FEATURES):
    for frame in [source,target]:
        cutoff=pd.to_datetime(frame.cutoff)
        if cutoff.isna().any() or (cutoff>=pd.Timestamp(origin)).any():raise ValueError('Chỉ dùng snapshot trước thời điểm test')
    X=np.vstack([source[feats].to_numpy(dtype='float32'),target[feats].to_numpy(dtype='float32')])
    y=np.r_[np.zeros(len(source)),np.ones(len(target))];prob=np.full(len(y),np.nan);ratio=np.zeros(len(source));fold_rows=[]
    for fold,(train,heldout) in enumerate(company_folds(source,target)):
        model=lgb.train(dict(objective='binary',learning_rate=.05,num_leaves=31,min_data_in_leaf=200,
            verbose=-1,num_threads=NT,seed=7),lgb.Dataset(X[train],y[train]),200)
        p=np.clip(model.predict(X[heldout]),.01,.99);prob[heldout]=p
        is_source=heldout<len(source);indices=heldout[is_source];sp=p[is_source]
        ratio[indices]=sp/(1-sp)*np.sum(y[train]==0)/np.sum(y[train]==1)
        fold_rows.append(dict(fold=fold,n_train=len(train),n_heldout=len(heldout),
            n_source_train=int(np.sum(y[train]==0)),n_target_train=int(np.sum(y[train]==1))))
    if not np.isfinite(prob).all() or not (ratio>0).all():raise ValueError('Fold thiếu dự đoán')
    weights=np.clip(ratio/ratio.mean(),.05,20)
    return weights,dict(oof_domain_AUC=roc_auc_score(y,prob),folds=fold_rows,
        weight_min=float(weights.min()),weight_max=float(weights.max()),weight_std=float(weights.std()),
        effective_sample_size=float(weights.sum()**2/np.square(weights).sum()))
