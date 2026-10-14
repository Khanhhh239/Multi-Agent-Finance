"""Reproduce PLAN_08 tests, actual SDK probes and public synthetic artifacts."""
import sys
import json
import unittest
import itertools
import platform
import importlib.metadata
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/plan08'
sys.path.insert(0,str(APP))
sys.path.insert(0,str(APP/'tests/rules_v1'))


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def main():
    from src.rules.contracts import ComplianceResult,RuleOutcome,EngineContext,Aggregate,ModelPackage,ExecutionPolicy,PaymentProof
    from src.rules.executor import implementation_sha
    from src.rules.models import load_package
    from src.rules.money_boundary import add,equal
    from src.persistence.repository import digest
    import test_rules as fixtures
    import zen
    results=[]
    for name in ('contracts','ingestion','ocr','extraction_v1','quality','review','planning','rules_v1'):
        suite=unittest.TestLoader().discover(str(APP/'tests'/name))
        result=unittest.TextTestRunner(verbosity=1).run(suite)
        results.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    for model in (ComplianceResult,RuleOutcome,EngineContext,Aggregate,ModelPackage,ExecutionPolicy,PaymentProof):
        write(APP/'contracts/rules-v1'/(model.__name__+'.schema.json'),model.model_json_schema())
    package=load_package()
    probes=[]
    for name,expression,context in (
        ('decimal_object','amount >= 5000000',{'amount':Decimal('5000000')}),
        ('decimal_string_add','amount + 0.01',{'amount':'5000000.01'}),
        ('unsafe_large_integer_add','amount + 1',{'amount':9007199254740992})):
        try:probes.append(dict(name=name,value=zen.evaluate_expression(expression,context)))
        except (TypeError,RuntimeError) as exc:probes.append(dict(name=name,error_type=type(exc).__name__))
    write(OUT/'money_boundary_probe.json',dict(engine_version=importlib.metadata.version('zen-engine'),unsafe_probes=probes,
        selected_policy='decimal-facts-v1',safe_sum=str(add(('9007199254740992','1'))),
        distinct_large_values=not equal('9007199254740992','9007199254740993'),money_sent_to_engine=False,
        supported_domain=dict(max_digits=60,max_scale=12),fraction_oracle_cases=500))
    rows=[]
    for model in package.models:
        decision=zen.ZenEngine().create_decision(model.jdm_json)
        ids=[b.condition_id for b in model.bindings]
        for values in itertools.product((False,True),repeat=len(ids)):
            response=decision.evaluate({'facts':dict(zip(ids,values))},{'trace':True})
            value=response['result']['result']
            expected='PASS' if all(values) else 'FAIL'
            if value!=expected:raise ValueError('DRAFT offline truth table mismatch')
            rows.append(dict(model_id=model.model_id,facts=dict(zip(ids,values)),expected=expected,observed=value,
                matched_row_id=response['trace']['table']['traceData']['rule']['_id']))
    write(OUT/'model_truth_tables.json',dict(scope='Offline technical truth tables on DRAFT models; not approved legal outcomes',rows=rows))
    fixture=fixtures.PersistenceTests('test_capture_review_plan_real_worker_store_replay_end_to_end')
    fixture.setUp()
    try:
        plan,approved=fixture.approved_capture_plan()
        result=fixture.repo.work(fixture.ctx,fixture.payer,plan.evaluation_id,package=approved)
        fixture.repo.replay(fixture.ctx,fixture.payer,result.execution_id)
        ComplianceResult.model_validate_json(result.model_dump_json())
        write(OUT/'synthetic_compliance_result.json',result.model_dump(mode='json'))
        sample=dict(execution_id=result.execution_id,verdict=result.aggregate.verdict,coverage=result.aggregate.coverage,
            record_revision=result.record_revision,attempts=len(result.attempts),replay_verified=True,
            scope='Synthetic approved fixture only; capture/review/real isolated ZEN/SQLite/replay')
    finally:fixture.doCleanups()
    binaries={p.name:digest(p.read_bytes()) for p in Path(zen.__file__).parent.glob('*.pyd')}
    report=dict(checked_on='2026-10-15',scope='PLAN_08 technical; not legal approval, production or real invoice accuracy',
        command='agent3_tax_compliance/.venv/Scripts/python.exe scripts/validate_plan08.py',
        python=platform.python_version(),platform=platform.system(),zen_version=importlib.metadata.version('zen-engine'),
        zen_native_sha256=binaries,implementation_sha256=implementation_sha(),
        package_sha256=fixtures.sha(package.model_dump(mode='json')),model_hashes={m.model_id:m.jdm_sha256 for m in package.models},
        suites=results,total_tests=sum(r['tests'] for r in results),passed=all(not r['failures'] and not r['errors'] for r in results),
        precedence_matrix_cases=128,boolean_review_table_cases=16,public_draft_truth_table_cases=len(rows),fraction_oracle_cases=500,
        functional_sample=sample,pending=['Legal rule/model approval and real goods/services mappings',
            'PLAN_05/06 real-data acceptance','PLAN_09 UI/job integration and template explanations',
            'Trusted payment proof ingestion/matching; no HTTP assertion endpoint'])
    write(OUT/'validation_summary.json',report)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
