"""Run current regression without overwriting historical PLAN_09 evidence."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/plan12'
sys.path.insert(0,str(APP))


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())


def main():
    results=[]
    for name in ('contracts','ingestion','ocr','extraction_v1','quality','review','planning','rules_v1','e2e_v1','explanation'):
        result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(APP/'tests'/name)))
        results.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    js=[]
    for file in ('app.js','compliance.js','explanation.js'):
        command=['node','--check','src/review/static/'+file]
        result=subprocess.run(command,cwd=APP,capture_output=True,text=True)
        js.append(dict(command=' '.join(command),passed=result.returncode==0))
    for file in ('review_client.test.js','explanation_client.test.js'):
        command=['node','tests/review/'+file]
        result=subprocess.run(command,cwd=APP,capture_output=True,text=True)
        js.append(dict(command=' '.join(command),passed=result.returncode==0))
        if result.returncode:print(result.stderr)
    from src.explanation_v2.service import load_config, implementation_sha
    from src.explanation_v2.cli import inspect,probe
    from src.explanation_v2.contracts import ExplanationArtifact,LLMOutput,Corpus,Policy
    from src.legal_registry.registry import load_registry
    policy,corpus=load_config();configuration=inspect(policy,corpus,load_registry());configuration['runtime']=probe(policy)
    write(OUT/'configuration_manifest.json',configuration)
    for model in (ExplanationArtifact,LLMOutput,Corpus,Policy):
        write(APP/'contracts/explanation-v1'/(model.__name__+'.schema.json'),model.model_json_schema())
    files={p.relative_to(APP).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for folder in ('src/explanation_v2','configs/explanation')
           for p in sorted((APP/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')}
    browser=APP/'data/plan12/browser/result.json'
    browser_result=json.loads(browser.read_text(encoding='utf-8')) if browser.exists() else {'result':'PENDING'}
    write(OUT/'browser_summary.json',browser_result)
    report=dict(checked_on='2026-10-15',scope='Technical synthetic contracts/native ZEN/local HTTP and browser; no LLM or legal accuracy claim',
        suites=results,total_tests=sum(r['tests'] for r in results),javascript=js,browser=browser_result,
        implementation_sha256=implementation_sha(),source_sha256=files,
        passed=all(not r['failures'] and not r['errors'] for r in results) and all(r['passed'] for r in js) and browser_result['result']=='PASS',
        legal_corpus_acceptance='PENDING',real_model_inference='NOT_RUN_NO_INSTALLED_PINNED_MODEL',
        readability_evaluation='PENDING',production_release='NOT_APPROVED')
    write(OUT/'validation_summary.json',report)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
