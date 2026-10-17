"""Readable JSONL audit traces for experimental CLI sessions."""
from dataclasses import asdict,is_dataclass
from datetime import datetime,timezone
from pathlib import Path
import json,uuid
from .constants import NOTICE
from .untrusted import wrap_untrusted

def public_data(value):
    if is_dataclass(value): value=asdict(value)
    if isinstance(value,dict):
        return {k:public_data(v) for k,v in value.items() if not k.startswith('_') and k!='description'}
    if isinstance(value,(list,tuple)): return [public_data(v) for v in value]
    return value

class TraceWriter:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)

    def append(self,question,reply):
        record={'request_id':str(uuid.uuid4()),'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                'experimental_notice':NOTICE,'G0_7':'CHƯA ĐẠT','question':wrap_untrusted(question,'trace.question',limit=1200),
                'behavior':reply.behavior,'answer':reply.text,'usage':reply.usage,'latency_ms':reply.latency_ms,
                'lineage_ids':reply.blocks.get('lineage_ids',[]),'calls':reply.blocks.get('calls',[]),
                'steps':public_data(reply.trace)}
        with self.path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
        return record['request_id']
