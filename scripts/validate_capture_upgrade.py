"""Full regression for five operator/OCR/layout/explanation/measurement upgrades."""
import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/capture_upgrade_20261021'
sys.path.insert(0,str(APP))

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode())

def main():
    spec=importlib.util.spec_from_file_location('capture_regression',ROOT/'scripts/validate_automation_v1.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner);runner.OUT=OUT
    status=runner.main(checked_on='2026-10-21');report=json.loads((OUT/'validation_summary.json').read_bytes())
    for name in ('items.js','insights.js'):
        command=['node','--check','src/review/static/'+name];r=subprocess.run(command,cwd=APP,capture_output=True,text=True)
        report['javascript'].append(dict(command=' '.join(command),passed=r.returncode==0))
        if r.returncode:print(r.stderr);status=1
    r=subprocess.run([sys.executable,str(ROOT/'scripts/check_capture_upgrade_browser.py')],cwd=ROOT,capture_output=True,text=True)
    if r.returncode:print(r.stdout,r.stderr);status=1
    browser=json.loads((APP/'data/capture_upgrade/browser/result.json').read_bytes()) if not r.returncode else {'result':'FAIL','checks':[]}
    write(OUT/'browser_capture_upgrade.json',browser)
    report['browser'].append(dict(name='capture_upgrade',passed=browser['result']=='PASS',checks=len(browser['checks'])))
    report['browser_checks']=sum(r['checks'] for r in report['browser'])
    report['implementation_files']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('src/review','src/recovery','src/explanation_v2','src/extraction','src/quality')
        for p in sorted((APP/folder).rglob('*')) if p.suffix in ('.py','.js','.css','.html') and p.is_file()}
    report['scope']='Synthetic operator security/revision/evidence tests, HTTP/SQLite/Chrome and legacy native ZEN regression. No independent real-invoice or legal acceptance.'
    report['passed']=not status and all(r['passed'] for r in report['javascript']+report['browser'])
    write(OUT/'validation_summary.json',report)
    from src.review.contracts import CorrectionCommand,ItemOperation
    target=APP/'contracts/review-v1';registry=json.loads((target/'registry.json').read_bytes())
    for model,name in ((CorrectionCommand,'correction_command.schema.json'),(ItemOperation,'item_operation.schema.json')):
        write(target/name,model.model_json_schema(mode='serialization'));registry['schemas'][name]=hashlib.sha256((target/name).read_bytes()).hexdigest()
    write(target/'registry.json',registry)
    from src.recovery.regions import RegionCommand
    write(APP/'contracts/recovery-v1/RegionCommand.schema.json',RegionCommand.model_json_schema())
    from src.explanation_v2.contracts import UserGuide,ExplanationArtifact
    write(APP/'contracts/explanation-v1/UserGuide.schema.json',UserGuide.model_json_schema())
    write(APP/'contracts/explanation-v1/ExplanationArtifact.schema.json',ExplanationArtifact.model_json_schema())
    print(json.dumps(dict(passed=report['passed'],python_tests=report['total_tests'],browser_checks=report['browser_checks']),indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
