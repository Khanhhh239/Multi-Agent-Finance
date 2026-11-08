"""Reproducible DEV ablation; private rasters/raw responses stay under app/data."""
import argparse
import hashlib
import json
import sys
import time
import traceback
import unicodedata
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from src.config import Settings
from src.ingestion.pdf_reader import read_pdf
from src.adapters.ocr.bridge import request_for
from src.adapters.ocr.protocol import OCRConfig,OCRBridgeResponse
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.normalizer import normalize
from src.extraction.service import extract,implementation_sha
from src.extraction.contracts import ExtractionProfile
from src.domain.taxpayer import TaxpayerMaster
from src.quality.completeness import flatten
from benchmark_public_invoices import document
from evaluate_automation_pilot import normalized

CASES=('charity_2023-p1','software_kct-p1','cyber_construction-p69')
MATRIX=(('base150','ppocrv6_vietocr',150),('base200','ppocrv6_vietocr',200),
    ('base300','ppocrv6_vietocr',300),('beam200','ppocrv6_vietocr_beam',200),
    ('tiles200','ppocrv6_vietocr_tiles',200),('deskew200','ppocrv6_vietocr_deskew',200),
    ('pprec200','ppocrv6_medium',200))


def score(record,gold):
    fields=flatten(record) if record else {};rows=[]
    for path,want in gold['fields'].items():
        if want is None:continue
        field=fields.get(path);present=bool(field and field.status=='PRESENT' and field.value is not None)
        exact=present and normalized(field.value,path)==normalized(want,path)
        rows.append({'field_path':path,'correct':bool(exact),'present':present,'wrong_present':present and not exact})
    return {'labeled':len(rows),'correct':sum(r['correct'] for r in rows),
        'wrong_present':sum(r['wrong_present'] for r in rows),'missing_or_ambiguous':sum(not r['present'] for r in rows),
        'fields':rows,'item_count_correct':bool(record) and len(record.items)==gold.get('item_count')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--variant',action='append');parser.add_argument('--case',action='append',choices=CASES)
    parser.add_argument('--timeout',type=int,default=240,choices=range(30,601))
    parser.add_argument('--summarize-only',action='store_true');args=parser.parse_args()
    pilot=ROOT/'data invoice/real_invoice_pilot_v1';out=APP/'data/ocr_coverage_v1';out.mkdir(parents=True,exist_ok=True)
    labels=json.loads((pilot/'labels.json').read_bytes());rows=[]
    for variant,model,dpi in MATRIX:
        if args.summarize_only:break
        if args.variant and variant not in args.variant:continue
        client=WorkerClient(model_id=model);runtime=client.inventory()['runtime_sha256']
        config=OCRConfig(version='coverage-ablation-v1',model_id=model,timeout_seconds=args.timeout,memory_mb=6144,max_attempts=1)
        for case in CASES:
            if args.case and case not in args.case:continue
            folder=out/variant/case;folder.mkdir(parents=True,exist_ok=True)
            source=pilot/'cases'/(case+'.pdf');source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            page=read_pdf(source,folder,dict(source_id=case,document_id=case,input_sha256=source_hash),
                Settings(render_dpi=dpi,max_render_pixels=12_000_000))[0]
            binding=hashlib.sha256((runtime+page.render_sha256+config.model_dump_json()).encode()).hexdigest()
            cache=folder/(binding+'.private.json');started=time.perf_counter();cache_hit=cache.exists()
            try:
                if cache_hit:response=OCRBridgeResponse.model_validate_json(cache.read_bytes())
                else:
                    response=client.run_batch([request_for(page,folder/'page-0.png',config,runtime)],config)[0]
                    cache.write_bytes(response.model_dump_json(indent=2).encode())
                blocks=tuple(normalize(page,response));doc=document(case,page,blocks,config,(response,))
                master=TaxpayerMaster(config_version='coverage-benchmark',creator='benchmark',stage='benchmark',tenant_id=doc.tenant_id,
                    taxpayer_id=doc.taxpayer_id,revision=1,tax_code='0000000000',effective_from=date(1900,1,1),provenance_reference='DEV-only')
                artifact=extract(doc,'PDF',master,ExtractionProfile(number_locale='VI'))
                (folder/'extraction.private.json').write_bytes(artifact.model_dump_json(indent=2).encode())
                metric=score(artifact.record,labels[case])
                row=dict(variant=variant,model_id=model,dpi=dpi,case_id=case,input_sha256=source_hash,render_sha256=page.render_sha256,
                    runtime_sha256=runtime,extractor_sha256=implementation_sha(),cache_hit=cache_hit,
                    load_ms=response.result.load_time_ms,inference_ms=response.result.inference_time_ms,
                    block_count=len(blocks),coverage=response.result.metadata.get('coverage_detection'),
                    deskew=response.result.metadata.get('coverage_geometry'),status='COMPLETE',**metric)
            except Exception as exc:
                (folder/'failure.private.txt').write_bytes(traceback.format_exc().encode())
                row=dict(variant=variant,model_id=model,dpi=dpi,case_id=case,status='FAILED',error_type=type(exc).__name__,
                    error_code=getattr(getattr(exc,'issue',None),'code',None),timeout_seconds=args.timeout)
            row['elapsed_seconds']=time.perf_counter()-started;rows.append(row)
            (folder/'metrics.json').write_bytes((json.dumps(row,ensure_ascii=False,indent=2)+'\n').encode())
            print(json.dumps({k:v for k,v in row.items() if k not in ('fields','deskew')},ensure_ascii=True),flush=True)
    # Merge separately invoked/resumed variants, excluding previous raw values.
    combined=[json.loads(p.read_bytes()) for p in sorted(out.glob('*/*/metrics.json'))]
    summary={'scope':'3 previously used DEV invoice groups; correlated DPI variants; no holdout/autoaccept claim',
        'cold_warm':'Fresh subprocess/model load per cache miss; load_ms and inference_ms reported separately; cached elapsed is not a latency sample',
        'rows':combined,'input_group_count':len({r['case_id'] for r in combined}),'planned_input_groups':len(CASES),
        'all_expected_complete':len(combined)==len(MATRIX)*len(CASES) and all(r['status']=='COMPLETE' for r in combined)}
    (out/'summary.json').write_bytes((json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode())


if __name__=='__main__':main()
