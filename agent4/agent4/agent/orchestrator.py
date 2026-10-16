"""Hints -> retrieval -> constrained model -> validation -> engine -> verified facts."""
from __future__ import annotations
from dataclasses import dataclass,field,asdict
from time import perf_counter
import hashlib,json,re
from .constants import NOTICE
from .llm import LLMUnavailable
from .preprocess import analyze
from .retriever import MetricRetriever,Candidate
from .validator import validate,repair_prompt as call_repair
from .tools import execute,Principal,build_union_schema,principal_access
from .packer import pack_facts
from .render import render_facts
from .verifier import verify,mentions,Violation,repair_prompt as answer_repair
from .prompts import build_messages,COMMENTARY_SCHEMA,COMMENTARY_SYSTEM
from .fewshot import FewShotBank
from .state import ConversationState,update
from .policy import AgentConfig,should_clarify,use_think
from .guardrails import pre_filter,protect_result

@dataclass
class Step:
    stage: str
    elapsed_ms: float
    data: dict = field(default_factory=dict)

@dataclass
class AgentReply:
    text: str
    blocks: dict
    behavior: str
    trace: list[Step]
    usage: dict
    latency_ms: float

class CFOAgent:
    def __init__(self,engine,llm,retriever=None,cfg=None,ops=None):
        self.engine,self.llm=engine,llm
        self.retriever=retriever or MetricRetriever()
        self.cfg=cfg or AgentConfig()
        self.examples=FewShotBank()
        self.ops=ops # No P1 write handler is exposed.

    def ask(self,question,principal=None,state=None):
        principal=principal or Principal()
        state=state or ConversationState(user_id=principal.user_id)
        if not state.active(principal.user_id): state=ConversationState(user_id=principal.user_id)
        start=perf_counter()
        steps=[]
        usage={'prompt_tokens':0,'eval_tokens':0}
        results=[]
        def log(stage,**data):
            steps.append(Step(stage,(perf_counter()-start)*1000,data))
        def finish(text,behavior='answer',**blocks):
            if NOTICE not in text: text+='\n'+NOTICE
            blocks.update(experimental_notice=NOTICE,G0_7='CHƯA ĐẠT')
            return AgentReply(text,blocks,behavior,steps,dict(usage),(perf_counter()-start)*1000)
        def call_model(messages,schema,num_predict=256):
            remaining=self.cfg.max_duration_s-(perf_counter()-start)
            if remaining<=0: raise LLMUnavailable('Đã hết thời gian thử nghiệm.')
            response=self.llm.chat(messages,schema=schema,options={'num_predict':num_predict,'_timeout_s':remaining},think=False)
            for key in usage: usage[key]+=response.usage.get(key,0)
            log('llm',usage=response.usage,latency_ms=response.latency_ms)
            return response
        log('policy',notice=NOTICE)
        if not isinstance(question,str) or not question.strip() or len(question)>2000:
            return finish('Câu hỏi trống hoặc quá dài.','clarify')
        guarded=pre_filter(question)
        hints=analyze(guarded.normalized,self.engine,state)
        hints.cues.update(guarded.cues)
        log('guardrails',cues=sorted(guarded.cues),warnings=guarded.warnings)
        log('hints',hints=hints.data())
        if not principal_access(principal):
            return finish('Vai trò hoặc phạm vi không cho phép tra cứu.','refuse')
        if hints.cues.intersection({'unsafe_action','out_of_scope','jailbreak'}):
            log('policy_refusal',cues=sorted(hints.cues))
            return finish('Yêu cầu ngoài phạm vi tra cứu hoặc không an toàn. Có thể tra chỉ số tài chính và xem nguồn.','refuse')
        candidates=self.retriever.topk(question,8,hints=hints)
        if candidates and not principal_access(principal,candidates[0].metric):
            return finish('Chỉ số được hỏi vượt quyền của vai trò hiện tại.','refuse')
        inherited=hints.inherited.get('metric')
        if inherited and all(c.metric!=inherited for c in candidates):
            candidates=[Candidate(inherited,1.0),*candidates][:8]
        candidates=[c for c in candidates if principal_access(principal,c.metric)]
        log('retriever',candidates=[asdict(c) for c in candidates])
        if should_clarify(candidates,hints):
            options=[{'label':self.engine.get_definition(c.metric).label,'patch':{'metric':c.metric}} for c in candidates[:3]]
            if not options:
                options=[{'label':'Doanh thu thuần','patch':{'metric':'net_revenue'}},{'label':'Phải thu','patch':{'metric':'ar_balance'}}]
            return finish('Bạn muốn xem chỉ số hoặc loại lợi nhuận nào?','clarify',options=options)
        examples=self.examples.select_examples(question,12)
        messages=build_messages(question,hints,candidates,state,examples)
        schema=build_union_schema([c.metric for c in candidates])
        log('prompt',sha256=hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest(),
            characters=sum(len(m['content']) for m in messages),preview=messages[-1]['content'][:240])
        call=None
        for attempt in range(self.cfg.repair_attempts+1):
            try:
                response=call_model(messages,schema)
                if response.tool_calls:
                    function=response.tool_calls[0].get('function',{})
                    arguments=function.get('arguments',{})
                    if isinstance(arguments,str): arguments=json.loads(arguments)
                    proposed={'action':function.get('name'),**arguments}
                else: proposed=json.loads(response.text)
                checked=validate(proposed,hints=hints,candidates=candidates,principal=principal,engine=self.engine)
                log('validator',ok=checked.ok,action=checked.action,issues=[asdict(e) for e in checked.errors],call=checked.fixed_call)
            except (ValueError,TypeError):
                log('validator',ok=False,action='repair',issues=[{'code':'INVALID_JSON'}])
                checked=None
            except LLMUnavailable:
                log('llm_unavailable')
                return finish('Model chưa sẵn sàng. Chọn chỉ số và kỳ ở chế độ tra cứu có cấu trúc.','clarify',form_options=[c.metric for c in candidates])
            if checked and checked.ok:
                call=checked.fixed_call
                break
            if checked and checked.action in ('refuse','clarify'):
                text='Không thể thực hiện yêu cầu trong phạm vi được phép.' if checked.action=='refuse' else 'Cần làm rõ chỉ số, khung hoặc thực thể trước khi tra cứu.'
                return finish(text,checked.action,options=[{'label':self.engine.get_definition(c.metric).label,'patch':{'metric':c.metric}} for c in candidates[:3]])
            messages.append({'role':'user','content':call_repair(checked.errors) if checked else 'Fix JSON to match the schema. Use candidate metric and HINTS.'})
        if call is None: return finish('Chưa nhận được lời gọi hợp lệ. Hãy chọn chỉ số và kỳ.','clarify',form_options=[c.metric for c in candidates])
        if call['action']=='refuse': return finish('Yêu cầu ngoài phạm vi hoặc chưa đủ quyền.','refuse')
        if call['action']=='ask_clarification':
            update(state,call,{},question=question,user_id=principal.user_id)
            options=[{'label':self.engine.get_definition(o['patch']['metric']).label if o['patch'].get('metric') else 'Chọn kỳ phù hợp',
                      'patch':o['patch']} for o in call['options']]
            return finish('Bạn muốn xem chỉ số nào?','clarify',options=options)
        outcome=execute(call,self.engine,principal)
        log('engine',ok=outcome.ok,call=call,error=outcome.error,lineage_id=outcome.data.get('audit_trail',{}).get('lineage_id'))
        if not outcome.ok:
            return finish('Không thể tra cứu: '+outcome.error['message'],'refuse',error=outcome.error)
        if call['action']=='propose_action':
            return finish('Đề xuất thử nghiệm đã soạn nháp; chưa lưu và chưa thực thi.','propose',proposal=outcome.data)
        if call['action'] not in ('query_metric','explain_metric'):
            return finish('Thông tin danh mục đã được tra cứu; chọn chỉ số để xem số liệu.','clarify',catalog=pack_facts(outcome.data))
        results.append(outcome.data)
        results=[protect_result(r) for r in results]
        block=render_facts(results,hints,question=question)
        log('render',lineage_ids=block.lineage_ids)
        base_check=verify(block.text,block.allowed,block.required_labels)
        log('verifier_facts',ok=base_check.ok,violations=[asdict(v) for v in base_check.violations])
        if not base_check.ok:
            return finish('Khối sự kiện chưa qua xác minh; cần rà soát nguồn trước khi trả số.','refuse')
        text=block.text
        if self.cfg.commentary and call['action']=='query_metric':
            commentary_messages=[{'role':'system','content':COMMENTARY_SYSTEM},
                {'role':'user','content':json.dumps([pack_facts(r) for r in results],ensure_ascii=False)}]
            for attempt in range(self.cfg.verify_attempts+1):
                try:
                    response=call_model(commentary_messages,COMMENTARY_SCHEMA,128)
                    commentary=json.loads(response.text).get('commentary','')
                    if not isinstance(commentary,str): raise ValueError()
                    combined=block.text+'\n'+commentary
                    checked=verify(combined,block.allowed,block.required_labels)
                    # All numerical output remains in the deterministic block.
                    if re.search(r'\d',commentary) or list(mentions(commentary)):
                        checked.ok=False
                        checked.violations.append(Violation('NUMERIC_COMMENTARY','Diễn giải phải định tính.'))
                    log('verifier',ok=checked.ok,violations=[asdict(v) for v in checked.violations])
                    if checked.ok:
                        text=combined
                        break
                    commentary_messages.append({'role':'user','content':answer_repair(checked.violations)})
                except (LLMUnavailable,ValueError,TypeError):
                    log('commentary_unavailable')
                    break
            else: log('verifier_fallback')
        update(state,call,outcome.data,question=question,user_id=principal.user_id)
        return finish(text,facts=[pack_facts(r) for r in results],caveats=block.caveats,lineage_ids=block.lineage_ids,
                      calls=[call],results=results,required_labels=block.required_labels)
