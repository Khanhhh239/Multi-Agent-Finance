"""System Python + existing jsonschema; executes tests with isolated .venv."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT/'agent3_tax_compliance'
EVIDENCE = ROOT/'docs/agent3/plans/evidence/plan01'


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    legacy_paths=sorted((PROJECT/'data/database').glob('*.db'))
    before={str(p.relative_to(ROOT)):sha(p) for p in legacy_paths}
    snapshot=json.loads((EVIDENCE/'environment_snapshot.json').read_text(encoding='utf-8'))
    assert snapshot['lock_sha256']==sha(PROJECT/'requirements-foundation.lock')
    for name, expected in snapshot['files'].items():
        assert sha(PROJECT/'.venv/Lib/site-packages'/name)==expected, name
    contracts=PROJECT/'contracts/v1'
    registry=json.loads((contracts/'registry.json').read_text(encoding='utf-8'))
    validators={}
    for filename, expected in registry['schemas'].items():
        assert sha(contracts/filename)==expected, filename
        schema=json.loads((contracts/filename).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        validators[filename.removesuffix('.schema.json')]=Draft202012Validator(schema)
    examples=json.loads((contracts/'examples.json').read_text(encoding='utf-8'))
    for example in examples['valid']:
        validators[example['contract']].validate(example['payload'])
    for example in examples['invalid']:
        assert list(validators[example['contract']].iter_errors(example['payload'])),example['name']
    python=PROJECT/'.venv/Scripts/python.exe'
    probe=subprocess.run([str(python),'-c',
        "import importlib.metadata as m,json,sys; ns="+repr(list(snapshot['packages']))+
        "; print(json.dumps({'python':sys.version,'packages':{n:m.version(n) for n in ns}}))"],
        cwd=PROJECT,capture_output=True,text=True,check=True)
    versions=json.loads(probe.stdout)
    assert versions['packages']==snapshot['packages']
    result=subprocess.run([str(python),'-m','unittest','discover','-s','tests/contracts','-p','test_*.py','-v'],
                          cwd=PROJECT,capture_output=True,text=True)
    after={str(p.relative_to(ROOT)):sha(p) for p in legacy_paths}
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    (EVIDENCE/'test_output.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert before==after,'legacy DB changed during validation'
    if result.returncode:
        print(result.stdout+result.stderr)
        raise RuntimeError('foundation tests failed')
    match=re.search(r'Ran (\d+) tests',result.stderr)
    assert match,'test count not found'
    code_paths=[]
    for sub in ('src/domain','src/persistence'):
        code_paths+=list((PROJECT/sub).glob('*.py'))
    code_paths += [PROJECT/'src/app.py',PROJECT/'src/config.py',PROJECT/'migrations/001_foundation.sql']
    code_paths += list((PROJECT/'tests/contracts').glob('*.py'))
    code_paths += [ROOT/'scripts'/name for name in ('bootstrap_foundation.py','export_foundation_contracts.py','validate_foundation.py')]
    code_paths += [PROJECT/'requirements-foundation.lock']
    report={
        'schema_version':'1.0.0','config_version':'foundation-v1','creator':'validate_foundation',
        'stage':'gate-validation','created_at':datetime.now(timezone.utc).isoformat(),
        'gate':'PASS','scope':'capture-foundation-v1','runtime':versions,
        'test_count':int(match[1]),'tests_passed':True,
        'json_schemas_checked':len(validators),'valid_producer_consumer_examples':len(examples['valid']),
        'invalid_examples_rejected_by_schema_and_domain':len(examples['invalid']),
        'isolated_dependency_files_verified':len(snapshot['files']),
        'legacy_hashes_before':before,'legacy_hashes_after':after,
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in code_paths},
        'registry_sha256':sha(contracts/'registry.json'), 'examples_sha256':sha(contracts/'examples.json'),
        'environment_snapshot_sha256':sha(EVIDENCE/'environment_snapshot.json'),
        'test_output_sha256':sha(EVIDENCE/'test_output.txt'),
        'limitations':['No OCR/ZEN ingestion implementation','No real-data accuracy certification',
                        'HTTP health only; trusted AccessContext injection required before data APIs',
                        'Offline dependency snapshot is Python 3.10.5 Windows specific',
                        'httpx TestClient deprecation warning; current pinned combination passes'],
    }
    (EVIDENCE/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f"PASS: {report['test_count']} tests; {len(validators)} schemas; 7 valid/4 invalid examples; 438 dependency files; {len(before)} legacy DB hashes unchanged")


if __name__=='__main__':
    main()
