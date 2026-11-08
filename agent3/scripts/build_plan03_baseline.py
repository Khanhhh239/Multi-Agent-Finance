"""Reproducible synthetic OCR comparison; never a real invoice accuracy claim."""
import json
import math
import re
import sqlite3
import statistics
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(PROJECT))
import pymupdf
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.ingestion.repository import IngestionRepository
from src.adapters.ocr.bridge import OCRBridge,request_for
from src.adapters.ocr.protocol import OCRConfig
from src.adapters.ocr.worker_client import WorkerClient,sha
from src.adapters.ocr.layout_merge import overlap

LOCAL=ROOT/'data invoice/plan03_local'
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan03'
OLD=ROOT/'data invoice/plan02_local/native_unicode_v2'


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1): nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]


def canonical(text):
    return ' '.join(unicodedata.normalize('NFC',text).split())


def quantile95(values):
    return sorted(values)[max(0,math.ceil(.95*len(values))-1)]


def main():
    LOCAL.mkdir(exist_ok=True); PUBLIC.mkdir(exist_ok=True)
    dbpath=LOCAL/'baseline.sqlite3'
    if not dbpath.exists():
        with sqlite3.connect(OLD/'baseline.sqlite3') as source,sqlite3.connect(dbpath) as target:
            source.backup(target)
    settings=Settings(database_path=dbpath,staging_directory=LOCAL/'staging')
    ctx=AccessContext(actor_id='ocr-baseline',tenant_id='synthetic-tenant',taxpayer_ids=frozenset({'synthetic-payer'}),permissions=frozenset({'ADMIN'}))
    repo=IngestionRepository(settings); repo.base.initialize()
    manifest=[json.loads(line) for line in (OLD/'baseline_manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    originals=[row for row in manifest if row['case']=='project-original']
    selected=[row for row in originals if row['source_path'].endswith('-image.png')]
    client=WorkerClient(); runtime=client.inventory()
    (PUBLIC/'adapter_runtime_matrix.json').write_text(json.dumps({'selected':runtime,
        'other_engines':{'easyocr':'NOT_EXECUTED','ppocrv6_medium':'NOT_EXECUTED',
                        'ppocrv6_vietocr':'NOT_EXECUTED','VLM':'NOT_PROBED_NO_AUTO_DOWNLOAD'},
        'hardware_budget':{'device':'CPU','worker_memory_mb':512,'concurrency':1,'process_limit':3},
        'fallback':'DISABLED'},indent=2),encoding='utf-8')
    comparison=[]
    # Same ten logical documents, same pixels, same generated reference for all configs.
    # Evaluation is development selection only, not held-out validation.
    with tempfile.TemporaryDirectory(prefix='capture-ocr-eval-') as directory:
        paths=[]; pages=[]; references=[]; annotations=[]
        for index,row in enumerate(selected):
            doc=repo.document(ctx,'synthetic-payer',row['ingestion_id']); page=doc.pages[0]
            path=Path(directory)/f'page-{index}.png';path.write_bytes(repo.render(ctx,'synthetic-payer',row['ingestion_id'],0))
            paths.append(path);pages.append(page)
            original=ROOT/row['source_path']; stem=original.stem.replace('-image','-pdf_text')
            with pymupdf.open(original.with_name(stem+'.pdf')) as reference:
                references.append(canonical(reference[0].get_text()))
            annotations.append(json.loads(original.with_suffix('.annotation.json').read_text(encoding='utf-8')))
        for psm in (3,6,11):
            config=OCRConfig(version=f'tesseract-v1-psm{psm}',psm=psm)
            requests=[request_for(page,path,config,runtime['runtime_sha256']) for page,path in zip(pages,paths)]
            started=time.perf_counter(); responses=client.run_batch(requests,config); elapsed=(time.perf_counter()-started)*1000
            records=[]; ce=we=chars=words=0; total_hits=date_hits=total_n=date_n=0
            for row,page,response,reference,annotation in zip(selected,pages,responses,references,annotations):
                result=response.result; predicted=canonical(result.document_text_raw)
                c=distance(reference,predicted);w=distance(reference.split(),predicted.split())
                ce+=c;we+=w;chars+=len(reference);words+=len(reference.split())
                diagnostics={}
                for name in ('invoice.issue_date','totals.gross'):
                    field=next((f for f in annotation['fields'] if f['field_path']==name and f['status']=='OBSERVED'),None)
                    if not field: continue
                    value=canonical(field['raw_text']);hits=[]
                    # Ground-truth region selects OCR lines. This evaluates OCR
                    # recognition with an oracle region, not field localization.
                    expected_bbox=field['evidence'][0]['bbox']
                    for det in result.detections:
                        xs,ys=zip(*det.polygon)
                        box=(min(xs)/page.render_width,min(ys)/page.render_height,max(xs)/page.render_width,max(ys)/page.render_height)
                        if overlap(box,expected_bbox)<.5: continue
                        pattern=r'\d{1,2}/\d{1,2}/\d{4}' if name=='invoice.issue_date' else r'[0-9]+(?:[.,][0-9]+)*'
                        values=re.findall(pattern,det.text_raw)
                        if values and values[-1]==value: hits.append(det.source_id)
                    diagnostics[name]={'exact_region_value':bool(hits),'reference':value}
                    if name=='invoice.issue_date': date_n+=1;date_hits+=bool(hits)
                    else: total_n+=1;total_hits+=bool(hits)
                records.append({'source_path':row['source_path'],'image_sha256':page.render_sha256,
                    'response':response.model_dump(mode='json'),'reference_sha256':sha(reference.encode()),
                    'char_edits':c,'reference_chars':len(reference),'word_edits':w,'reference_words':len(reference.split()),
                    'diagnostics':diagnostics})
            run=LOCAL/f'comparison-psm{psm}.jsonl'
            run.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
            latency=[r.result.inference_time_ms for r in responses]
            scores=[d.confidence for r in responses for d in r.result.detections if d.confidence is not None]
            comparison.append({'config':config.model_dump(mode='json'),'samples':len(responses),
                'split':'synthetic-functional-development-10','cer_micro':ce/chars,'wer_micro':we/words,
                'char_edits':ce,'reference_chars':chars,'word_edits':we,'reference_words':words,
                'date_exact_line_value':{'correct':date_hits,'eligible':date_n},
                'total_exact_line_value':{'correct':total_hits,'eligible':total_n},
                'inference_p50_ms':statistics.median(latency),'inference_p95_ms':quantile95(latency),
                'cold_first_inference_ms':latency[0], 'warm_inference_p50_ms':statistics.median(latency[1:]),
                'adapter_load_ms':responses[0].result.load_time_ms,'batch_wall_ms':elapsed,
                'peak_job_memory_mb':client.last_metrics['peak_job_memory_bytes']/1024/1024 if client.last_metrics['peak_job_memory_bytes'] is not None else None,
                'raw_score_distribution':{'semantics':'ENGINE_HEURISTIC_NOT_CALIBRATED','count':len(scores),
                    'min':min(scores) if scores else None,'median':statistics.median(scores) if scores else None,
                    'max':max(scores) if scores else None},
                'failure_rate':0,'geometry_available_rate':sum(bool(r.result.detections) for r in responses)/len(responses),
                'run_manifest':str(run.relative_to(ROOT)),'run_sha256':sha(run.read_bytes())})
    # Invoice capture prioritizes exact recognition of critical dates/totals,
    # then global text errors and latency. CER alone can hide a date regression.
    winner=min(comparison,key=lambda x:(
        -x['total_exact_line_value']['correct']/max(1,x['total_exact_line_value']['eligible']),
        -x['date_exact_line_value']['correct']/max(1,x['date_exact_line_value']['eligible']),
        x['cer_micro'],x['wer_micro'],x['config']['psm']!=3,x['inference_p50_ms']))
    config=OCRConfig.model_validate(winner['config'])
    bridge=OCRBridge(settings,config,client)
    outcomes=[]
    for row in manifest:
        if row['status']!='SUCCEEDED': continue
        outcome=bridge.work_one(ctx,'synthetic-payer',row['ingestion_id'])
        result=outcome['result']
        path=LOCAL/(row['ingestion_id']+'.extraction.json')
        if result: path.write_text(result.model_dump_json(indent=2),encoding='utf-8')
        outcomes.append({'ingestion_id':row['ingestion_id'],'case':row['case'],'status':outcome['status'],
            'pages':len(result.pages) if result else 0,'blocks':sum(len(p.blocks) for p in result.pages) if result else 0,
            'result_sha256':sha(path.read_bytes()) if result else None,
            'path':str(path.relative_to(ROOT)) if result else None})
    summary={'date':'2026-10-12','scope':'synthetic-functional-v1','runtime_sha256':runtime['runtime_sha256'],
             'comparison':comparison,'selected_config':winner['config'],'document_outcomes':outcomes,
             'ram_observed_mb':max(c['peak_job_memory_mb'] or 0 for c in comparison),'ram_budget_mb':512,'vram_observed_mb':None,'gpu_used':False,
             'limitations':['No independently reviewed Vietnamese invoices; no production quality claim.',
                'Total/date are OCR exact recognition with ground-truth regions, not CFR field extraction accuracy.',
                'All configurations share the same functional development split; no held-out selection test.',
                'RAM is Windows Job Object peak committed memory for the worker tree, not GPU or system-wide RAM.',
                'Load time is adapter Python initialization; Tesseract executable/model loads inside each inference.',
                'One engine, three segmentation modes; no cross-engine superiority claim.']}
    (PUBLIC/'baseline_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'selected_psm':config.psm,'documents':len(outcomes),'statuses':{s:sum(o['status']==s for o in outcomes) for s in ('COMPLETE','PARTIAL','FAILED')}}))


if __name__=='__main__': main()
