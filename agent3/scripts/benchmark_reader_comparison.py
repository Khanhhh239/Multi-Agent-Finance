"""One labeled difficult DEV crop, two local configs; raw values stay ignored."""
import hashlib
import json
import sys
import time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.protocol import OCRConfig,OCRBridgeRequest
from src.recovery.field_reads import text_read
from evaluate_automation_pilot import normalized


def main():
    path=(APP/'data/field_coverage_round3/software_kct-p1-parties_buyer_name-1.png').resolve()
    expected=json.loads((ROOT/'data invoice/real_invoice_pilot_v1/labels.json').read_bytes())['software_kct-p1']['fields']['parties.buyer.name']
    out=APP/'data/ocr_coverage_v1/readers';out.mkdir(parents=True,exist_ok=True);rows=[]
    with Image.open(path) as image:w,h=image.size
    for model in ('vietocr_region_v1','vietocr_region_wide'):
        client=WorkerClient(model_id=model);runtime=client.inventory()['runtime_sha256']
        config=OCRConfig(version='reader-comparison-v1',model_id=model,timeout_seconds=45,memory_mb=3072,max_attempts=1)
        request=OCRBridgeRequest(config_version=config.version,creator='benchmark',stage='ocr',request_id='reader-comparison',
            source_id='case',document_id='case',page_id='case',page_index=0,image_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
            image_path=str(path),image_width=w,image_height=h,model_config_version=config.version,runtime_sha256=runtime,
            model_id=model,timeout_seconds=config.timeout_seconds)
        started=time.perf_counter();response=client.run_batch([request],config)[0]
        (out/(model+'.private.json')).write_bytes(response.model_dump_json(indent=2).encode())
        value=text_read('parties.buyer.name',[response.result.document_text_raw])
        rows.append({'model_id':model,'runtime_sha256':runtime,'crop_sha256':request.image_hash,
            'labeled':1,'exact':int(normalized(value,'parties.buyer.name')==normalized(expected,'parties.buyer.name')),
            'elapsed_seconds':time.perf_counter()-started,'load_ms':response.result.load_time_ms,'inference_ms':response.result.inference_time_ms})
    report={'scope':'One selected difficult DEV name crop, agent labels, no database writes or holdout claim',
        'rows':rows,'promotion_approved':False,'comparison_uses_same_weights':True}
    (out.parent/'wide_comparison.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps(report))


if __name__=='__main__':main()
