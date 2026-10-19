"""python -m agent4.agent.cli --model qwen3:4b-instruct-2507-q4_K_M"""
from __future__ import annotations
import argparse,json,re,sys
from dataclasses import asdict
from pathlib import Path
from agent4.config import get_settings,LLMConfig
from agent4.engine.engine import ExecutionEngine,EngineError
from .constants import NOTICE
from .llm import OllamaClient
from .orchestrator import CFOAgent,AgentReply,Step
from .policy import AgentConfig
from .state import ConversationState
from .tools import Principal,execute
from .preprocess import Hints
from .validator import validate
from .render import render_facts
from .verifier import verify
from .trace import TraceWriter,public_data
from .pipeline import PipelineAgent,PipelineConfig

def form_query(engine,metric,period,principal):
    try:
        definition=engine.get_definition(metric)
    except EngineError:
        return AgentReply('Chỉ số form không hợp lệ.\n'+NOTICE,{'error':{'code':'METRIC_NOT_FOUND'}},'refuse',[],{},0)
    checked=validate({'action':'query_metric','metric':metric,'period':period},hints=Hints(view_hint='tax' if definition.default_view=='tax' else None),
                     candidates=[metric],principal=principal,engine=engine)
    if not checked.ok:
        return AgentReply('Yêu cầu form chưa hợp lệ.\n'+NOTICE,{},'refuse',[],{},0)
    outcome=execute(checked.fixed_call,engine,principal)
    if not outcome.ok: return AgentReply('Không thể tra cứu trong phạm vi cho phép.\n'+NOTICE,{'error':outcome.error},'refuse',[],{},0)
    block=render_facts([outcome.data])
    result=verify(block.text,block.allowed,block.required_labels)
    return AgentReply(block.text if result.ok else 'Chưa xác minh được nguồn.\n'+NOTICE,
        {'calls':[checked.fixed_call],'results':[outcome.data],'lineage_ids':block.lineage_ids,'G0_7':'CHƯA ĐẠT','experimental_notice':NOTICE},
        'answer' if result.ok else 'refuse',[Step('form_query',0,{'ok':result.ok})],{},0)

def main(argv=None):
    settings=get_settings()
    parser=argparse.ArgumentParser(description='CFO ảo P1 thử nghiệm — '+NOTICE)
    parser.add_argument('--model',default=None)
    parser.add_argument('--config',type=Path,help='P2 experimental JSON/YAML-subset pipeline configuration')
    parser.add_argument('--db',type=Path,default=settings.warehouse_path)
    parser.add_argument('--num-ctx',type=int,default=None)
    parser.add_argument('--trace',type=Path,default=settings.warehouse_path.parent/'traces/cli.jsonl')
    parser.add_argument('--question',action='append',default=[])
    parser.add_argument('--samples',type=int,choices=range(1,31),metavar='1..30')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--no-commentary',action='store_true')
    parser.add_argument('--query',help='Tra cứu form không cần model, bằng metric ID')
    parser.add_argument('--period',default=None)
    args=parser.parse_args(argv)
    pipeline=PipelineConfig(**json.loads(args.config.read_text(encoding='utf8'))) if args.config else None
    args.model=args.model or (pipeline.model if pipeline else 'qwen3:4b-instruct-2507-q4_K_M')
    args.num_ctx=args.num_ctx or (pipeline.num_ctx if pipeline else 4096)
    if not args.db.exists(): parser.error('Chưa có kho dữ liệu; chạy python -m agent4.datagen.build trước.')
    if args.num_ctx<1024 or args.num_ctx>8192: parser.error('num-ctx trong thử nghiệm phải từ 1024 đến 8192.')
    principal=Principal()
    writer=TraceWriter(args.trace)
    questions=list(args.question)
    if args.samples:
        sample=Path(__file__).resolve().parents[2]/'reference_v0/sample-questions.md'
        questions+=re.findall(r'^\d+\. (.+)$',sample.read_text(encoding='utf-8'),re.M)[:args.samples]
    def output(q,reply):
        trace_id=writer.append(q,reply)
        if args.json:
            print(json.dumps({'question':q,'request_id':trace_id,**public_data(reply)},ensure_ascii=False,default=str),flush=True)
        else:
            print(reply.text,flush=True)
            print(f"[token vào/ra: {reply.usage.get('prompt_tokens',0)}/{reply.usage.get('eval_tokens',0)}; {reply.latency_ms:.0f} ms; trace {trace_id}]",flush=True)
    with ExecutionEngine(args.db) as engine:
        if args.query:
            output(args.query,form_query(engine,args.query,args.period,principal))
            return 0
        cfg=LLMConfig(model=args.model,num_ctx=args.num_ctx,timeout_s=pipeline.max_duration_s if pipeline else 20)
        with OllamaClient(cfg) as client:
            if pipeline:
                if args.no_commentary:pipeline.answer_mode='template'
                agent=PipelineAgent(engine,client,pipeline)
            else:agent=CFOAgent(engine,client,cfg=AgentConfig(commentary=not args.no_commentary))
            state=ConversationState(user_id=principal.user_id)
            if questions:
                for question in questions: output(question,agent.ask(question,principal,state))
            else:
                print('CFO ảo — P1 thử nghiệm; '+NOTICE+'. Gõ /quit để thoát.',file=sys.stderr)
                for line in sys.stdin:
                    question=line.strip()
                    if question in ('/quit','/exit'): break
                    if not question: continue
                    output(question,agent.ask(question,principal,state))
    return 0

if __name__=='__main__': raise SystemExit(main())
