"""Full current regression with separate UI evidence; preserve historical gate reports."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/automation_20261018_v1'


def main(checked_on='2026-10-18'):
    spec=importlib.util.spec_from_file_location('business_regression',ROOT/'scripts/validate_business_review.py')
    regression=importlib.util.module_from_spec(spec);spec.loader.exec_module(regression)
    regression.OUT=OUT
    status=regression.main()
    report=json.loads((OUT/'validation_summary.json').read_text(encoding='utf-8'))
    import unittest
    recovery=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(APP/'tests/recovery')))
    report['suites'].append(dict(suite='recovery',tests=recovery.testsRun,failures=len(recovery.failures),errors=len(recovery.errors),skipped=len(recovery.skipped)))
    report['total_tests']+=recovery.testsRun
    if recovery.failures or recovery.errors:status=1
    commands=[['node','--check','src/review/static/'+file] for file in ('app.js','compliance.js','explanation.js','business.js','workflow.js','automation.js','region.js')]
    commands += [['node','tests/review/'+file] for file in ('review_client.test.js','explanation_client.test.js')]
    js=[]
    for command in commands:
        result=subprocess.run(command,cwd=APP,capture_output=True,text=True)
        js.append(dict(command=' '.join(command),passed=result.returncode==0))
        if result.returncode:print(result.stderr)
    browsers=[]
    for script,source,label in [('check_automation_v2_browser.py','data/automation_v2/browser/result.json','automation_v2'),
        ('check_region_browser.py','data/region_recovery/browser/result.json','region'),
        ('check_automation_browser.py','data/automation_v1/browser/result.json','automation'),
        ('check_workflow_browser.py','data/workflow_ui/browser/result.json','workflow'),
        ('check_business_browser.py','data/business_ui/browser/result.json','business'),
        ('check_compliance_browser.py','data/plan09/browser/result.json','compliance'),
        ('check_explanation_browser.py','data/plan12/browser/result.json','explanation')]:
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/script)],cwd=ROOT,capture_output=True,text=True)
        if result.returncode:print(result.stdout,result.stderr)
        data=json.loads((APP/source).read_text(encoding='utf-8')) if not result.returncode else {'result':'FAIL','checks':[]}
        regression.write(OUT/('browser_'+label+'.json'),data)
        browsers.append(dict(name=label,passed=result.returncode==0 and data['result']=='PASS',checks=len(data['checks'])))
    from src.business_review.web import SaveCommand
    regression.write(APP/'contracts/business-review-v1/SaveCommand.schema.json',SaveCommand.model_json_schema())
    report.update(checked_on=checked_on,javascript=js,browser=browsers,browser_checks=sum(b['checks'] for b in browsers),
        scope='Synthetic operator review in real HTTP/SQLite/Chrome, regression and native ZEN fixtures; no legal or bank-document accuracy claim.',
        ui_source_sha256={p.relative_to(APP).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((APP/'src/review/static').glob('*')) if p.is_file()},
        passed=not status and all(r['passed'] for r in js+browsers))
    regression.write(OUT/'validation_summary.json',report)
    print(json.dumps(dict(passed=report['passed'],python_tests=report['total_tests'],browser=report['browser'],browser_checks=report['browser_checks']),indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
