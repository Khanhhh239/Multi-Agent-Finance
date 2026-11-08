"""PLAN_04 gate verification; earlier evidence is read-only."""
import json,re,sqlite3,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(PROJECT))
from src.extraction.contracts import ExtractionArtifact
from src.extraction.service import implementation_sha,canonicalize
from src.extraction.repository import ExtractionRepository
from src.domain.taxpayer import AccessContext
from src.config import Settings
from src.persistence.repository import digest
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan04'

def main():
    PUBLIC.mkdir(parents=True,exist_ok=True)
    prior=[p for p in (ROOT/'docs/agent3/plans/evidence').rglob('*') if p.is_file() and 'plan04' not in p.parts and p.suffix in ('.json','.txt')]
    legacy=list((PROJECT/'data/database').glob('*.db'))
    before={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in prior+legacy}
    tests={}
    for name in ('contracts','ingestion','ocr','extraction_v1'):
        run=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),'-m','unittest','discover','-s','tests/'+name,'-v'],cwd=PROJECT,capture_output=True,text=True)
        output=run.stdout+run.stderr;(PUBLIC/(name+'_test_output.txt')).write_text(output,encoding='utf-8')
        if run.returncode: print(output);raise RuntimeError(name+' tests failed')
        tests[name]=int(re.search(r'Ran (\d+) tests',output)[1])
    for name in ('plan01','plan02'):
        snapshot=json.loads((ROOT/'docs/agent3/plans/evidence'/name/'environment_snapshot.json').read_text(encoding='utf-8'))
        for file,expected in snapshot['files'].items(): assert digest((PROJECT/'.venv/Lib/site-packages'/file).read_bytes())==expected
    directory=PROJECT/'contracts/extraction-v1';registry=json.loads((directory/'registry.json').read_text())
    validators={}
    for name,expected in registry['schemas'].items():
        raw=(directory/name).read_bytes();assert digest(raw)==expected
        schema=json.loads(raw);Draft202012Validator.check_schema(schema);validators[name]=Draft202012Validator(schema)
    baseline=json.loads((PUBLIC/'baseline_summary.json').read_text(encoding='utf-8'))
    assert len(baseline['outcomes'])==15 and baseline['all_require_review'] and not baseline['production_accuracy_claim']
    sha=implementation_sha()
    for row in baseline['outcomes']:
        raw=(ROOT/row['artifact_path']).read_bytes();assert digest(raw)==row['artifact_sha256']
        payload=json.loads(raw);validators['extraction_artifact.schema.json'].validate(payload)
        artifact=ExtractionArtifact.model_validate(payload)
        assert artifact.extractor_sha256==sha and artifact.review_required and row['idempotence_and_pure_replay']
        settings=Settings(database_path=ROOT/'data invoice/plan04_local'/(row['cohort']+'.sqlite3'))
        repo=ExtractionRepository(settings)
        ctx=AccessContext(actor_id='validator',tenant_id=artifact.tenant_id,taxpayer_ids=frozenset({artifact.taxpayer_id}))
        assert repo.get(ctx,artifact.taxpayer_id,artifact.artifact_id)==artifact
        assert repo.base.record(ctx,artifact.taxpayer_id,artifact.record.record_id)==artifact.record
        normalized=repo.ocr.get(ctx,artifact.taxpayer_id,artifact.ingestion_id,row['ocr_config_key'])['result']
        master=repo.base.taxpayer(ctx,artifact.taxpayer_id,artifact.record.taxpayer_master_revision)
        replay=canonicalize(normalized,artifact.record.source_format,master,artifact.profile,artifact.identity_map,
            record_id=artifact.record.record_id,artifact_id=artifact.artifact_id,created_at=artifact.created_at,extractor_sha256=sha)
        assert replay==artifact
        assert artifact.record.item_discovery_status=='UNKNOWN' # Original fixtures have no explicit row-count evidence.
    for path,expected in before.items(): assert digest((ROOT/path).read_bytes())==expected,path
    for path,version in (('data invoice/plan02_local/native_unicode_v2/baseline.sqlite3',2),
                         ('data invoice/plan03_local/baseline.sqlite3',3),('data invoice/plan03_local/model_switch/baseline.sqlite3',3)):
        with sqlite3.connect(ROOT/path) as db: assert db.execute('PRAGMA user_version').fetchone()[0]==version
    paths=[p for folder in ('extraction','canonicalization','domain') for p in (PROJECT/'src'/folder).glob('*.py')]
    paths+=list((PROJECT/'tests/extraction_v1').glob('*.py'))+[PROJECT/'migrations/004_extraction.sql',PROJECT/'src/persistence/repository.py',PROJECT/'src/app.py']
    paths+=[ROOT/'scripts'/name for name in ('build_extraction_baseline.py','export_extraction_contracts.py','validate_extraction.py')]
    report={'date':'2026-10-12','created_at':datetime.now(timezone.utc).isoformat(),'gate':'PASS_TECHNICAL_FUNCTIONAL_ONLY',
        'production_quality_gate':'NOT_EVALUATED','tests':tests,'total_tests':sum(tests.values()),'schemas':len(validators),
        'documents':15,'pages':sum(r['pages'] for r in baseline['outcomes']),'cohorts':baseline['cohorts'],
        'extractor_sha256':sha,'baseline_sha256':digest((PUBLIC/'baseline_summary.json').read_bytes()),
        'source_sha256':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in paths},
        'test_output_sha256':{name:digest((PUBLIC/(name+'_test_output.txt')).read_bytes()) for name in tests},
        'prior_evidence_and_legacy_unchanged':before,'limitations':baseline['limitations']}
    (PUBLIC/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS technical scope: '+str(sum(tests.values()))+' tests, '+str(len(validators))+' schemas, 15 documents; production accuracy NOT EVALUATED.')

if __name__=='__main__': main()
