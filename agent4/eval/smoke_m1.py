"""Measure exactly the first ten sample questions through the real CLI.

Development demonstration only. It never opens the held-out val/test warehouses.
Expected labels/dates are explicit; values use the independent base-table oracle.
"""
import argparse,calendar,json,math,os,statistics,subprocess,sys
from datetime import date
from pathlib import Path
from time import perf_counter
import duckdb
import httpx
from eval.oracle import oracle,Reference,BASE
from agent4.agent.constants import NOTICE

EXPECTED=[
 ('net_revenue','2026-10-01','2026-10-31',None),
 ('net_revenue','2026-10-01','2026-12-31',None),
 ('cogs','2026-04-01','2026-09-30','month'),
 ('gross_margin_pct','2026-10-01','2026-10-31',None),
 ('gross_profit','2026-10-01','2026-10-31','product_line'),
 ('expense_by_category','2026-10-01','2026-10-31','cost_category'),
 ('operating_profit','2026-01-01','2026-10-14',None),
 ('net_profit','2026-10-01','2026-10-31',None),
 ('cash_and_equivalents','2026-10-14','2026-10-14',None),
 ('net_cash_flow','2026-10-01','2026-10-31',None),
]

def check_groups(con,result,metric,start_date,end_date,group):
    """Require the entire expected breakdown, not merely correct returned rows."""
    start,end=date.fromisoformat(start_date),date.fromisoformat(end_date)
    ref=Reference(con,start,end,'mgmt',{})
    if group=='month':
        keys={f'2026-{month:02}' for month in range(4,10)}
    else:
        prefixes=('511','521','632') if group=='product_line' else ('641','642')
        condition=' OR '.join('a.account_code LIKE ?' for _ in prefixes)
        keys={row[0] for row in con.execute(
            f"SELECT DISTINCT g.{group} FROM {BASE} WHERE g.posting_date BETWEEN ? AND ? "
            f"AND ({condition}) AND NOT COALESCE(g.is_closing,FALSE) "
            "AND COALESCE(g.source_module,'') <> 'OPENING'",
            [start,ref.effective,*[p+'%' for p in prefixes]]).fetchall()}
    rows=result.get('rows',[])
    errors=[]
    if result.get('group_by')!=group: errors.append('group')
    if {row['key'] for row in rows}!=keys or len(rows)!=len(keys) or result.get('rows_total')!=len(keys):
        errors.append('group_coverage')
    for row in rows:
        if group=='month':
            y,m=map(int,row['key'].split('-'))
            gold=oracle(con,metric,date(y,m,1),date(y,m,calendar.monthrange(y,m)[1]))
        elif row['key'] is None:
            gold=(-ref.gl(('511','521','632'),extra='g.product_line IS NULL') if group=='product_line'
                  else ref.gl(('641','642'),extra='g.cost_category IS NULL'))
        else: gold=oracle(con,metric,start,end,'mgmt',{group:[row['key']]})
        if abs(row['value']-gold)>.5: errors.append('group_value:'+str(row['key']))
    return errors

def trace_observations(traces):
    steps=[step for trace in traces for step in trace['steps']]
    return {
        'llm_calls':sum(s['stage']=='llm' for s in steps),
        'validator_failed_attempts':sum(s['stage']=='validator' and not s['data'].get('ok') for s in steps),
        'commentary_rejected_attempts':sum(s['stage']=='verifier' and not s['data'].get('ok') for s in steps),
        'facts_fallback_answers':sum(s['stage']=='verifier_fallback' for s in steps),
        'llm_unavailable':sum(s['stage']=='llm_unavailable' for s in steps),
        'commentary_unavailable':sum(s['stage']=='commentary_unavailable' for s in steps),
        'facts_verification_failures':sum(s['stage']=='verifier_facts' and not s['data'].get('ok') for s in steps),
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',default='qwen3:4b-instruct-2507-q4_K_M')
    parser.add_argument('--run-id',default='m1-first')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=root/'docs/5_handoff/measurements'/args.run_id
    out.mkdir(parents=True,exist_ok=False)
    try:
        server=httpx.get('http://localhost:11434/api/version',timeout=5).json()
        tags=httpx.get('http://localhost:11434/api/tags',timeout=5).json().get('models',[])
        model_meta=next((m for m in tags if m.get('name')==args.model),{})
    except httpx.HTTPError:
        server,model_meta={},{}
    command=[sys.executable,'-X','utf8','-m','agent4.agent.cli','--model',args.model,'--samples','10','--json','--trace',str(out/'trace.jsonl')]
    start=perf_counter()
    responses=[]
    with (out/'stderr.txt').open('w',encoding='utf-8') as errors,(out/'responses.jsonl').open('w',encoding='utf-8') as saved:
        process=subprocess.Popen(command,cwd=root,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'})
        for line in process.stdout:
            saved.write(line); saved.flush()
            response=json.loads(line)
            responses.append(response)
            print(json.dumps({'question':len(responses),'behavior':response['behavior'],'tokens':response['usage'],
                              'latency_ms':response['latency_ms'],'notice':NOTICE},ensure_ascii=False),flush=True)
        returncode=process.wait()
    con=duckdb.connect(str(root/'data/cfo_warehouse.duckdb'),read_only=True)
    scored=[]
    for index,(metric,start_date,end_date,group) in enumerate(EXPECTED):
        errors=[]
        response=responses[index] if index<len(responses) else {}
        result=(response.get('blocks',{}).get('results') or [{}])[0]
        expected=oracle(con,metric,date.fromisoformat(start_date),date.fromisoformat(end_date),'mgmt')
        actual=result.get('value')
        tolerance=1e-9 if metric=='gross_margin_pct' else .5
        if response.get('behavior')!='answer': errors.append('behavior')
        valid_metrics={metric,'operating_expenses'} if index==5 else {metric}
        if result.get('metric_id') not in valid_metrics: errors.append('metric')
        if result.get('view')!='mgmt': errors.append('view')
        if result.get('period',{}).get('start_date')!=start_date or result.get('period',{}).get('end_date')!=end_date: errors.append('period')
        if actual is None or abs(actual-expected)>tolerance: errors.append('value')
        if result.get('display','__missing__') not in response.get('text',''): errors.append('display')
        if group: errors.extend(check_groups(con,result,metric,start_date,end_date,group))
        if index in (1,7):
            mode='previous_period' if index==1 else 'same_period_last_year'
            cmp_start,cmp_end=('2026-07-01','2026-07-14') if index==1 else ('2025-10-01','2025-10-14')
            gold=oracle(con,metric,date.fromisoformat(cmp_start),date.fromisoformat(cmp_end))
            cmp=result.get('comparison',{})
            call=(response.get('blocks',{}).get('calls') or [{}])[0]
            if call.get('compare_to')!=mode: errors.append('compare_mode')
            if cmp.get('value') is None or abs(cmp['value']-gold)>.5: errors.append('compare_value')
            if cmp.get('period',{}).get('start_date')!=cmp_start or cmp.get('period',{}).get('end_date')!=cmp_end: errors.append('compare_period')
            delta=expected-gold
            pct=delta/abs(gold)*100 if gold else None
            if cmp.get('delta') is None or abs(cmp['delta']-delta)>.5: errors.append('compare_delta')
            if pct is not None and (cmp.get('delta_pct') is None or abs(cmp['delta_pct']-pct)>1e-9): errors.append('compare_pct')
            if cmp.get('delta_display','__missing__') not in response.get('text',''): errors.append('compare_delta_display')
            if cmp.get('delta_pct_display','__missing__') not in response.get('text',''): errors.append('compare_pct_display')
        stages={step['stage'] for step in response.get('trace',[])}
        required={'hints','retriever','llm','validator','engine','render','verifier_facts'}
        if not required<=stages: errors.append('pipeline')
        if not any(s['stage']=='verifier_facts' and s['data'].get('ok') for s in response.get('trace',[])): errors.append('verifier')
        if NOTICE not in response.get('text','') or response.get('blocks',{}).get('G0_7')!='CHƯA ĐẠT': errors.append('G0.7_label')
        scored.append({'question':index+1,'passed':not errors,'errors':errors,'expected_value':expected,'actual_value':actual,
                       'tokens':response.get('usage',{}),'latency_ms':response.get('latency_ms'),
                       'rows_total':result.get('rows_total'),'rows_returned':len(result.get('rows',[]))})
    warehouse=dict(con.execute('SELECT key,value FROM company_info').fetchall())
    con.close()
    traces=[json.loads(line) for line in (out/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    trace_ok=len(traces)==10 and [t['request_id'] for t in traces]==[r['request_id'] for r in responses]
    latencies=[r['latency_ms'] for r in responses]
    report={'notice':NOTICE,'report_notice':'formulas not accountant-approved','G0_7':'CHƯA ĐẠT','model':args.model,'num_ctx':4096,'dataset':'first 10 reference_v0/sample-questions.md, development demo',
            'ollama':server,'model_digest':model_meta.get('digest'),'python':sys.version,
            'warehouse':{k:warehouse.get(k) for k in ('as_of_date','data_version','seed','last_closed_month')},
            'trace_records':len(traces),'trace_ids_match':trace_ok,
            'observations':trace_observations(traces),
            'command':command,'cli_exit':returncode,'questions':10,'passed':sum(r['passed'] for r in scored),'M1':returncode==0 and trace_ok and len(responses)==10 and all(r['passed'] for r in scored),
            'wall_seconds':perf_counter()-start,'latency_p50_ms':statistics.median(latencies) if latencies else None,
            'latency_p95_ms':sorted(latencies)[math.ceil(.95*len(latencies))-1] if latencies else None,
            'prompt_tokens':sum(r['usage'].get('prompt_tokens',0) for r in responses),'eval_tokens':sum(r['usage'].get('eval_tokens',0) for r in responses),
            'cases':scored,'not_measured':['large evaluation','held-out val/test','8B answer quality','pilot readiness','accountant approval'],
            'limitations':['no warmup added; cold/warm residency was not controlled, loading is included if required','tables display at most eight rows with explicit truncation','numeric membership and deterministic anchors do not establish every natural-language causal claim']}
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','command')},ensure_ascii=False),flush=True)
    raise SystemExit(0 if report['M1'] else 1)

if __name__=='__main__': main()
