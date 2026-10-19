"""Real local VietOCR beam rereads on frozen DEV failures, no CFR/database writes.

Raw invoice observations remain in ignored app/data. Published summary contains
IDs/counts/hashes only. This measures reread candidates, not saved-field accuracy.
"""
import hashlib
import json
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path
from uuid import uuid4
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from src.adapters.ocr.protocol import NormalizedDocumentExtraction,OCRConfig,OCRBridgeRequest
from src.adapters.ocr.worker_client import WorkerClient
from src.domain.taxpayer import TaxpayerMaster
from src.extraction.contracts import ExtractionArtifact
from src.extraction.service import extract,implementation_sha
from src.recovery.regions import plan_regions,crop_box,MODEL,POLICY,implementation_sha as recovery_sha
from src.recovery.field_reads import typed_read,text_read,TYPED_PATHS

TARGETS={'charity_2023-p1':('parties.buyer.tax_id','invoice.series','parties.seller.name','parties.buyer.name'),
         'software_kct-p1':('parties.seller.tax_id','invoice.issue_date','parties.buyer.name'),
         'cyber_construction-p69':('parties.seller.name',)}


def text_key(value):return ' '.join(unicodedata.normalize('NFC',str(value)).split())


def main():
    pilot=ROOT/'data invoice/real_invoice_pilot_v1';out=APP/'data/field_coverage_round3';out.mkdir(parents=True,exist_ok=True)
    labels=json.loads((pilot/'labels.json').read_bytes());client=WorkerClient(model_id=MODEL)
    started=time.perf_counter();runtime=client.inventory()['runtime_sha256'];rows=[];private=[]
    config=OCRConfig(version=POLICY,model_id=MODEL,timeout_seconds=30,memory_mb=3072,max_attempts=1,max_output_bytes=512*1024)
    for case,paths in TARGETS.items():
        doc=NormalizedDocumentExtraction.model_validate_json((pilot/'normalized'/(case+'-scan.json')).read_bytes())
        old=ExtractionArtifact.model_validate_json((pilot/'verified_all_fields'/(case+'-scan.json')).read_bytes())
        master=TaxpayerMaster(config_version='field-coverage-dev-v1',creator='benchmark',stage='benchmark',tenant_id=doc.tenant_id,
            taxpayer_id=doc.taxpayer_id,revision=doc.taxpayer_master_revision,tax_code='0000000000',effective_from=date(1900,1,1),provenance_reference='dev-not-direction-test')
        artifact=extract(doc,'PDF',master,old.profile)
        for path in paths:
            field,regions=plan_regions(artifact.record,artifact,doc,path);requests=[]
            for index,(page,block) in enumerate(regions):
                image_path=pilot/'normalized'/case/('page-'+str(page.page_index)+'.png')
                if hashlib.sha256(image_path.read_bytes()).hexdigest()!=page.image_hash:raise ValueError('Frozen render hash mismatch')
                with Image.open(image_path) as image:
                    with image.crop(crop_box(block.evidence.bbox,*image.size)).convert('RGB') as crop:
                        target=out/(case+'-'+path.replace('.','_')+'-'+str(index)+'.png');crop.save(target);width,height=crop.size
                requests.append(OCRBridgeRequest(config_version=POLICY,creator='benchmark',stage='ocr',request_id='dev-'+uuid4().hex,
                    source_id=doc.source_id,document_id=doc.document_id,page_id=page.page_id,page_index=page.page_index,
                    image_path=str(target.resolve()),image_hash=hashlib.sha256(target.read_bytes()).hexdigest(),image_width=width,image_height=height,
                    model_config_version=config.version,runtime_sha256=runtime,model_id=MODEL,timeout_seconds=config.timeout_seconds))
            before=time.perf_counter();responses=client.run_batch(requests,config)
            texts=[r.result.document_text_raw for r in responses]
            value=typed_read(path,texts,artifact.profile) if path in TYPED_PATHS else text_read(path,texts)
            expected=labels[case]['fields'][path]
            row={'case_id':case,'field_path':path,'old_status':field['status'],'old_correct':field.get('value') is not None and text_key(field['value'])==text_key(expected),
                'candidate_parsed':bool(value),'candidate_exact':bool(value) and text_key(value)==text_key(expected),
                'candidate_casefold_exact':bool(value) and text_key(value).casefold()==text_key(expected).casefold(),
                'crop_count':len(requests),'elapsed_seconds':time.perf_counter()-before,'input_sha256':doc.input_sha256}
            rows.append(row);private.append({'result':row,'old':field,'expected':expected,'candidate':value,'responses':[r.model_dump(mode='json') for r in responses]})
            (out/'observations.private.json').write_bytes(json.dumps(private,ensure_ascii=False,indent=2).encode())
            print(json.dumps(row,ensure_ascii=True),flush=True)
    report={'scope':'Selected DEV failures; existing agent labels; candidates require human review; no database writes or holdout claim',
        'model_id':MODEL,'runtime_sha256':runtime,'extractor_sha256':implementation_sha(),'recovery_sha256':recovery_sha(),'policy':POLICY,'targets':len(rows),
        'distinct_invoice_groups':len(TARGETS),'candidate_exact':sum(r['candidate_exact'] for r in rows),
        'candidate_casefold_exact':sum(r['candidate_casefold_exact'] for r in rows),'candidate_unparsed':sum(not r['candidate_parsed'] for r in rows),
        'rows':rows,'elapsed_seconds':time.perf_counter()-started,'auto_confirmed':False,'holdout_evaluated':False}
    (out/'summary.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())


if __name__=='__main__':main()
