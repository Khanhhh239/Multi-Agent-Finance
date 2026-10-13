"""Verify quality technical gate, without rewriting previous gate evidence."""
import json,re,sqlite3,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(PROJECT))
from src.persistence.repository import digest
from src.quality.contracts import QualityAssessment
from src.quality.policy import load_policy
from src.quality.repository import QualityRepository,replay,implementation_sha
from src.config import Settings
from src.domain.taxpayer import AccessContext
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan05'

def main():
    PUBLIC.mkdir(parents=True,exist_ok=True)
    previous=[p for p in (ROOT/'docs/agent3/plans/evidence').rglob('*') if p.is_file() and 'plan05' not in p.parts and p.suffix in ('.json','.txt')]
    previous+=list((PROJECT/'data/database').glob('*.db'))
    before={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in previous}
    tests={}
    for name in ('contracts','ingestion','ocr','extraction_v1','quality'):
        run=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),'-m','unittest','discover','-s','tests/'+name,'-v'],cwd=PROJECT,capture_output=True,text=True)
        output=run.stdout+run.stderr;(PUBLIC/(name+'_test_output.txt')).write_text(output,encoding='utf-8')
        if run.returncode: print(output);raise RuntimeError(name+' tests failed')
        tests[name]=int(re.search(r'Ran (\d+) tests',output)[1])
    for name in ('plan01','plan02'):
        snapshot=json.loads((ROOT/'docs/agent3/plans/evidence'/name/'environment_snapshot.json').read_text(encoding='utf-8'))
        for file,expected in snapshot['files'].items(): assert digest((PROJECT/'.venv/Lib/site-packages'/file).read_bytes())==expected
    target=PROJECT/'contracts/quality-v1';registry=json.loads((target/'registry.json').read_text());validators={}
    for name,expected in registry['schemas'].items():
        raw=(target/name).read_bytes();assert digest(raw)==expected
        schema=json.loads(raw);Draft202012Validator.check_schema(schema);validators[name]=Draft202012Validator(schema)
    validators['quality_policy.schema.json'].validate(load_policy().model_dump(mode='json'))
    summary=json.loads((PUBLIC/'baseline_summary.json').read_text(encoding='utf-8'))
    assert summary['documents']==15 and summary['review_rate']==1 and summary['accepted_fields']==0
    assert summary['accepted_field_precision'] is None and summary['eligible_calibration_samples']==0
    assert summary['known_wrong_present_fields']==6 and summary['known_wrong_present_auto_accepted']==0
    assert not summary['frozen_release_test_executed'] and not summary['calibration_fit_on_development']
    impl=implementation_sha()
    for row in summary['outcomes']:
        raw=(ROOT/row['artifact_path']).read_bytes();assert digest(raw)==row['artifact_sha256']
        payload=json.loads(raw);validators['quality_assessment.schema.json'].validate(payload)
        assessment=QualityAssessment.model_validate(payload);assert assessment.implementation_sha256==impl
        repo=QualityRepository(Settings(database_path=ROOT/'data invoice/plan05_local'/(row['cohort']+'.sqlite3')))
        ctx=AccessContext(actor_id='quality-validator',tenant_id=assessment.tenant_id,taxpayer_ids=frozenset({assessment.taxpayer_id}))
        assert repo.get(ctx,assessment.taxpayer_id,assessment.assessment_id)==assessment
        assert replay(repo.inputs(ctx,assessment.taxpayer_id,assessment.assessment_id),assessment)==assessment
        assert not any(f.auto_accepted for f in assessment.fields) and assessment.confidence.calibrated_count==0
    card=json.loads((PUBLIC/'calibration_card.json').read_text());assert card['status']=='UNAVAILABLE' and not card['production_enabled']
    inventory=json.loads((PUBLIC/'calibration_dataset_manifest.json').read_text(encoding='utf-8'))
    assert len(inventory)==211 and all(r['split']=='DEVELOPMENT' and not r['calibration_eligible'] for r in inventory)
    for path,version in (('data invoice/plan02_local/native_unicode_v2/baseline.sqlite3',2),
                         ('data invoice/plan03_local/baseline.sqlite3',3),('data invoice/plan03_local/model_switch/baseline.sqlite3',3),
                         ('data invoice/plan04_local/native.sqlite3',4),('data invoice/plan04_local/hybrid.sqlite3',4)):
        with sqlite3.connect(ROOT/path) as db: assert db.execute('PRAGMA user_version').fetchone()[0]==version
    for path,expected in before.items(): assert digest((ROOT/path).read_bytes())==expected,path
    paths=list((PROJECT/'src/quality').glob('*.py'))+list((PROJECT/'tests/quality').glob('*.py'))
    paths+=[PROJECT/'migrations/005_quality.sql',PROJECT/'src/persistence/repository.py',PROJECT/'src/app.py',PROJECT/'configs/quality/quality_policy_v1.yaml']
    paths+=[ROOT/'scripts'/name for name in ('export_quality_contracts.py','build_quality_baseline.py','validate_quality.py')]
    report={'date':'2026-10-13','created_at':datetime.now(timezone.utc).isoformat(),'gate':'PASS_TECHNICAL_MANUAL_REVIEW_ONLY',
        'production_calibration_gate':'NOT_EVALUATED_DQ_DEPENDENCIES','tests':tests,'total_tests':sum(tests.values()),'schemas':len(validators),
        'documents':15,'pages':17,'review_rate':1.0,'auto_accepted_fields':0,'accepted_precision':None,
        'known_wrong_present_fields':6,'wrong_present_auto_accepted':0,'eligible_calibration_samples':0,
        'implementation_sha256':impl,'source_sha256':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in paths},
        'output_sha256':{str(p.relative_to(PUBLIC)):digest(p.read_bytes()) for p in PUBLIC.glob('*.json') if p.name!='validation_summary.json'},
        'prior_evidence_and_legacy_unchanged':before,'limitations':summary['limitations']}
    (PUBLIC/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS technical/manual: '+str(sum(tests.values()))+' tests, '+str(len(validators))+' schemas; 15 documents; production calibration UNAVAILABLE.')

if __name__=='__main__': main()
