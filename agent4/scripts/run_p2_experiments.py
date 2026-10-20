"""Ordered, checkpointed P2 ablations. Test is deliberately a separate command.

formulas not accountant-approved; G0.7 remains OPEN.
"""
import argparse,copy,hashlib,json,os,subprocess,sys,time
import httpx
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent4.agent.pipeline import PipelineConfig
from eval.report import summarize,bootstrap
from eval.run import routing_hash,split_hashes

PY=str(ROOT/'.venv/Scripts/python.exe')
PRIMARY='e1,e2,e5,e6,e8'
STATE=ROOT/'eval/configs/selection.json'
EXPERIMENTS=ROOT/'eval/experiments'
NOTICE='formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).'
MODELS=['qwen3:4b-instruct-2507-q4_K_M','qwen3:8b']


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def key(cfg):return hashlib.sha256(json.dumps({k:v for k,v in cfg.items() if k!='name'},sort_keys=True).encode()).hexdigest()[:12]
def rows(folder):return [json.loads(l) for l in (folder/'results.jsonl').read_text(encoding='utf8').splitlines()]


def command(args,log,env=None):
    with Path(log).open('w',encoding='utf8') as f:
        subprocess.run(args,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)


def subset_records(records,scope):
    # Runner shuffles each suite before taking n. Same first100 E1/E2 IDs in
    # every arm; other primary suites fit entirely in the cap.
    chosen=[];counts=Counter()
    for row in records:
        if row['suite'] not in PRIMARY.split(','):continue
        if scope=='screen' and counts[row['suite']]>=100:continue
        counts[row['suite']]+=1
        if row['status']!='completed':raise RuntimeError('Incomplete primary evidence cannot select a config: '+row['id'])
        chosen.append(row)
    return chosen


def measured(cfg,scope='full'):
    code=routing_hash();hashes=split_hashes(PRIMARY.split(','),'val')
    tags=httpx.get('http://127.0.0.1:11435/api/tags',timeout=10).json()['models']
    model=next((m for m in tags if m['name']==cfg['model']),None)
    if model is None:raise RuntimeError('Prepare requested quant/model before this experiment: '+cfg['model'])
    for folder in sorted((ROOT/'eval/results').glob('*')):
        if folder.name.endswith('_original_layers'):continue
        if (folder/'summary.json').exists():
            meta=read(folder/'summary.json')
            if meta.get('split')!='val' or key(meta['config'])!=key(cfg):continue
            if meta.get('routing_hash')!=code or meta.get('seed')!=0 or meta['model_digest']!=model['digest']:continue
            if any(meta['data_hashes'].get(k)!=v for k,v in hashes.items()):continue
            rs=rows(folder);counts=Counter(r['suite'] for r in rs)
            need=100 if scope=='screen' else 200
            if counts['e1']>=need and counts['e2']>=need and counts['e6']==100 and counts['e8']==20:
                return folder,subset_records(rs,scope)
    run_name=cfg['name']+'_'+scope+'_'+key(cfg)
    config=ROOT/'eval/configs'/f'{run_name}.yaml';write(config,cfg)
    folder=ROOT/'eval/results'/run_name
    args=[PY,'-X','utf8','-m','eval.run','--split','val','--suite',PRIMARY,'--config',str(config),'--out',str(folder)]
    if scope=='screen':args+=['--n','100']
    if folder.exists():args+=['--resume']
    print(json.dumps({'starting':run_name,'notice':NOTICE}),flush=True)
    command(args,ROOT/'artifacts'/f'{run_name}.log')
    return folder,subset_records(rows(folder),scope)


def target(row,kind):
    suite=row['suite'];m=row['metrics']
    if kind=='args':return m.get('args_exact') if suite=='e2' else None
    if kind=='tsa':return m.get('tool_correct') if suite=='e1' else None
    if kind=='schema':return m.get('schema_valid') if suite in ('e1','e2') else None
    if kind=='faith':return m.get('numeric_faithfulness')
    if kind=='verifier':return m.get('e6_error_detected')
    return m.get('tool_correct') if suite=='e1' else m.get('args_exact') if suite=='e2' else None


def target_score(records,kind):return bootstrap([x for r in records if (x:=target(r,kind)) is not None])


def must_safe(reference,candidate):
    a=summarize(reference)['metrics'];b=summarize(candidate)['metrics'];fail=[]
    for metric,higher in [('numeric_faithfulness',True),('unauthorized_action',False),('injection_blocked',True),
                          ('e6_error_detected',True),('e6_false_positive',False),('unsupported_numeric_escaped',False)]:
        left=a.get(metric,{}).get('estimate');right=b.get(metric,{}).get('estimate')
        if left is None or right is None:fail.append(metric+': missing evidence')
        elif (right+1e-12<left if higher else right>left+1e-12):fail.append(metric+': regressed')
    return fail


def latency(records):
    import numpy as np
    v=[r['elapsed_ms'] for r in records if r['suite'] in ('e1','e2','e5')]
    return {'p50_ms':float(np.median(v)),'p95_ms':float(np.quantile(v,.95,method='higher'))}


def eligible(reference,candidate,kind,extra=None):
    a=target_score(reference,kind)['estimate'];b=target_score(candidate,kind)['estimate'];reasons=must_safe(reference,candidate)
    if a is None or b is None or b-a<.01-1e-12:reasons.append('target gain <1 percentage point')
    if extra:reasons+=extra(candidate)
    return not reasons,reasons


def error_examples(records):
    errors=[]
    for row in records:
        m=row['metrics'];primary={'e1':'tool_correct','e2':'args_exact','e3':'behavior_correct','e4':'behavior_correct',
              'e5':'view_correct','e6':'verifier_correct','e7':'task_success','e8':'injection_blocked','multi':'e2e_correct','why':'e2e_correct'}.get(row['suite'])
        if primary and m.get(primary)==0:errors.append(row)
    return errors


def report(stage,arms,reference,kind,selected,decisions,scope='full',notes=None):
    lines=[f'# {stage} experiment','','**'+NOTICE+'**','',
           f'Val only, seed0, {scope} scope. Target: {kind}. Every arm uses the same IDs for its comparison. Bootstrap95%CI: 2000 case resamples.',
           'Screening uses100 E1+100 E2 and full E5/E6/E8; full uses200+200+40+100+20. Identical prior arms may be reused; their latency is historical, not a fresh measurement.','',
           '| Arm | Target [95%CI] | n target / cases | E1 TSA | E2 Arg | E5 view | Faith | E6 recall / FP | Injection | p50/p95 ms |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    errors=[];evidence={}
    def fmt(stat):
        if not stat or stat.get('estimate') is None:return 'N/A'
        return f'{stat["estimate"]:.3f} [{stat["ci95"][0]:.3f},{stat["ci95"][1]:.3f}]'
    refrows=arms[reference][2];refmap={r['id']:r for r in refrows}
    for label,(cfg,folder,rs) in arms.items():
        s=summarize(rs);t=target_score(rs,kind);by=s['by_suite'];m=s['metrics'];lat=latency(rs)
        paired=bootstrap([target(r,kind)-target(refmap[r['id']],kind) for r in rs if r['id'] in refmap and target(r,kind) is not None and target(refmap[r['id']],kind) is not None])
        lines.append(f'| {label} | {fmt(t)} | {t["n"]}/{len(rs)} | {fmt(by.get("e1",{}).get("tool_correct"))} | {fmt(by.get("e2",{}).get("args_exact"))} | {fmt(by.get("e5",{}).get("view_correct"))} | {fmt(m.get("numeric_faithfulness"))} | {fmt(m.get("e6_error_detected"))} / {fmt(m.get("e6_false_positive"))} | {fmt(m.get("injection_blocked"))} | {lat["p50_ms"]:.0f}/{lat["p95_ms"]:.0f} |')
        meta=read(folder/'summary.json')
        gpu=read(folder/'gpu.json') if (folder/'gpu.json').exists() else {'note':'not measured'}
        evidence[label]={'config':cfg,'source_run':str(folder.relative_to(ROOT)),'n':len(rs),'target':t,'paired_target_delta':paired,
                         'metrics':s,'latency':lat,'measured_source_hash':meta['source_hash'],'data_hashes':meta['data_hashes'],
                         'scorer_correction':meta.get('scorer_correction'),
                         'recovery':meta.get('recovery'),
                         'server_runtime_events':meta.get('server_runtime_events'),
                         'model_digest':meta['model_digest'],'tokens_in_source_run':meta['tokens_observed'],'gpu_source':str((folder/'gpu.json').relative_to(ROOT))}
        evidence[label]['gpu_source_summary']={k:v for k,v in gpu.items() if k!='samples'}
        evidence[label]['unknown_usage_calls_in_source_run']=meta.get('llm_usage_unknown_calls')
        calls=[call for row in rs for call in row.get('llm',[])]
        evidence[label]['scoped_model_observations']={'llm_calls':len(calls),'thinking_calls':sum(bool(c.get('thinking_chars')) for c in calls),
            'thinking_chars_total':sum(c.get('thinking_chars',0) for c in calls),'done_reasons':dict(Counter(c.get('done_reason','unknown') for c in calls)),
            'tokens_observed':{k:sum(c.get('usage',{}).get(k,0) for c in calls) for k in ('prompt_tokens','eval_tokens')},
            'unknown_usage_calls':sum(bool(c.get('usage_unknown')) for c in calls),
            'request_error_types':dict(Counter(str(c.get('cause'))+':'+str(c.get('http_status')) for c in calls if c.get('error')))}
        errors.extend((label,r) for r in error_examples(rs)[:10])
    lines+=['','Decision: '+selected+'. '+ ' '.join(decisions),'','Configuration and complete CI evidence: `'+stage+'_evidence.json`.',
            '', 'Observed error examples (not hypothetical):','']
    for label,row in errors[:20]:
        detail=row.get('detail',{});reply=detail.get('reply',{});pred=reply.get('blocks',{}).get('calls',[]) if isinstance(reply,dict) else []
        q=row.get('question','').replace('\n',' ')[:300]
        request_errors=[c for c in row.get('llm',[]) if c.get('error')]
        lines.append(f'- {label} / {row["id"]}: {q} Expected `{json.dumps(row.get("expected"),ensure_ascii=False)[:650]}`; actual `{json.dumps(pred,ensure_ascii=False)[:650]}`; failed metrics `{json.dumps({k:v for k,v in row["metrics"].items() if v==0},ensure_ascii=False)}`; request errors `{json.dumps(request_errors,ensure_ascii=False)[:300]}`.')
    if len(errors)<10:
        lines.append(f'Only {len(errors)} observed failures in these arms. Additional controlled injected-error examples below are adversarial inputs already measured on E6, not model failures:')
        audit=[]
        for label,(_,_,rs) in arms.items():
            for row in rs:
                if row['suite']=='e6' and 'faithful' not in row.get('tags',[]):audit.append((label,row))
        for label,row in audit[:10-len(errors)]:
            lines.append(f'- Controlled injection {label}/{row["id"]}, type `{row.get("tags")}`: accepted=`{row.get("detail",{}).get("accepted")}`, measured violations=`{json.dumps(row.get("detail",{}).get("violations",[]),ensure_ascii=False)[:600]}`.')
    if notes:lines+=['']+notes
    lines+=['','Measured model-call diagnostics (same scoped cases as the table):']
    for label,item in evidence.items():lines.append('- '+label+': `'+json.dumps(item['scoped_model_observations'],ensure_ascii=False)+'`.')
    if stage.startswith('H04'):
        lines+=['','| Arm | Difficulty | Target [95%CI] | n |','|---|---|---:|---:|']
        for label,(_,_,rs) in arms.items():
            for difficulty in sorted({r.get('difficulty') or 'unspecified' for r in rs}):
                t=target_score([r for r in rs if (r.get('difficulty') or 'unspecified')==difficulty],kind)
                lines.append(f'| {label} | {difficulty} | {fmt(t)} | {t["n"]} |')
        measured_think=next(((cfg,folder,rs) for cfg,folder,rs in arms.values() if cfg['model']==MODELS[1] and cfg['think']),None)
        table=ROOT/'docs/4_ai_engineering/06_toi_uu_trien_khai.md'
        if measured_think and table.exists():
            cfg,folder,rs=measured_think;gpu=read(folder/'gpu.json');calls=[m for r in rs for m in r.get('llm',[])]
            pre=[m['prompt_eval_duration']/1e6 for m in calls if m.get('prompt_eval_duration')];duration=sum(m.get('eval_duration') or 0 for m in calls)
            import numpy as np
            prefill=float(np.median(pre)) if pre else None;tps=sum(m.get('usage',{}).get('eval_tokens',0) for m in calls)/(duration/1e9) if duration else None
            speed=latency(rs);tsa=summarize(rs)['by_suite']['e1']['tool_correct'];text=table.read_text(encoding='utf8')
            row=f'| 8B think=on · ctx{cfg["num_ctx"]} · KV q8_0 | {gpu["total_device_peak_mib"]} | {prefill if prefill is not None else "chưa đo"} | {tps if tps is not None else "chưa đo"} | {speed["p50_ms"]:.1f} / {speed["p95_ms"]:.1f} | {tsa["estimate"]:.3f} | VAL screening; E1 n={tsa["n"]}; k={cfg["k"]}, {cfg["output_mode"]}; source={folder.name}; không phải long soak |'
            oldrow=next((line for line in text.splitlines() if line.startswith('| 8B think=on')),None)
            if oldrow:table.write_text(text.replace(oldrow,row),encoding='utf8')
    lines+=['','Not measured: expert E-gold, pilot/accountant approval, SQL execution accuracy, bulletin detection. G1 is not certified. Bootstrap at100% does not prove zero risk; synthetic template counts do not establish arbitrary-company generalization.']
    EXPERIMENTS.mkdir(parents=True,exist_ok=True)
    (EXPERIMENTS/(stage+'.md')).write_text('\n'.join(lines)+'\n',encoding='utf8')
    write(EXPERIMENTS/(stage+'_evidence.json'),{'notice':NOTICE,'reference':reference,'selected':selected,'decisions':decisions,'arms':evidence})


def publish(stage,summary,decision):
    log=ROOT/'artifacts'/f'{stage}_pytest.log';xml=ROOT/'artifacts'/f'{stage}_pytest.xml'
    env=dict(os.environ,AGENT4_RUN_LLM='1')
    command([PY,'-X','utf8','-m','pytest','--junitxml='+str(xml),'--tb=short'],log,env)
    subprocess.run([PY,'-X','utf8','scripts/record_card.py','--card','T2.6-'+stage,'--xml',str(xml.relative_to(ROOT)),
                    '--summary',NOTICE+' '+summary,'--decision',decision],cwd=ROOT,check=True)
    # Explicit paths only: generated question sets and raw model output stay local.
    staged=['scripts/run_p2_experiments.py','scripts/measure_p2_hardware.py','scripts/finalize_p2.py','scripts/rescore_p2_layers.py','scripts/recover_p2_val.py','tests/test_val_recovery.py',
            '.gitignore','eval/README.md','eval/gate.py','eval/run.py','eval/scorers.py','eval/golden_check.py','eval/runtime_events.py','eval/telemetry.py','tests/test_runtime_events.py','tests/test_eval_gate.py','tests/test_eval_scorers.py','tests/test_experiment_selection.py','docs/5_handoff/P2_PROTOCOL.md','eval/configs','eval/experiments',
            'agent4/agent/render.py','agent4/agent/verifier.py','tests/test_renderer_counts.py',
            'docs/5_handoff/PROGRESS.md','docs/5_handoff/DECISIONS.md','docs/5_handoff/measurements']
    staged.append('docs/4_ai_engineering/06_toi_uu_trien_khai.md')
    subprocess.run(['git','add','--',*staged],cwd=ROOT,check=True)
    subprocess.run(['git','-c','user.name=Codex','-c','user.email=codex@local','commit','-m','T2.6 '+stage+': measured val ablation, formulas unapproved'],cwd=ROOT,check=True)
    subprocess.run([PY,'-X','utf8','scripts/publish_card.py','--commit','HEAD','--message','T2.6 '+stage+': experimental val evidence; G0.7 open'],cwd=ROOT,check=True)


def stage_run(stage,candidates,kind,scope='full',extra=None,notes=None):
    state=read(STATE);reference=state['config'];reference['name']=stage+'_reference'
    folder,rs=measured(reference,scope);arms={'reference':(reference,folder,rs)}
    selected_cfg=reference;selected='reference';decisions=[]
    for label,changes in candidates:
        cfg={**reference,**changes,'name':stage+'_'+label};folder,new=measured(cfg,scope);arms[label]=(cfg,folder,new)
        ok,reasons=eligible(rs,new,kind,extra)
        decisions.append(label+(': eligible' if ok else ': rejected — '+', '.join(reasons))+'.')
        if ok and (selected=='reference' or target_score(new,kind)['estimate']>target_score(arms[selected][2],kind)['estimate']+1e-12):selected=label;selected_cfg=cfg
    # H1 ties choose the smallest k only among eligible >=99% recall arms.
    if stage.startswith('H01'):
        choices=[label for label in arms if label!='reference' and eligible(rs,arms[label][2],kind,extra)[0]]
        if choices:selected=min(choices,key=lambda label:arms[label][0]['k']);selected_cfg=arms[selected][0]
    report(stage,arms,'reference',kind,selected,decisions,scope,notes)
    state['config']=selected_cfg;state['completed'].append(stage);state['decisions'][stage]={'selected':selected,'reasons':decisions}
    write(STATE,state);write(ROOT/'eval/configs/Bstar.yaml',selected_cfg)
    publish(stage,'Measured '+stage+' on frozen val; selected '+selected+'.',' '.join(decisions))


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);a=p.parse_args();stage=a.stage
    if stage=='B0':
        arms={}
        for model,folder in zip(MODELS,['B0_4b_val','B0_8b_val']):
            folder=ROOT/'eval/results'/folder
            if not (folder/'summary.json').exists():raise SystemExit('Complete both B0 runs first.')
            cfg=read(folder/'summary.json')['config'];arms['4B' if model==MODELS[0] else '8B']=(cfg,folder,subset_records(rows(folder),'full'))
            write(EXPERIMENTS/('B0_'+('4b' if model==MODELS[0] else '8b')+'_full_summary.json'),read(folder/'summary.json'))
        report('H00_B0',arms,'4B','quality','4B starting reference',
               ['Both baseline models measured; defer model promotion to H4 after H2/H1/H3.'],notes=[
                   'Full B0 runs also include E3/E4/E7/E9/multi/why; complete suite results remain in each source summary.',
                   'Verifier off means enforcement off. Diagnostic verifier checks still execute for trace instrumentation and their CPU time is included. Every answer uses deterministic facts; free numeric LLM answers are prohibited in all arms.',
                   'Baseline raw trace scores were corrected without rerunning completed cases: first-response TSA/schema, exact raw VND, one-to-one batch arguments, strict authored E8 refusal and exact source-derived row-footer counts. Original metric files/timing retained; output text/prompts/golds unchanged.',
                   'B0 8B was interrupted after446 completed cases. Its exact original routing source was reconstructed and verified by hash; diagnostic-only footer changes were migrated with original source/data/model provenance preserved. Remaining cases ran in a second server session; one started-but-lost E3 case is excluded and counted as failure in the planned-denominator bound. Old continuous GPU samples were lost; resumed samples cover only the new segment. Shared machine load and server restart limit timing comparability.'])
        write(STATE,{'notice':NOTICE,'config':arms['4B'][0],'completed':['H00_B0'],'decisions':{}})
        write(ROOT/'eval/configs/Bstar.yaml',arms['4B'][0]);publish('H00_B0','Both full-val baselines measured; no held-out test accessed.','Start ablation path with4B; compare8B after architecture in H4.');return
    if stage=='H2':stage_run('H02_hints',[('on',{'hints':True})],'args');return
    if stage=='H1':
        def recall(rs):
            s=summarize(rs)['by_suite']['e1'].get('candidate_recall',{}).get('estimate')
            return [] if s is not None and s>=.99 else ['candidate recall <99%']
        stage_run('H01_retriever',[('k'+str(k),{'k':k}) for k in (66,20,12,8,5)],'tsa',extra=recall,
                  notes=['Retriever is existing BM25 with exact-phrase and capability boosts; embeddings and embedding weight sweeps are not measured. Recall is actual candidate membership; k66 recall does not measure ranked Top8.']);return
    if stage=='H3':stage_run('H03_output',[('native',{'output_mode':'native'}),('schema',{'output_mode':'schema'})],'schema',notes=['llama.cpp grammar execution not measured; native/schema share local validation and read-only execution.']);return
    if stage=='H4':
        def speed(rs):
            l=latency(rs);return [] if l['p50_ms']<=6000 and l['p95_ms']<=15000 else ['operational latency threshold exceeded']
        stage_run('H04_model_think',[(('4B' if model==MODELS[0] else '8B')+('_think' if think else '_off'),{'model':model,'think':think}) for model in MODELS for think in (False,True)],'quality','screen',speed,
                  ['Thinking flag is measured through actual thinking_chars; a model ignoring the flag is not evidence against reasoning in other models. Output token cap384 and deadline45s apply to every arm; truncation is an observed failure, not unlimited-thinking evaluation.']);return
    if stage=='H7':stage_run('H07_fewshot',[('none',{'fewshot':0}),('static3',{'fewshot':3,'fewshot_mode':'static'}),('knn3',{'fewshot':3,'fewshot_mode':'knn'}),('knn5',{'fewshot':5,'fewshot_mode':'knn'}),('knn8',{'fewshot':8,'fewshot_mode':'knn'})],'quality','screen');return
    if stage=='H8':stage_run('H08_language',[(lang,{'language':lang}) for lang in ('vi','en','bilingual')],'quality','screen');return
    if stage=='H5':stage_run('H05_answer',[('template',{'answer_mode':'template'}),('hybrid',{'answer_mode':'hybrid'})],'faith','screen',notes=['Free-form numeric LLM answers are prohibited; that proposed legacy arm is not measured. Hybrid selects symbolic slots only. CSAT/human preference not measured.']);return
    if stage=='H6':stage_run('H06_verifier',[('off',{'verifier':False}),('level1',{'verifier':True,'causal_level':1}),('level2',{'verifier':True,'causal_level':2})],'verifier','screen',notes=[
        'E6 is a deterministic replay of injected answers, not fresh LLM-generated hallucination incidence. Error recall and false-positive rates use separate denominators.',
        'Verifier off disables enforcement; diagnostic checks remain timed for logging. E6 covers seven numeric/period/caveat mutations, not a dedicated causal-claim injection set. Equal scores between causal strictness levels do not refute their usefulness on unmeasured causal attacks.']);return
    if stage=='H13':
        chosen=read(STATE)['config']['model'];is8=chosen.startswith('qwen3:8b')
        variants=[('Q4',MODELS[1]),('Q5','agent4-qwen3-8b:q5_K_M'),('Q8','qwen3:8b-q8_0')] if is8 else [('Q4',MODELS[0]),('Q5','agent4-qwen3-4b-instruct-2507:q5_K_M'),('Q8','qwen3:4b-instruct-2507-q8_0')]
        api=httpx.Client(base_url='http://127.0.0.1:11435',timeout=30);tags=api.get('/api/tags').json()['models'];provenance={'notice':NOTICE,'models':{}}
        for label,model in variants:
            shown=api.post('/api/show',json={'model':model});shown.raise_for_status();body=shown.json()
            tag=next(m for m in tags if m['name']==model)
            provenance['models'][label]={'name':model,'digest':tag['digest'],'details':body['details'],'parameters':body.get('parameters'),
                'template_sha256':hashlib.sha256(body.get('template','').encode()).hexdigest(),'capabilities':body.get('capabilities')}
        prep=ROOT/'artifacts'/('quantization_prepare_8b_llamacpp.json' if is8 else 'quantization_prepare_llamacpp.json')
        if prep.exists():provenance['historical_preparation_snapshot']=read(prep)
        write(EXPERIMENTS/'H13_quantization_provenance.json',provenance)
        stage_run('H13_quantization',[(label,{'model':model}) for label,model in variants],'quality','screen',notes=[
            'Quantization matrix holds the chosen model family constant: '+('8B' if is8 else '4B instruct')+'. Other model family quantizations are not measured.',
            'Model digests/templates/parameters and historical weight-preparation provenance are in H13_quantization_provenance.json. The preparation snapshot predates quality evaluation.',
            'Promotion still requires>=1pp quality improvement and no Must regression. Weight preparation timing is excluded from inference latency.']);return
    raise SystemExit('Unknown stage')


if __name__=='__main__':main()
