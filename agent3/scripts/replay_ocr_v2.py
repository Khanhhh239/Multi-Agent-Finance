"""Replay frozen V2 normalized inputs with current extraction; never rerun OCR."""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'data invoice/ocr_extraction_v2'
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.domain.taxpayer import TaxpayerMaster
from src.extraction.service import extract,implementation_sha
from src.extraction.contracts import ExtractionProfile


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def field(record,path):
    for part in path.split('.'):
        record=record.get(part) if record else None
    return record


def score(value,expected):
    if not value:return 'NO_RECORD'
    if value['status']!='PRESENT':return value['status']
    return 'CORRECT' if unicodedata.normalize('NFC',str(value['value']))==unicodedata.normalize('NFC',expected) else 'WRONG_PRESENT'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input-run',required=True)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if not all(re.fullmatch(r'[a-zA-Z0-9_-]+',v) for v in (args.input_run,args.run_id)):
        parser.error('plain run names required')
    source=LOCAL/args.input_run;out=LOCAL/args.run_id
    inputs=sorted(source.glob('*/*.normalized.json'))
    if not inputs:parser.error('No frozen normalized inputs')
    if out.exists():parser.error('Frozen replay exists')
    out.mkdir(parents=True)
    labels=read(ROOT/'data invoice/real_invoice_pilot_v1/labels.json')
    rows=[];changes=[]
    for path in inputs:
        doc=NormalizedDocumentExtraction.model_validate_json(path.read_text(encoding='utf-8'))
        case=path.parent.name;mode=path.name.split('.')[0]
        master=TaxpayerMaster(config_version='v2-replay',creator='v2-replay',stage='benchmark',
            tenant_id=doc.tenant_id,taxpayer_id=doc.taxpayer_id,revision=doc.taxpayer_master_revision,
            tax_code='0000000000',effective_from=date(2000,1,1),provenance_reference='technical-only')
        artifact=extract(doc,'PDF',master,ExtractionProfile(number_locale='VI'))
        (out/(case+'-'+mode+'.json')).write_text(artifact.model_dump_json(indent=2),encoding='utf-8')
        before=read(path.with_name(mode+'.extraction.json'))['record']
        after=artifact.model_dump(mode='json')['record'];counts=Counter()
        for name,expected in labels[case]['fields'].items():
            old=score(field(before,name),expected);new=score(field(after,name),expected)
            counts[new]+=1
            if old!=new:changes.append(dict(case=case,mode=mode,field=name,before=old,after=new))
        rows.append(dict(case=case,mode=mode,counts=dict(counts),input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    summary=dict(parent_plan='PLAN_06',input_run=args.input_run,run_id=args.run_id,
        extractor_sha256=implementation_sha(),label_status='SELF_CHECK_NOT_INDEPENDENT',rows=rows,changes=changes)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':main()
