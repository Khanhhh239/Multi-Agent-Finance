"""Phiên bản T1 local mã hoá cùng kho dữ liệu; không tự nâng thành mô hình pilot."""
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from agent1.models import t1
from agent1.models.features import FEATURES


def code_signature():
    root=Path(__file__).resolve().parents[1]
    return hashlib.sha256(b''.join((root/p).read_bytes() for p in
        ['agent1/models/features.py','agent1/models/t1.py','agent1/calendar_vn.py'])).hexdigest()


def register(store,firm,model,metadata,reference):
    if model.booster is None:raise ValueError('Mô hình chưa fit')
    payload=dict(metadata)
    payload.update(model_text=model.booster.model_to_string(),features=list(model.feats),code_signature=code_signature(),
                   research_only=True,reference={c:pd.to_numeric(reference[c],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna().head(1000).tolist()
                                                 for c in FEATURES})
    payload['model_sha256']=hashlib.sha256(payload['model_text'].encode()).hexdigest()
    payload['id']=hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]
    store.put(firm,'model_registry',[payload])
    return {k:v for k,v in payload.items() if k not in {'model_text','reference'}}


def load(store,firm,cutoff):
    active=store.get(firm,'model_active')
    if not active:return None,None
    identifier=active[0]['version']
    record=next((r for r in store.get(firm,'model_registry') if r['id']==identifier),None)
    if record is None:raise ValueError('Không tìm thấy phiên bản đang dùng')
    if record['code_signature']!=code_signature() or record['features']!=FEATURES:
        raise ValueError('Mã/đặc trưng đã thay đổi; cần huấn luyện lại')
    if hashlib.sha256(record['model_text'].encode()).hexdigest()!=record['model_sha256']:
        raise ValueError('Hash mô hình không khớp')
    if pd.Timestamp(record['available_at'])>pd.Timestamp(cutoff):
        raise ValueError('Phiên bản mô hình chưa tồn tại tại ngày dự báo')
    model=t1.HazardGBM();model.booster=lgb.Booster(model_str=record['model_text'])
    return model,record


def activate(store,firm,version):
    if not any(r['id']==version for r in store.get(firm,'model_registry')):
        raise ValueError('Không tìm thấy phiên bản của DN')
    store.put(firm,'model_active',[dict(id='active',version=version,research_only=True)])


def summaries(store,firm):
    active=store.get(firm,'model_active')
    selected=active[0]['version'] if active else None
    return [dict({k:v for k,v in r.items() if k not in {'model_text','reference'}},active=r['id']==selected)
            for r in store.get(firm,'model_registry')]
