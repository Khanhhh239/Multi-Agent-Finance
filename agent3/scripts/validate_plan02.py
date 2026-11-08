"""Validate ingestion + foundation regression without changing PLAN_01 history."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'agent3_tax_compliance'
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan02'


def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''): result.update(chunk)
    return result.hexdigest()


def main():
    python=PROJECT/'.venv/Scripts/python.exe'
    legacy={str(p.relative_to(ROOT)):sha(p) for p in (PROJECT/'data/database').glob('*.db')}
    snapshots=[]
    packages={}
    for plan,lock in [('plan01','requirements-foundation.lock'),('plan02','requirements-ingestion.lock')]:
        path=ROOT/'docs/agent3/plans/evidence'/plan/'environment_snapshot.json'
        snapshot=json.loads(path.read_text(encoding='utf-8'))
        assert snapshot['lock_sha256']==sha(PROJECT/lock)
        for relative,expected in snapshot['files'].items():
            assert sha(PROJECT/'.venv/Lib/site-packages'/relative)==expected,relative
        packages.update(snapshot['packages']); snapshots.append(sha(path))
    probe=subprocess.run([str(python),'-c',"import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in "+repr(list(packages))+"}))"],
                         cwd=PROJECT,capture_output=True,text=True,check=True)
    assert json.loads(probe.stdout)==packages
    results={}
    for folder in ('contracts','ingestion'):
        result=subprocess.run([str(python),'-m','unittest','discover','-s','tests/'+folder,'-p','test_*.py','-v'],
                              cwd=PROJECT,capture_output=True,text=True)
        output=result.stdout+result.stderr
        (PUBLIC/(folder+'_test_output.txt')).write_text(output,encoding='utf-8')
        if result.returncode:
            print(output); raise RuntimeError(folder+' tests failed')
        results[folder]=int(re.search(r'Ran (\d+) tests',output)[1])
    validators={}
    for path in (PROJECT/'contracts/ingestion-v1').glob('*.schema.json'):
        schema=json.loads(path.read_text(encoding='utf-8')); Draft202012Validator.check_schema(schema)
        validators[path.name]=Draft202012Validator(schema)
    registry=json.loads((PROJECT/'contracts/ingestion-v1/registry.json').read_text())
    for name,value in registry['schemas'].items(): assert sha(PROJECT/'contracts/ingestion-v1'/name)==value
    baseline=json.loads((PUBLIC/'baseline_summary.json').read_text())
    manifest=ROOT/'data invoice/plan02_local/native_unicode_v2/baseline_manifest.jsonl'
    assert sha(manifest)==baseline['manifest_sha256']
    schema_checked=0
    for line in manifest.read_text(encoding='utf-8').splitlines():
        row=json.loads(line); assert sha(ROOT/row['source_path'])==row['sha256']
        if row['status']=='SUCCEEDED':
            path=ROOT/row['document_manifest']; assert sha(path)==row['document_sha256']
            payload=json.loads(path.read_text(encoding='utf-8'))
            validators['document_artifact.schema.json'].validate(payload); schema_checked+=1
        else:
            validators['ingestion_issue.schema.json'].validate(row['issue'])
    assert baseline['original_source_count']==30 and baseline['extra_source_count']==11
    assert not baseline['unexpected_failures']
    # Semantic routing regression: every original native PDF must avoid unnecessary OCR.
    assert all(r['expected']==r['actual'] for r in baseline['route_confusion'])
    assert legacy=={str(p.relative_to(ROOT)):sha(p) for p in (PROJECT/'data/database').glob('*.db')}
    paths=list((PROJECT/'src/ingestion').glob('*.py'))
    paths += [PROJECT/'src/config.py',PROJECT/'src/app.py',PROJECT/'src/persistence/repository.py']
    paths += list((PROJECT/'tests/ingestion').glob('*.py'))+list((PROJECT/'migrations').glob('*.sql'))
    paths += [ROOT/'scripts'/p for p in ('bootstrap_ingestion.py','build_plan02_baseline.py','export_ingestion_contracts.py','validate_plan02.py')]
    report=dict(schema_version='1.0.0',config_version='ingestion-v1',creator='validate_plan02',stage='gate-validation',
        created_at=datetime.now(timezone.utc).isoformat(),gate='PASS',tests=results,total_tests=sum(results.values()),
        schemas_checked=len(validators),documents_schema_checked=schema_checked,packages=packages,
        environment_snapshot_sha256=snapshots,legacy_hashes_unchanged=legacy,
        baseline_summary_sha256=sha(PUBLIC/'baseline_summary.json'),
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths},
        test_output_sha256={name:sha(PUBLIC/(name+'_test_output.txt')) for name in results},
        limitations=['synthetic technical scope only','no OCR inference, field extraction or confidence calibration',
                    'single local worker; extraction outbox consumer belongs to PLAN_03',
                    'Windows Job Object verified; POSIX limits not exercised on this host'])
    (PUBLIC/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {sum(results.values())} tests; {len(validators)} schemas; {schema_checked} document manifests; legacy databases unchanged')


if __name__=='__main__': main()
