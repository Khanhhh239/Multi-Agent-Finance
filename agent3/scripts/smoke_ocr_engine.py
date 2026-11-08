"""Real engine smoke on a project synthetic fixture; no implicit downloads."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.registry import load_default_config
from src.adapters.ocr.protocol import OCRConfig
from src.adapters.ocr.bridge import request_for
from src.adapters.ocr.normalizer import normalize
from src.ingestion.pdf_reader import read_image
from src.config import Settings
from src.persistence.repository import digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path);args=parser.parse_args()
    config=OCRConfig.model_validate_json(args.config.read_text(encoding='utf-8')) if args.config else load_default_config()
    client=WorkerClient(model_id=config.model_id);runtime=client.inventory()
    path=ROOT/'agent3_tax_compliance/tests/fixtures/ocr/functional_set_v1/syn-00-image.png'
    with tempfile.TemporaryDirectory(prefix='capture-ocr-smoke-') as directory:
        page=read_image(path,Path(directory),dict(source_id='source-smoke',document_id='document-smoke',input_sha256=digest(path.read_bytes())),Settings())[0]
        request=request_for(page,Path(directory)/'page-0.png',config,runtime['runtime_sha256'])
        started=time.perf_counter();response=client.run_batch([request],config)[0]
        blocks=normalize(page,response)
        public=ROOT/'docs/agent3/plans/evidence/plan03/model_switch';public.mkdir(parents=True,exist_ok=True)
        local=ROOT/'data invoice/plan03_local/model_switch';local.mkdir(parents=True,exist_ok=True)
        output=local/(config.model_id+'.smoke.json');output.write_text(response.model_dump_json(indent=2),encoding='utf-8')
        report=dict(config=config.model_dump(mode='json'),runtime=runtime,page_sha256=page.render_sha256,
                    wall_ms=(time.perf_counter()-started)*1000,load_ms=response.result.load_time_ms,
                    inference_ms=response.result.inference_time_ms,metrics=client.last_metrics,blocks=len(blocks),
                    response_path=str(output.relative_to(ROOT)),response_sha256=digest(output.read_bytes()),
                    text_preview=response.result.document_text_raw[:100],status='PASS_SMOKE_ONLY')
        (public/(config.model_id+'.smoke.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('status','wall_ms','load_ms','inference_ms','metrics','blocks','text_preview')}))


if __name__=='__main__': main()
