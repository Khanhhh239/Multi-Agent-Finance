"""One-time scorer correction from unchanged raw traces; no model requests."""
import argparse,copy,json,shutil,sys,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent4.engine.engine import ExecutionEngine
from eval.scorers import score_case,score_verifier_fixture
from agent4.agent.pipeline import PipelineConfig
from eval.report import summarize,markdown
from eval.run import source_hash,routing_hash
from eval.runtime_events import latest_log,events


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('dest',type=Path);a=p.parse_args()
    a.source=a.source.resolve();a.dest=a.dest.resolve()
    if a.dest.exists():raise SystemExit('Destination already exists; preserve the original and corrected scores.')
    old=json.loads((a.source/'summary.json').read_text(encoding='utf8'))
    changed=subprocess.check_output(['git','diff','--name-only',old['git_sha'],'--','agent4'],cwd=ROOT,text=True).splitlines()
    if set(changed)-{'agent4/agent/render.py','agent4/agent/verifier.py'}:raise SystemExit('Routing/engine code changed; cannot attribute a scorer-only replay.')
    if old['config']['verifier'] or old['config']['answer_mode']!='template':raise SystemExit('This correction applies only to enforcement-off template baselines.')
    if old['split']!='val':raise SystemExit('Only pre-final val layer correction authorized here.')
    rs=[json.loads(l) for l in (a.source/'results.jsonl').read_text(encoding='utf8').splitlines()]
    cases={r['id']:r for f in (ROOT/'eval/data').glob('*.val.jsonl') for line in f.read_text(encoding='utf8').splitlines() if (r:=json.loads(line))}
    with ExecutionEngine(ROOT/'data/val.duckdb') as engine:
        for row in rs:
            if row['status']!='completed':continue
            case=cases[row['id']];detail=row.get('detail',{});row['metrics_before_layer_correction']=copy.deepcopy(row['metrics'])
            if 'reply' in detail:
                corrected=score_case(detail['reply'],case,engine)
                row['metrics']=corrected
            elif row['suite']=='e6':row['metrics'],row['detail']=score_verifier_fixture(case,PipelineConfig(**old['config']))
            elif row['suite']=='e7':
                for turn,gold in zip(detail['turns'],case['turns']):turn['metrics']=score_case(turn['reply'],{**gold,'expected_behavior':'answer'},engine)
                row['metrics']['task_success']=float(all(t['metrics'].get('e2e_correct')==1 for t in detail['turns']))
                row['metrics']['unauthorized_action']=max(t['metrics']['unauthorized_action'] for t in detail['turns'])
                faithful=[t['metrics']['numeric_faithfulness'] for t in detail['turns'] if 'numeric_faithfulness' in t['metrics']]
                if faithful:row['metrics']['numeric_faithfulness']=min(faithful)
    summary=summarize([r for r in rs if r['status']=='completed'])
    for key,value in old.items():
        if key not in ('metrics','by_suite','by_noise','by_difficulty','by_metric','n','ci_note','planned_denominator_lower_bounds'):summary[key]=value
    summary['planned_denominator_lower_bounds']={}
    for name,value in old['planned_denominator_lower_bounds'].items():
        suite,key=name.split('.',1);n=value['n_planned']
        summary['planned_denominator_lower_bounds'][name]={**value,'estimate':sum(r['metrics'].get(key,0) for r in rs if r['suite']==suite and r['status']=='completed')/n}
    summary['scorer_correction']={'notice':'formulas not accountant-approved','original_run':str(a.source.relative_to(ROOT)),
        'scoring_source_hash':source_hash(),'model_rerun':False,'rule':'First-proposal TSA/schema; exact raw VND; strict E8 refusal; one-to-one arguments; renderer footer counts checked as exact source-derived metadata. Baselines had verifier enforcement OFF and template answers, so the footer-context correction changes diagnostics only, not output text, routing, engine data, labels or prompts.'}
    summary['scorer_correction']['previous_correction']=old.get('scorer_correction')
    summary['measured_routing_hash']=old.get('measured_routing_hash',old.get('routing_hash'))
    summary['scoring_contract']='First-response TSA/schema; final normalized args; exact raw VND oracle, ratios1e-9; source/display faithfulness separately.'
    summary['routing_hash']=routing_hash()
    summary['llm_sampling']={'temperature':0,'top_k':20,'top_p':.8,'seed':old['seed'],'confirmation':'Original dedicated-server log shows temp0.000; no sampling change during rescoring.'}
    if old.get('server_runtime_events'):
        prior=old['server_runtime_events']
        summary['server_runtime_events']=events(prior.get('log'),prior.get('start_byte',0),prior.get('end_byte'))
    else:
        summary['server_runtime_events']=events(latest_log(ROOT/'artifacts'))
        summary['server_runtime_events']['note']='Whole dedicated-server log contains only B0 4B since its restart; captured before8B starts. Counts are events, not distinct questions.'
    a.dest.mkdir(parents=True)
    (a.dest/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf8')
    (a.dest/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    (a.dest/'report.md').write_text(markdown(summary),encoding='utf8')
    for filename in ('metadata.json','gpu.json','started.jsonl'):shutil.copy2(a.source/filename,a.dest/filename)
    print(json.dumps(summary['scorer_correction']))


if __name__=='__main__':main()
