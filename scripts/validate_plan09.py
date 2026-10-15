"""Latest integration validator; keeps historical PLAN_05–08 evidence unchanged."""
import sys,json,unittest,subprocess,importlib.metadata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';OUT=ROOT/'docs/agent3/plans/evidence/plan09'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/e2e_v1'))


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())


def main():
    import test_compliance as fixtures
    from src.orchestration.contracts import EvaluationCommand,EvaluationReport,EvaluationState,EvaluationArtifact,RuleResultView,Explanation
    from src.orchestration.workflow import implementation_sha
    from src.explanation.service import load_templates
    from src.canonicalization.derive import sha
    from src.rules.models import load_package
    from src.planning.catalog import load_catalog
    results=[]
    for name in ('contracts','ingestion','ocr','extraction_v1','quality','review','planning','rules_v1','e2e_v1'):
        result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(APP/'tests'/name)))
        results.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    commands=[['node','--check','src/review/static/app.js'],['node','--check','src/review/static/compliance.js'],['node','tests/review/review_client.test.js']]
    js=[]
    for command in commands:
        result=subprocess.run(command,cwd=APP,capture_output=True,text=True)
        js.append(dict(command=' '.join(command),passed=result.returncode==0))
        if result.returncode:print(result.stderr)
    for model in (EvaluationCommand,EvaluationReport,EvaluationState,EvaluationArtifact,RuleResultView,Explanation):
        write(APP/'contracts/compliance-v1'/(model.__name__+'.schema.json'),model.model_json_schema())
    fixture=fixtures.ComplianceTests('test_reviewed_capture_real_zen_template_snapshot_replay');fixture.setUp()
    try:
        fixture.approved();sample=fixture.run_evaluation()
        fixture.workflow.replay(fixture.ctx,fixture.payer,sample.evaluation_id)
        artifact=fixture.workflow.artifact(fixture.ctx,fixture.payer,sample.evaluation_id)
        write(OUT/'synthetic_evaluation.json',artifact.model_dump(mode='json'))
        fixture.correct_direction();new=fixture.run_evaluation('plan09-new-revision')
        write(OUT/'revision_acceptance.json',dict(old_evaluation_id=sample.evaluation_id,new_evaluation_id=new.evaluation_id,
            old_revision=sample.record_revision,new_revision=new.record_revision,
            old_is_current=fixture.workflow.get(fixture.ctx,fixture.payer,sample.evaluation_id).is_current_revision,
            hashes_differ=sample.report.record_sha256!=new.report.record_sha256,
            scope='Synthetic reviewed capture; not approved real legal cases'))
    finally:fixture.doCleanups()
    package=load_package();rules,legal,taxonomy=load_catalog()
    source_files={p.relative_to(APP).as_posix():sha_raw(p.read_bytes()) for folder in ('src/review/static','src/api/v1','src/orchestration','src/explanation')
        for p in sorted((APP/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.js','.css','.html','.json')}
    manifest=dict(release_id='capture-compliance-technical-v1',checked_on='2026-10-15',status='TECHNICAL_ONLY_LEGAL_RELEASE_PENDING',
        schema_version='1.0.0',database_version=9,workflow_sha256=implementation_sha(),source_sha256=source_files,
        zen_version=importlib.metadata.version('zen-engine'),package_version=package.version,package_sha256=sha(package.model_dump(mode='json')),
        schema_sha256={p.relative_to(APP).as_posix():sha_raw(p.read_bytes()) for p in sorted((APP/'contracts').rglob('*.schema.json'))},
        config_sha256={p.relative_to(APP).as_posix():sha_raw(p.read_bytes()) for p in sorted((APP/'configs').rglob('*.json'))},
        ruleset_version=rules.version,legal_snapshot=legal.version,taxonomy_version=taxonomy.version,
        template_version=load_templates()['version'],template_sha256=sha(load_templates()),
        approved_real_models=sum(m.publication!='DRAFT' for m in package.models),real_taxonomy_mappings=len(taxonomy.mappings),
        pending=['P09-T06 independently labeled legal evaluation and frozen legal holdout','Legal rule/model/mapping approval','PLAN_05/06 calibration and real-data acceptance','PLAN_14 production hardening'])
    write(OUT/'release_capture_compliance_v1.json',manifest)
    browser=APP/'data/plan09/browser/result.json'
    browser_result=json.loads(browser.read_text(encoding='utf-8')) if browser.exists() else {'result':'PENDING'}
    write(OUT/'browser_summary.json',browser_result)
    report=dict(checked_on='2026-10-15',scope='PLAN_09 integration technical only; synthetic native capture and actual ZEN/Chrome',
        workflow_sha256=implementation_sha(),suites=results,total_tests=sum(r['tests'] for r in results),javascript=js,
        browser=browser_result['result'],passed=all(not r['failures'] and not r['errors'] for r in results) and all(r['passed'] for r in js) and browser_result['result']=='PASS',
        legal_acceptance='PENDING',frozen_legal_evaluation='NOT_RUN_NO_APPROVED_RULES_OR_LEGAL_LABELS',
        sample_evaluation_id=sample.evaluation_id,stage_seconds=sample.report.stage_seconds,
        latency_scope='One synthetic integration sample; no SLA or p95 claim',release_manifest='release_capture_compliance_v1.json')
    write(OUT/'validation_summary.json',report)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['passed'] else 1


def sha_raw(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


if __name__=='__main__':raise SystemExit(main())
