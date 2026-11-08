import hashlib
import json
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.adapters.ocr import protocol
from src.adapters.ocr.registry import EngineProfile,load_default_config


def main():
    destination=ROOT/'agent3_tax_compliance/contracts/ocr-v1.1'
    destination.mkdir(parents=True,exist_ok=True)
    registry={}
    for name in ('OCRConfig','OCRBridgeRequest','OCRBridgeResponse','OCRIssue','BenchmarkResult','Detection',
                 'BlockOrigin','ExtractionBlock','NormalizedPageExtraction','NormalizedDocumentExtraction','OCRJobView'):
        model=getattr(protocol,name)
        filename=re.sub(r'(?<!^)(?=[A-Z][a-z])','_',name).lower()+'.schema.json'
        raw=(json.dumps(model.model_json_schema(mode='serialization'),indent=2)+'\n').encode()
        (destination/filename).write_bytes(raw)
        registry[filename]=hashlib.sha256(raw).hexdigest()
    (destination/'registry.json').write_text(json.dumps({'version':'ocr-v1','schemas':registry},indent=2)+'\n',encoding='utf-8')
    raw=(json.dumps(EngineProfile.model_json_schema(mode='serialization'),indent=2)+'\n').encode()
    (destination/'engine_profile.schema.json').write_bytes(raw)
    registry['engine_profile.schema.json']=hashlib.sha256(raw).hexdigest()
    (destination/'registry.json').write_text(json.dumps({'version':'ocr-v1.1','schemas':registry},indent=2)+'\n',encoding='utf-8')
    examples=destination/'examples';examples.mkdir(exist_ok=True)
    stamp=dict(config_version='ocr-layout-v1',creator='synthetic-fixture',stage='ocr',created_at='2026-10-12T00:00:00Z')
    config=load_default_config()
    identity=dict(request_id='request-example',source_id='source-example',document_id='document-example',page_id='page-example',
                  page_index=0,image_hash='a'*64,model_config_version=config.version,runtime_sha256='b'*64)
    request=protocol.OCRBridgeRequest(**stamp,**identity,image_path='page.png',image_width=100,image_height=100,timeout_seconds=config.timeout_seconds,model_id=config.model_id)
    response=protocol.OCRBridgeResponse(**stamp,**identity,engine_versions={'engine':'synthetic-example'},
        result=protocol.BenchmarkResult(schema_version='1.1',run_id=identity['request_id'],model_id=config.model_id,
            output_mode='boxes_and_text',image_id='page.png',image_width=100,image_height=100,
            load_time_ms=0,inference_time_ms=1,document_text_raw='SYNTHETIC',detections=(
                protocol.Detection(polygon=((5,5),(90,5),(90,20),(5,20)),text_raw='SYNTHETIC',confidence=.8),)))
    for name,value in [('request',request),('response',response)]:
        (examples/(name+'.json')).write_text(value.model_dump_json(indent=2)+'\n',encoding='utf-8')
    print(f'Exported {len(registry)} OCR contracts')


if __name__=='__main__': main()
