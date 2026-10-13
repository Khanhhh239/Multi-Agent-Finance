"""Current OCR gate after switching engine; retain original PLAN_03 reports."""
from datetime import datetime,timezone
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(PROJECT))
from src.persistence.repository import digest
from src.adapters.ocr.registry import load_default_config,EngineRegistry
from src.adapters.ocr.bridge import config_key
from src.adapters.ocr.protocol import NormalizedDocumentExtraction

PUBLIC=ROOT/'docs/agent3/plans/evidence/plan03/model_switch'


def sha(path): return digest(path.read_bytes())


def main():
    baseline=json.loads((PUBLIC/'baseline_summary.json').read_text())
    assert baseline['config']==load_default_config().model_dump(mode='json')
    assert baseline['config']['model_id']=='ppocrv6_vietocr'
    before={str(p.relative_to(ROOT)):sha(p) for p in (PROJECT/'data/database').glob('*.db')}
    original=ROOT/'docs/agent3/plans/evidence/plan03'
    history={str(p.relative_to(ROOT)):sha(p) for p in original.glob('*.json')}
    tests={}
    for name in ('contracts','ingestion','ocr'):
        run=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),'-m','unittest','discover','-s','tests/'+name,'-v'],
                           cwd=PROJECT,capture_output=True,text=True)
        output=run.stdout+run.stderr
        (PUBLIC/(name+'_test_output.txt')).write_text(output,encoding='utf-8')
        if run.returncode: print(output);raise RuntimeError(name+' tests failed')
        tests[name]=int(re.search(r'Ran (\d+) tests',output)[1])
    # Keep app environment pinning checks without rewriting earlier snapshots.
    for plan in ('plan01','plan02'):
        snapshot=json.loads((ROOT/'docs/agent3/plans/evidence'/plan/'environment_snapshot.json').read_text())
        for name,expected in snapshot['files'].items(): assert sha(PROJECT/'.venv/Lib/site-packages'/name)==expected
    directory=PROJECT/'contracts/ocr-v1.1'
    registry=json.loads((directory/'registry.json').read_text());schemas={}
    for name,expected in registry['schemas'].items():
        assert sha(directory/name)==expected
        schema=json.loads((directory/name).read_text());Draft202012Validator.check_schema(schema)
        schemas[name]=Draft202012Validator(schema)
    for name in ('request','response'):
        schemas['ocr_bridge_'+name+'.schema.json'].validate(json.loads((directory/'examples'/(name+'.json')).read_text()))
    for path in (PROJECT/'configs/ocr/engines').glob('*.json'):
        schemas['engine_profile.schema.json'].validate(json.loads(path.read_text()))
    runtime=baseline['runtime'];bench=ROOT/'data invoice/ocr_e2e_workflow'
    for name,expected in runtime['files'].items(): assert sha(bench/name)==expected,name
    assert runtime['profile']==EngineRegistry().get('ppocrv6_vietocr').model_dump(mode='json')
    with sqlite3.connect(ROOT/'data invoice/plan02_local/native_unicode_v2/baseline.sqlite3') as old:
        assert old.execute('PRAGMA user_version').fetchone()[0]==2
        for row in baseline['outcomes']:
            path=ROOT/row['artifact_path'];assert sha(path)==row['artifact_sha256']
            raw=json.loads(path.read_text(encoding='utf-8'))
            schemas['normalized_document_extraction.schema.json'].validate(raw)
            model=NormalizedDocumentExtraction.model_validate(raw)
            assert model.status==row['status']=='COMPLETE'
            assert row['config_key']==config_key(model.ocr_config,model.runtime_sha256)
            assert model.ocr_config.model_id=='ppocrv6_vietocr'
            doc=old.execute('SELECT sha256 FROM documents WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                            (model.tenant_id,model.taxpayer_id,model.ingestion_id)).fetchone()
            assert model.document_artifact_sha256==doc[0]
            for page in model.pages:
                if page.route=='NATIVE_TEXT': assert not page.raw_responses
                else:
                    assert len(page.raw_responses)==1
                    response=page.raw_responses[0]
                    assert response.result.model_id=='ppocrv6_vietocr'
                    assert response.result.metadata['recognizer_backend']=='VietOCR'
                    assert response.result.metadata['paddle_backend']=='TextDetection'
                    assert response.result.metadata['recognition_errors']==0
                    assert response.result.metadata['paddle_orientation_angle']==0
                    assert response.runtime_sha256==runtime['runtime_sha256']
                    assert all(o.score_kind in ('DETECTION','UNAVAILABLE') for b in page.blocks for o in b.origins if o.method=='OCR')
    assert len(baseline['outcomes'])==5 and sum(r['pages'] for r in baseline['outcomes'])==6
    assert sum(r['ocr_responses'] for r in baseline['outcomes'])==4
    assert baseline['restart_cache_reused']
    smoke=json.loads((PUBLIC/'ppocrv6_vietocr.smoke.json').read_text())
    assert sha(ROOT/smoke['response_path'])==smoke['response_sha256'] and smoke['blocks']>0
    assert all(sha(ROOT/name)==expected for name,expected in before.items())
    assert all(sha(ROOT/name)==expected for name,expected in history.items())
    paths=list((PROJECT/'src/adapters/ocr').glob('*.py'))+list((PROJECT/'tests/ocr').glob('*.py'))
    paths+=list((PROJECT/'configs/ocr').rglob('*.json'))
    paths += [PROJECT/'src/ingestion/sandbox.py',bench/'src/bridge_worker.py']
    paths += [ROOT/'scripts'/name for name in ('smoke_ocr_engine.py','build_ocr_switch_baseline.py','validate_ocr_switch.py','export_ocr_contracts.py')]
    report=dict(date='2026-10-12',created_at=datetime.now(timezone.utc).isoformat(),
        gate='PASS_MODEL_SWITCH_TECHNICAL_FUNCTIONAL',default_engine='ppocrv6_vietocr',
        tests=tests,total_tests=sum(tests.values()),schemas=len(schemas),documents=5,pages=6,ocr_pages=4,
        baseline_sha256=sha(PUBLIC/'baseline_summary.json'),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths},
        output_sha256={name:sha(PUBLIC/(name+'_test_output.txt')) for name in tests},
        original_plan03_reports_unchanged=history,legacy_databases_unchanged=before,
        limitations=baseline['limitations'])
    (PUBLIC/'validation_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f"PASS: {sum(tests.values())} tests; {len(schemas)} schemas; hybrid {report['documents']} docs/{report['pages']} pages")


if __name__=='__main__': main()
