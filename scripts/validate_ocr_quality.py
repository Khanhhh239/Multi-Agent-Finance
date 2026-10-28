"""Current regression evidence; never overwrites historical OCR gate reports."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);args=parser.parse_args()
    if not args.run_id.replace('_','').replace('-','').isalnum():parser.error('Use a plain run ID')
    out=APP/'data/ocr_quality'/args.run_id;out.mkdir(parents=True,exist_ok=False)
    report={'created_at':datetime.now(timezone.utc).isoformat(),'checks':[],'release_approved':False,
            'scope':'Functional regressions and real Chrome with synthetic fixtures; no real-invoice accuracy claim'}
    suites=('contracts','ingestion','ocr','extraction_v1','quality','review','planning','rules_v1','e2e_v1','explanation','legal_v2','business_review','recovery')
    commands=[(name,[sys.executable,'-m','unittest','discover','-s','tests/'+name,'-v'],APP) for name in suites]
    commands += [('javascript-syntax-'+path.name,['node','--check',str(path)],APP) for path in sorted((APP/'src/review/static').glob('*.js'))]
    commands += [(name,['node','tests/review/'+name],APP) for name in ('review_client.test.js','explanation_client.test.js')]
    commands += [(name,[sys.executable,str(ROOT/'scripts'/name)],ROOT) for name in
                 ('check_region_browser.py','check_automation_v2_browser.py','check_capture_upgrade_browser.py','check_invoice_test_browser.py')]
    for name,command,cwd in commands:
        result=subprocess.run(command,cwd=cwd,capture_output=True,encoding='utf-8',errors='replace')
        (out/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        counts=re.findall(r'Ran (\d+) tests?',result.stdout+result.stderr)
        report['checks'].append({'name':name,'passed':result.returncode==0,'python_tests':sum(map(int,counts))})
        report['python_tests']=sum(row['python_tests'] for row in report['checks'])
        report['passed']=all(row['passed'] for row in report['checks'])
        (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(name+': '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
    paths=[p for p in (APP/'src').rglob('*') if p.is_file() and p.suffix in ('.py','.js','.css','.html')]
    report['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
