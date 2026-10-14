"""Offline pilot: real public PDFs, cached engine output, independent local labels.

Run with the app interpreter. --ocr invokes the configured production OCR worker
on rendered scans; derived scans are NOT counted as new real invoices.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.config import Settings
from src.domain.taxpayer import TaxpayerMaster
from src.ingestion.pdf_reader import read_pdf
from src.adapters.ocr.protocol import NormalizedDocumentExtraction,NormalizedPageExtraction
from src.adapters.ocr.layout_merge import merge
from src.adapters.ocr.registry import load_default_config
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.bridge import request_for
from src.adapters.ocr.normalizer import normalize
from src.extraction.service import extract,implementation_sha
from src.extraction.contracts import ExtractionProfile

DATA=ROOT/'data invoice/real_invoice_pilot_v1'
CASES={
    'charity_2023-p1':'dev', 'charity_2023-p2':'dev',
    'viettel_adjustment-p1':'dev', 'cyber_construction-p69':'dev',
    'software_kct-p1':'dev', 'misa_public_filing-p117':'dev',
    'cyber_construction-p118':'same_template_check',
    'misa_public_filing-p134':'same_template_check',
    'accounting_training-p2':'unverified_training_source',
}
SCAN_CASES=('charity_2023-p1','cyber_construction-p69','software_kct-p1')
STAMP=dict(config_version='public-pilot-v1',creator='public-pilot',stage='benchmark')


def load_json(path): return json.loads(path.read_text(encoding='utf-8'))


def document(case,page,blocks,config,raw=()):
    normalized=NormalizedPageExtraction(**STAMP,page_id=page.page_id,page_index=page.page_index,image_hash=page.render_sha256,
        geometry=page.geometry,route='OCR' if raw else page.route,status='COMPLETE',blocks=blocks,raw_responses=raw)
    return NormalizedDocumentExtraction(**STAMP,tenant_id='pilot',taxpayer_id='pilot',taxpayer_master_revision=1,
        ingestion_id=case,source_id=case,document_id=case,input_sha256=page.input_sha256,
        document_artifact_sha256=hashlib.sha256(page.model_dump_json().encode()).hexdigest(),
        runtime_sha256=raw[0].runtime_sha256 if raw else '0'*64,ocr_config=config,status='COMPLETE',pages=(normalized,))


def field_at(record,path):
    for part in path.split('.'): record=getattr(record,part)
    return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',required=True)
    parser.add_argument('--ocr',action='store_true');args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.phase):parser.error('phase must be a plain directory name')
    if args.phase=='before_labeled' and (DATA/args.phase).exists():
        parser.error('Historical baseline is immutable; use a new phase name.')
    out=DATA/args.phase;out.mkdir(parents=True,exist_ok=True)
    cache=DATA/'normalized';cache.mkdir(exist_ok=True)
    config=load_default_config()
    master=TaxpayerMaster(**STAMP,tenant_id='pilot',taxpayer_id='pilot',revision=1,tax_code='0000000000',
        effective_from=date(2000,1,1),provenance_reference='technical-pilot-only')
    pages={};docs={}
    for case in CASES:
        path=DATA/'cases'/(case+'.pdf');folder=cache/case;folder.mkdir(exist_ok=True)
        page=read_pdf(path,folder,dict(source_id=case,document_id=case,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),Settings())[0]
        pages[case]=page
        docs[(case,'native_only')]=document(case,page,merge(page,()),config)
    if args.ocr:
        pending=[case for case in SCAN_CASES if not (cache/(case+'-scan.json')).exists()]
        if pending:
            client=WorkerClient(model_id=config.model_id);runtime=client.inventory()['runtime_sha256']
            requests=[request_for(pages[c],cache/c/'page-0.png',config,runtime) for c in pending]
            for case,response in zip(pending,client.run_batch(requests,config)):
                page=pages[case]
                if response.issue:
                    (cache/(case+'-error.json')).write_text(response.model_dump_json(indent=2),encoding='utf-8')
                    raise RuntimeError(case+': '+response.issue.code)
                blocks=normalize(page,response)
                for mode,content in [('scan',blocks),('hybrid',merge(page,blocks))]:
                    doc=document(case,page,tuple(content),config,(response,))
                    (cache/(case+'-'+mode+'.json')).write_text(doc.model_dump_json(indent=2),encoding='utf-8')
    for case in SCAN_CASES:
        for mode in ('scan','hybrid'):
            path=cache/(case+'-'+mode+'.json')
            if path.exists():docs[(case,mode)]=NormalizedDocumentExtraction.model_validate_json(path.read_text(encoding='utf-8'))
    # A combined real-source negative case must not become a single invoice.
    import pymupdf
    combined=cache/'multi_invoice_negative.pdf'
    if not combined.exists():
        with pymupdf.open() as pdf:
            for case in ('charity_2023-p1','charity_2023-p2'):
                with pymupdf.open(DATA/'cases'/(case+'.pdf')) as part:pdf.insert_pdf(part)
            pdf.save(combined)
    negative=cache/'multi_invoice_negative';negative.mkdir(exist_ok=True)
    negative_pages=read_pdf(combined,negative,dict(source_id='multi_invoice_negative',document_id='multi_invoice_negative',
        input_sha256=hashlib.sha256(combined.read_bytes()).hexdigest()),Settings())
    combined_doc=document('multi_invoice_negative',negative_pages[0],merge(negative_pages[0],()),config)
    combined_doc=combined_doc.model_copy(update={'pages':tuple(NormalizedPageExtraction(**STAMP,
        page_id=p.page_id,page_index=p.page_index,image_hash=p.render_sha256,geometry=p.geometry,
        route=p.route,status='COMPLETE',blocks=merge(p,())) for p in negative_pages),
        'document_artifact_sha256':hashlib.sha256(json.dumps([p.model_dump(mode='json') for p in negative_pages],sort_keys=True).encode()).hexdigest()})
    docs[('multi_invoice_negative','native_only')]=combined_doc
    gold=load_json(DATA/'labels.json') if (DATA/'labels.json').exists() else {}
    rows=[]
    for (case,mode),doc in docs.items():
        a=extract(doc,'PDF',master,ExtractionProfile(number_locale='VI'))
        (out/(case+'-'+mode+'.json')).write_text(a.model_dump_json(indent=2),encoding='utf-8')
        if case=='multi_invoice_negative':assert a.segmentation.status=='REVIEW_SPLIT' and a.record is None
        row=dict(case=case,split=CASES.get(case,'negative_multidocument'),mode=mode,segmentation=a.segmentation.status,
            items=len(a.record.items) if a.record else None,fields={})
        for path,expected in gold.get(case,{}).get('fields',{}).items():
            f=field_at(a.record,path) if a.record else None
            value=f.model_dump(mode='json')['value'] if f else None
            status=f.status if f else 'NO_RECORD'
            row['fields'][path]=dict(expected=expected,value=value,status=status,
                outcome='CORRECT' if status=='PRESENT' and value==expected else 'WRONG' if status=='PRESENT' else status)
        rows.append(row)
        print(json.dumps({k:v for k,v in row.items() if k!='fields'}),flush=True)
    summary=dict(phase=args.phase,extractor_sha256=implementation_sha(),number_locale='VI',
        label_status='agent_visual_transcription_not_human_adjudicated',rows=rows)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
