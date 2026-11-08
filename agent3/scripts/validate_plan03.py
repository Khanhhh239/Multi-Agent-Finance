"""Gate validation without overwriting historical PLAN_01/02 evidence."""
from datetime import datetime,timezone
import hashlib
import json
import re
import subprocess
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'agent3_tax_compliance'
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan03'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    PUBLIC.mkdir(exist_ok=True)
    legacy={str(p.relative_to(ROOT)):sha(p) for p in (PROJECT/'data/database').glob('*.db')}
    historical={str(p.relative_to(ROOT)):sha(p) for name in ('plan01','plan02') for p in
                (ROOT/'docs/agent3/plans/evidence'/name).glob('*') if p.is_file()}
    packages={}
    for plan,lock in [('plan01','requirements-foundation.lock'),('plan02','requirements-ingestion.lock')]:
        snapshot=json.loads((ROOT/'docs/agent3/plans/evidence'/plan/'environment_snapshot.json').read_text())
        assert sha(PROJECT/lock)==snapshot['lock_sha256']
        for relative,expected in snapshot['files'].items():
            assert sha(PROJECT/'.venv/Lib/site-packages'/relative)==expected
        packages.update(snapshot['packages'])
    python=PROJECT/'.venv/Scripts/python.exe'
    tests={}
    for name in ('contracts','ingestion','ocr'):
        result=subprocess.run([str(python),'-m','unittest','discover','-s','tests/'+name,'-v'],cwd=PROJECT,capture_output=True,text=True)
        output=result.stdout+result.stderr
        (PUBLIC/(name+'_test_output.txt')).write_text(output,encoding='utf-8')
        if result.returncode: print(output);raise RuntimeError(name+' tests failed')
        tests[name]=int(re.search(r'Ran (\d+) tests',output)[1])
    directory=PROJECT/'contracts/ocr-v1'
    registry=json.loads((directory/'registry.json').read_text())
    schemas={}
    for name,expected in registry['schemas'].items():
        assert sha(directory/name)==expected
        schema=json.loads((directory/name).read_text());Draft202012Validator.check_schema(schema)
        schemas[name]=Draft202012Validator(schema)
    baseline=json.loads((PUBLIC/'baseline_summary.json').read_text())
    for name in ('request','response'):
        example=json.loads((directory/'examples'/(name+'.json')).read_text())
        schemas['ocr_bridge_'+name+'.schema.json'].validate(example)
    matrix=json.loads((PUBLIC/'adapter_runtime_matrix.json').read_text())
    runtime=matrix['selected']
    assert baseline['runtime_sha256']==runtime['runtime_sha256']
    bench=ROOT/'data invoice/ocr_e2e_workflow'
    for name,expected in runtime['files'].items(): assert sha(bench/name)==expected,name
    comparison=baseline['comparison'];same_split=None
    for config in comparison:
        path=ROOT/config['run_manifest'];assert sha(path)==config['run_sha256']
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        identities=[(r['image_sha256'],r['reference_sha256']) for r in rows]
        if same_split is None: same_split=identities
        assert identities==same_split
        assert len(rows)==config['samples']==10
        assert config['total_exact_line_value']['eligible']==9
        assert config['date_exact_line_value']['eligible']==10
        for row in rows: schemas['ocr_bridge_response.schema.json'].validate(row['response'])
        assert sum(r['char_edits'] for r in rows)==config['char_edits']
        assert sum(r['word_edits'] for r in rows)==config['word_edits']
    documents=baseline['document_outcomes'];pages=0
    assert len(documents)==38
    for row in documents:
        path=ROOT/row['path'];assert sha(path)==row['result_sha256']
        payload=json.loads(path.read_text(encoding='utf-8'))
        schemas['normalized_document_extraction.schema.json'].validate(payload)
        assert payload['status']==row['status']=='COMPLETE'
        assert payload['runtime_sha256']==runtime['runtime_sha256']
        assert payload['ocr_config']==baseline['selected_config']
        pages+=len(payload['pages'])
    assert pages==41
    assert all(sha(ROOT/name)==value for name,value in legacy.items())
    assert all(sha(ROOT/name)==value for name,value in historical.items())
    paths=list((PROJECT/'src/adapters/ocr').glob('*.py'))+list((PROJECT/'tests/ocr').glob('*.py'))
    paths += [PROJECT/'src/app.py',PROJECT/'src/ingestion/sandbox.py',PROJECT/'src/persistence/repository.py',
              PROJECT/'migrations/003_ocr.sql',bench/'src/bridge_worker.py']
    paths += list((PROJECT/'configs/ocr').glob('*.json'))
    paths += [ROOT/'scripts'/name for name in ('build_plan03_baseline.py','export_ocr_contracts.py','validate_plan03.py')]
    report=dict(schema_version='1.0.0',config_version='ocr-layout-v1',creator='validate-plan03',stage='gate-validation',
        created_at=datetime.now(timezone.utc).isoformat(),gate='PASS_TECHNICAL_FUNCTIONAL',tests=tests,total_tests=sum(tests.values()),
        schemas=len(schemas),comparison_samples_per_config=10,configurations=3,document_artifacts=38,pages=pages,
        runtime_sha256=runtime['runtime_sha256'],baseline_sha256=sha(PUBLIC/'baseline_summary.json'),
        runtime_matrix_sha256=sha(PUBLIC/'adapter_runtime_matrix.json'),
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths},
        test_output_sha256={name:sha(PUBLIC/(name+'_test_output.txt')) for name in tests},
        legacy_databases_unchanged=legacy,historical_evidence_unchanged=True,
        limitations=baseline['limitations'])
    (PUBLIC/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f"PASS technical-functional: {sum(tests.values())} tests; {len(schemas)} schemas; {len(documents)} documents / {pages} pages")


if __name__=='__main__': main()
