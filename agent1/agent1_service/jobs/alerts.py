"""Mô phỏng gửi cảnh báo vào file mã hoá; tối đa hai đợt mỗi tuần/DN."""
import json
import uuid
import pandas as pd
from agent1.text.verbalize import verbalize


def emit_alert(store,directory,firm,result,threshold=.5):
    T=pd.Timestamp(result['cutoff']);week=str(T.to_period('W-SUN'))
    existing=store.get(firm,'alerts')
    current=[a for a in existing if a.get('week')==week]
    if len(current)>=2 or result['shortfall_4w']<threshold:
        return None
    cause='shortfall_4w'
    if any(a.get('cause')==cause for a in current):return None
    table={'week':4,'balance_text':str(round(result['band'][3]['P50'])),
           'risk_text':f"{100*result['shortfall_4w']:.1f}%"}
    text=verbalize(table)
    record=dict(id=uuid.uuid4().hex,week=week,cause=cause,table=table,text=text,delivery='simulated_file')
    store.put(firm,'alerts',[record])
    encrypted=store.cipher.encrypt(json.dumps(record,ensure_ascii=False).encode()).decode()
    with (directory/'alerts.encrypted.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(dict(firm=firm,ciphertext=encrypted))+'\n')
    return record
