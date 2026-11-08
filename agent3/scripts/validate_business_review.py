"""Regression and pinned implementation checks for PLAN_09 business preparation."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/business_review_20261016_v1'
sys.path.insert(0,str(APP))


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode())


def main():
    rows=[]
    for name in ('contracts','ingestion','ocr','extraction_v1','quality','review','planning','rules_v1','e2e_v1','explanation','legal_v2','business_review'):
        result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(APP/'tests'/name)))
        rows.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    from src.orchestration.workflow import implementation_sha as workflow_sha
    from src.business_review.service import implementation_sha
    from src.business_review.contracts import ReviewDossier
    write(APP/'contracts/business-review-v1/ReviewDossier.schema.json',ReviewDossier.model_json_schema())
    legacy_pin='f7f54d632a83f15e22d30662ce65dcd6a8180bfecabe55b8fb58633cacc18dd7'
    report=dict(checked_on='2026-10-16',suites=rows,total_tests=sum(r['tests'] for r in rows),
        implementation_sha256=implementation_sha(),legacy_workflow_implementation_sha256=workflow_sha(),
        source_sha256={p.relative_to(APP).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('src/business_review','configs/business_review') for p in sorted((APP/folder).rglob('*'))
            if p.is_file() and p.suffix in ('.py','.json')},
        legacy_replay_code_unchanged=workflow_sha()==legacy_pin,
        scope='Synthetic dossiers, real local CLI/SQLite/HTTP and native ZEN. Not real-product legal accuracy.',
        real_product_mappings='PENDING_NO_PRODUCT_DOSSIERS',legal_release='NOT_APPROVED',
        passed=all(not r['failures'] and not r['errors'] for r in rows) and workflow_sha()==legacy_pin)
    write(OUT/'validation_summary.json',report)
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
