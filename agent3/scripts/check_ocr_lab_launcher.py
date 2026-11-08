"""Isolated profile/HTTP startup smoke; never starts models or user queues."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from fastapi.testclient import TestClient
from src.local_web import configure,provision
from src.app import create_app
from src.adapters.ocr.registry import load_default_config


def main():
    out=APP/'data/ocr_coverage_v1/lab_smoke';out.mkdir(parents=True,exist_ok=True)
    with patch.dict(os.environ,{'CAPTURE_RENDER_DPI':'200','AGENT3_OCR_PROFILE':'ppocrv6_vietocr_coverage'}):
        settings,ctx=configure('ocr-lab-synthetic-smoke-'+'a'*40,out/'capture.sqlite3');provision(settings,ctx)
        with TestClient(create_app(settings)) as client:
            response=client.get('/review');assert response.status_code==200
            assert settings.render_dpi==200 and load_default_config().model_id=='ppocrv6_vietocr_coverage'
            assert settings.database_path.resolve()==(out/'capture.sqlite3').resolve()
    report={'result':'PASS','checks':['Enhanced profile resolves from trusted local configuration',
        '200 DPI settings reach the application','Separate lab database is provisioned without touching the normal review database',
        'Review HTML serves successfully'],'model_inference_run':False,'scope':'In-process HTTP/profile startup smoke; not an OCR accuracy test'}
    (out/'result.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps(report))


if __name__=='__main__':main()
