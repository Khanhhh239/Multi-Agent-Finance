"""Current legal-data regression, preserving historical evidence and core code pins."""
import json
import sys
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/legal_revision_20261016_v2'
sys.path.insert(0,str(APP))

def main():
    rows=[]
    for name in ('contracts','ingestion','ocr','extraction_v1','quality','review','planning','rules_v1','e2e_v1','explanation','legal_v2'):
        result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(APP/'tests'/name)))
        rows.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    js=[]
    for args in [('node','--check','src/review/static/app.js'),('node','--check','src/review/static/compliance.js'),
                 ('node','--check','src/review/static/explanation.js'),('node','tests/review/review_client.test.js'),
                 ('node','tests/review/explanation_client.test.js')]:
        run=subprocess.run(args,cwd=APP,capture_output=True,text=True)
        js.append(dict(command=' '.join(args),passed=run.returncode==0))
        if run.returncode:print(run.stderr)
    from src.orchestration.workflow import implementation_sha
    report=dict(checked_on='2026-10-16',suites=rows,total_tests=sum(r['tests'] for r in rows),javascript=js,
        legacy_workflow_implementation_sha256=implementation_sha(),
        scope='Synthetic business cases and real native ZEN; source-linked data, not legal approval or real OCR accuracy',
        production_release='NOT_APPROVED',taxonomy_product_mapping='PENDING',
        passed=all(not r['failures'] and not r['errors'] for r in rows) and all(r['passed'] for r in js))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'validation_summary.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
