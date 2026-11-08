"""Hybrid integration baseline. Historical PLAN_03 Tesseract evidence is retained."""
import json
import sqlite3
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.adapters.ocr.bridge import OCRBridge,config_key
from src.adapters.ocr.registry import load_default_config
from src.adapters.ocr.worker_client import WorkerClient
from src.persistence.repository import digest

LOCAL=ROOT/'data invoice/plan03_local/model_switch'
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan03/model_switch'
OLD=ROOT/'data invoice/plan02_local/native_unicode_v2'


def main():
    LOCAL.mkdir(exist_ok=True,parents=True);PUBLIC.mkdir(exist_ok=True,parents=True)
    database=LOCAL/'baseline.sqlite3'
    if not database.exists():
        with sqlite3.connect(OLD/'baseline.sqlite3') as source,sqlite3.connect(database) as target: source.backup(target)
    settings=Settings(database_path=database,staging_directory=LOCAL/'staging')
    config=load_default_config();client=WorkerClient(model_id=config.model_id)
    bridge=OCRBridge(settings,config,client);bridge.repository.ingestion.base.initialize()
    ctx=AccessContext(actor_id='hybrid-integration-baseline',tenant_id='synthetic-tenant',
                      taxpayer_ids=frozenset({'synthetic-payer'}),permissions=frozenset({'ADMIN'}))
    rows=[json.loads(line) for line in (OLD/'baseline_manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    selected=[r for r in rows if r['status']=='SUCCEEDED' and (r['case'] in ('hybrid','rotation-90')
        or Path(r['source_path']).name in ('syn-00-image.png','syn-08-pdf_image.pdf','syn-00-pdf_text.pdf'))]
    assert len(selected)==5
    runtime=client.inventory();key=config_key(config,runtime['runtime_sha256']);outcomes=[]
    for row in selected:
        started=time.perf_counter();before=len(client.metrics_history)
        job=bridge.work_one(ctx,'synthetic-payer',row['ingestion_id']);result=job['result']
        if result is None: raise RuntimeError('OCR did not return a document artifact')
        path=LOCAL/(row['ingestion_id']+'.extraction.json');path.write_text(result.model_dump_json(indent=2),encoding='utf-8')
        outcome=dict(source_path=row['source_path'],input_sha256=row['sha256'],case=row['case'],
            ingestion_id=row['ingestion_id'],config_key=key,status=job['status'],
            pages=len(result.pages),routes=[p.route for p in result.pages],
            issues=[p.issue.model_dump(mode='json') if p.issue else None for p in result.pages],
            blocks=sum(len(p.blocks) for p in result.pages),ocr_responses=sum(len(p.raw_responses) for p in result.pages),
            wall_ms=(time.perf_counter()-started)*1000,worker_metrics=client.metrics_history[before:],
            artifact_path=str(path.relative_to(ROOT)),artifact_sha256=digest(path.read_bytes()))
        outcomes.append(outcome)
        print(json.dumps({'case':row['case'],'source':Path(row['source_path']).name,'status':job['status'],'pages':outcome['pages'],'blocks':outcome['blocks']}),flush=True)
    first=selected[0]['ingestion_id'];before=len(client.metrics_history)
    repeated=OCRBridge(settings,config,client).work_one(ctx,'synthetic-payer',first)
    assert len(client.metrics_history)==before and repeated['status']=='COMPLETE'
    summary=dict(date='2026-10-12',scope='hybrid-model-switch-functional-v1',config=config.model_dump(mode='json'),
        runtime=runtime,outcomes=outcomes,restart_cache_reused=True,automatic_fallback=False,
        limitations=['Five synthetic integration documents only; no claim of better accuracy than Tesseract.',
                    'Detector scores are not VietOCR text confidence or calibrated field probabilities.',
                    'Orientation correction inside OCR disabled; raster transforms inherited from PLAN_02.',
                    'CPU model initialization occurs for each page subprocess; persistent model serving is future hardening.'])
    (PUBLIC/'baseline_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    assert all(r['status']=='COMPLETE' for r in outcomes)
    print(json.dumps({'status':'PASS_FUNCTIONAL','documents':len(outcomes),'pages':sum(r['pages'] for r in outcomes)}))


if __name__=='__main__': main()
