"""Small, expiring conversation state. JSON is used as a YAML subset."""
from dataclasses import dataclass,field
import json,time
from .packer import pack_facts

@dataclass
class ConversationState:
    last_metric: str|None = None
    last_period: str|dict|None = None
    last_filters: dict = field(default_factory=dict)
    last_group_by: str|None = None
    last_view: str|None = None
    last_result: dict = field(default_factory=dict)
    pending_clarification: dict|None = None
    history: list[dict] = field(default_factory=list)
    user_id: str|None = None
    updated_at: float = field(default_factory=time.time)

    def active(self,user_id=None,now=None):
        return (now or time.time())-self.updated_at<=900 and (not self.user_id or not user_id or self.user_id==user_id)

    def summary(self):
        # <=80 UTF-8 bytes is an upper bound of 80 byte-level BPE tokens.
        # Include only whole fields; the full state still informs deterministic hints.
        result={}
        for key,value in [('m',self.last_metric),('p',self.last_period),('v',self.last_view),('g',self.last_group_by),('f',self.last_filters)]:
            candidate={**result,key:value}
            if value and len(json.dumps(candidate,ensure_ascii=True,separators=(',',':')).encode())<=80:
                result=candidate
        return json.dumps(result,ensure_ascii=True,separators=(',',':'))

def update(state,call,result,*,question='',user_id=None):
    state=state or ConversationState()
    if call.get('action') in ('query_metric','explain_metric'):
        state.last_metric=call.get('metric')
        state.last_period=call.get('period')
        resolved=result.get('filters') or {}
        state.last_filters={key:[row['code'] for row in rows] for key,rows in resolved.items()}
        if 'exclude_top_customers' in (call.get('filters') or {}):
            state.last_filters['exclude_top_customers']=call['filters']['exclude_top_customers']
        state.last_group_by=call.get('group_by')
        state.last_view=call.get('view')
        state.last_result=pack_facts(result)
        state.pending_clarification=None
    elif call.get('action')=='ask_clarification':
        state.pending_clarification=call
    state.history=(state.history+[{'question':question,'action':call.get('action'),'metric':call.get('metric')}])[-3:]
    state.updated_at=time.time()
    state.user_id=user_id or state.user_id
    return state
