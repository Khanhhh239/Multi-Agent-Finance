"""Audited recovery of the interrupted B0 VAL run; never accepts TEST."""
import argparse,copy,hashlib,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from eval.run import routing_hash,source_hash,split_hashes
from eval.gate import digest
from eval.runtime_events import events
from eval.scorers import score_case
from agent4.engine.engine import ExecutionEngine


def reconstructed_routing_hash(root,git_sha):
    h=hashlib.sha256()
    for path in sorted((root/'agent4').rglob('*.py')):
        name=path.relative_to(root).as_posix();h.update(name.encode())
        content=subprocess.check_output(['git','show',git_sha+':'+name],cwd=root) if name in ('agent4/agent/render.py','agent4/agent/verifier.py') else path.read_bytes()
        h.update(content)
    h.update((root/'agent4/agent/data/fewshot_train.jsonl').read_bytes())
    return h.hexdigest()


def require_recoverable(meta,reconstructed,current_data):
    if meta['split']!='val':raise ValueError('Recovery is VAL only; TEST contract is immutable.')
    cfg=meta['config']
    if cfg['verifier'] or cfg['answer_mode']!='template':raise ValueError('Only diagnostic-only baseline changes are recoverable.')
    if reconstructed!=meta['routing_hash']:raise ValueError('Original routing source cannot be reconstructed exactly.')
    if current_data!=meta['data_hashes']:raise ValueError('Frozen val data changed.')


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('dest',type=Path);a=p.parse_args()
    source=a.source.resolve();dest=a.dest.resolve()
    if dest.exists():raise SystemExit('Destination exists; preserve evidence.')
    if (source/'summary.json').exists():raise SystemExit('This helper is only for an interrupted partial baseline.')
    meta=json.loads((source/'metadata.json').read_text(encoding='utf8'))
    require_recoverable(meta,reconstructed_routing_hash(ROOT,meta['git_sha']),split_hashes([k for k in meta['data_hashes'] if not k.startswith('_')],'val'))
    rs=[json.loads(l) for l in (source/'results.jsonl').read_text(encoding='utf8').splitlines()]
    # Only the already completed simple-answer suites are migrated. Stateful,
    # adversarial and final-test recovery require their own immutable contract.
    if any(r['status']!='completed' or r['suite'] not in ('e1','e2','e3','e4','e5') for r in rs):raise SystemExit('Unsupported partial segment; do not silently migrate it.')
    cases={r['id']:r for suite in ('e1','e2','e3','e4','e5') for l in (ROOT/'eval/data'/f'{suite}.val.jsonl').read_text(encoding='utf8').splitlines() if (r:=json.loads(l))}
    with ExecutionEngine(ROOT/'data/val.duckdb') as engine:
        for row in rs:
            row['metrics_before_layer_correction']=copy.deepcopy(row['metrics'])
            row['metrics']=score_case(row['detail']['reply'],cases[row['id']],engine)
            row['measured_source_hash']=meta['source_hash']
    prior=meta.get('server_log_audit',{})
    recovery={'notice':'formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).',
        'utc':datetime.now(timezone.utc).isoformat(),'original_run':str(source.relative_to(ROOT)),
        'original_metadata_sha256':digest(source/'metadata.json'),'original_results_sha256':digest(source/'results.jsonl'),
        'original_source_hash':meta['source_hash'],'original_routing_hash':meta['routing_hash'],'completed_cases_reused':len(rs),
        'original_metadata':copy.deepcopy(meta),'previous_server_runtime_events':events(prior.get('path'),prior.get('start_byte',0)),
        'note':'Exact original agent source reconstructed from Git for the two diagnostic footer files; all other agent bytes and TRAIN bank match original routing hash. No prompts, golds, engine values, sampling or model output changed. Existing rows rescored CPU-only. Completed IDs are not rerun; started-but-lost ID becomes interrupted_not_repeated. Old GPU sampler was lost on process termination; new samples cover resumed segment only. Source hashes are segmented, never represented as a single uninterrupted measurement.'}
    meta.update({'recovery':recovery,'source_hash':source_hash(),'routing_hash':routing_hash(),
                 'scorer_correction':{'scoring_source_hash':source_hash(),'model_rerun':False,'original_run':str(source.relative_to(ROOT))}})
    meta.pop('server_log_audit',None)  # The resumed runner records its NEW server segment.
    dest.mkdir(parents=True)
    (dest/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
    (dest/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf8')
    shutil.copy2(source/'started.jsonl',dest/'started.jsonl')
    print(json.dumps({'reused':len(rs),'destination':str(dest),'original_preserved':str(source)}))


if __name__=='__main__':main()
