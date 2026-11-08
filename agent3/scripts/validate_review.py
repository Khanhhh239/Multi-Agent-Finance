"""Validate the technical review milestone and preserve prior evidence/environment/data."""
import json,re,sqlite3,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(PROJECT))
from src.persistence.repository import digest
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.review.correction_service import CorrectionService
from src.review.contracts import CorrectionEvent
from src.quality.repository import replay,implementation_sha
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan06'

def main():
    PUBLIC.mkdir(parents=True,exist_ok=True)
    previous=[p for p in (ROOT/'docs/agent3/plans/evidence').rglob('*') if p.is_file() and 'plan06' not in p.parts and p.suffix in ('.json','.txt')]
    previous+=list((PROJECT/'data/database').glob('*.db'))
    versions={'data invoice/plan02_local/native_unicode_v2/baseline.sqlite3':2,'data invoice/plan03_local/baseline.sqlite3':3,
        'data invoice/plan03_local/model_switch/baseline.sqlite3':3,'data invoice/plan04_local/native.sqlite3':4,'data invoice/plan04_local/hybrid.sqlite3':4,
        'data invoice/plan05_local/native.sqlite3':5,'data invoice/plan05_local/hybrid.sqlite3':5}
    previous+=[ROOT/path for path in versions]
    before={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in previous}
    tests={}
    for name in ('contracts','ingestion','ocr','extraction_v1','quality','review'):
        run=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),'-m','unittest','discover','-s','tests/'+name,'-v'],cwd=PROJECT,capture_output=True,text=True)
        output=run.stdout+run.stderr;(PUBLIC/(name+'_test_output.txt')).write_text(output,encoding='utf-8')
        if run.returncode:print(output);raise RuntimeError(name+' tests failed')
        tests[name]=int(re.search(r'Ran (\d+) tests',output)[1])
    for command,name in ((['node','--check','src/review/static/app.js'],'client_syntax'),
        (['node','tests/review/review_client.test.js'],'client_dom'),
        ([str(PROJECT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/replay_plan05_snapshot.py')],'historical_plan05_replay')):
        run=subprocess.run(command,cwd=PROJECT,capture_output=True,text=True)
        (PUBLIC/(name+'_output.txt')).write_text(run.stdout+run.stderr,encoding='utf-8')
        if run.returncode:raise RuntimeError(name+' failed: '+run.stdout+run.stderr)
    for name in ('plan01','plan02'):
        snapshot=json.loads((ROOT/'docs/agent3/plans/evidence'/name/'environment_snapshot.json').read_text(encoding='utf-8'))
        for file,expected in snapshot['files'].items():assert digest((PROJECT/'.venv/Lib/site-packages'/file).read_bytes())==expected
    target=PROJECT/'contracts/review-v1';registry=json.loads((target/'registry.json').read_text());validators={}
    for name,expected in registry['schemas'].items():
        raw=(target/name).read_bytes();assert digest(raw)==expected;schema=json.loads(raw);Draft202012Validator.check_schema(schema);validators[name]=Draft202012Validator(schema)
    summary=json.loads((PUBLIC/'baseline_summary.json').read_text(encoding='utf-8'))
    assert summary['documents']==15 and summary['pages']==17
    assert summary['human_correction_time_seconds'] is None and summary['after_human_review_field_accuracy'] is None
    assert summary['reviewed_by_independent_human']==0 and summary['ocr_rerun'] is False
    for row in summary['outcomes']:
        raw=(ROOT/row['export_path']).read_bytes();assert digest(raw)==row['export_sha256'];export=json.loads(raw)
        record=export['record'];ctx=AccessContext(actor_id='review-validator',tenant_id=record['tenant_id'],taxpayer_ids=frozenset({record['taxpayer_id']}),permissions=frozenset({'READ'}));payer=record['taxpayer_id']
        repo=CorrectionService(Settings(database_path=ROOT/'data invoice/plan06_local'/(row['cohort']+'.sqlite3')))
        assert repo.rebuild(ctx,payer,row['record_id'])['verified']
        q=repo.quality.get(ctx,payer,row['assessment_id']);assert q.implementation_sha256==implementation_sha()
        assert replay(repo.quality.inputs(ctx,payer,q.assessment_id),q)==q
        assert export['record']['revision']==2 and export['review_required'] and 'verdict' not in export
        with repo.ingestion.db() as db:
            event=db.execute('SELECT * FROM review_events WHERE tenant_id=? AND taxpayer_id=? AND event_id=?',(ctx.tenant_id,payer,row['event_id'])).fetchone()
            event=repo.checked_event(event);validators['correction_event.schema.json'].validate(event);CorrectionEvent.model_validate(event)
            assert db.execute('PRAGMA user_version').fetchone()[0]==6
        tasks=repo.page(ctx,payer,'tasks',record_id=row['record_id'],revision=2,limit=100)
        validators['task_page.schema.json'].validate(tasks)
    for path,version in versions.items():
        with sqlite3.connect(ROOT/path) as db:assert db.execute('PRAGMA user_version').fetchone()[0]==version
    for path,expected in before.items():assert digest((ROOT/path).read_bytes())==expected,path
    paths=list((PROJECT/'src/review').rglob('*'))+list((PROJECT/'src/jobs').glob('*.py'))+list((PROJECT/'tests/review').glob('*'))
    paths+=[PROJECT/'migrations/006_review.sql',PROJECT/'src/app.py',PROJECT/'src/persistence/repository.py',PROJECT/'src/quality/repository.py',PROJECT/'src/quality/assessor.py']
    paths+=list((ROOT/'archive/plan06_pinned_plan05_quality').glob('*.py'))
    paths+=[ROOT/'scripts'/name for name in ('export_review_contracts.py','build_review_baseline.py','validate_review.py','replay_plan05_snapshot.py')]
    paths=[p for p in paths if p.is_file() and '__pycache__' not in p.parts]
    report={'created_at':datetime.now(timezone.utc).isoformat(),'gate':'PASS_TECHNICAL_MANUAL_REVIEW_ONLY','production_gate':'NOT_EVALUATED_DQ_01_TO_05',
        'tests':tests,'total_tests':sum(tests.values()),'schemas':len(validators),'documents':15,'pages':17,'client_dom_harness':'PASS','visual_browser_acceptance':'NOT_EXECUTED',
        'historical_plan05_replay':'PASS_15_ASSESSMENTS_PINNED_IMPLEMENTATION','human_review_time_measured':False,'after_human_review_accuracy_measured':False,
        'correction_latency_ms':summary['correction_latency_ms'],'quality_implementation_sha256':implementation_sha(),
        'source_sha256':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in paths},'prior_evidence_environment_and_databases_unchanged':before,
        'limitations':summary['limitations']}
    (PUBLIC/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS technical/manual: '+str(sum(tests.values()))+' Python tests, client DOM/syntax, 10 schemas, 15 documents/17 pages; production/user acceptance pending.')
if __name__=='__main__':main()
