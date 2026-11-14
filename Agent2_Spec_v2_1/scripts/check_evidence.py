#!/usr/bin/env python3
"""Validate evidence consistency. Not a proof of honest tests or reviewer identity."""
import argparse,csv,hashlib,json,re,sys,xml.etree.ElementTree as ET
from pathlib import Path
import jsonschema

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)
def load(p):return json.loads(p.read_text())
def check(root,stage):
    folder=root/'evidence'/stage
    a=load(folder/'acceptance.json');jsonschema.validate(a,load(root/'templates/acceptance.schema.json'))
    require(a['stage']==stage,'stage mismatch')
    expected={x['id'] for x in load(root/'test_catalog.json')['tests'] if x['stage']==stage}
    ids=[x['id'] for x in a['tests']];require(len(ids)==len(set(ids)) and set(ids)==expected,'missing/duplicate/extra test IDs')
    require(all(x['status']=='pass' for x in a['tests']),'acceptance not all pass')
    for t in a['tests']:require((folder/t['evidence_path']).is_file(),'missing evidence '+t['id'])
    if stage=='R0':
        env=load(folder/'environment.json')
        for k in ['repo_path','commit','languages','framework','database','native_test_commands','tool_versions']:require(bool(env.get(k)),f'missing environment {k}')
        require(Path(env['repo_path']).is_dir(),'repo not accessible')
        rows=list(csv.DictReader((folder/'inventory.csv').open()))
        require({'rules','scores','graph','ml','orchestrator','web'}<={x.get('group') for x in rows},'incomplete inventory groups')
        for x in rows:require(all(x.get(k) for k in ['path','input','output','fit_requirement','decision']),'incomplete inventory row')
        flows=load(folder/'flow_inventory.json');require({x['id'] for x in flows}=={f'FLOW-{i:02}' for i in range(1,9)},'missing FLOW')
        for f in flows:
            require(f['status'] in ['present','not_present','not_testable'],'FLOW status')
            require((folder/f['evidence_path']).is_file(),'FLOW evidence missing')
            if f['status']=='present':require(bool(f.get('red_test_id') or f.get('blocker')),'present FLOW needs red test or blocker')
            if f['status']=='not_testable':require(bool(f.get('blocker')),'not_testable needs blocker')
        for name in ['state_migration.csv','baseline.json','source_audit.json','REPORT.md']:require((folder/name).is_file(),'missing '+name)
        require(load(folder/'source_audit.json')['spec_version']=='2.1','source version')
        return {'status':'READY_FOR_REVIEW','stage':stage,'scope':'R0 document checks; baseline may be red'}
    result=load(folder/'commands_result.json')
    require(result['spec_version']=='2.1' and result['stage']==stage,'run version/stage mismatch')
    require(a['run_id']==result['run_id'],'stale acceptance run_id')
    require(bool(result.get('commit')) and bool(result.get('tool_versions')),'missing provenance')
    statuses={}
    for command in result['commands']:
        require(command['exit_code']==0 and not command['timed_out'],'command failed/timed out')
        report=folder/command['report_file'];require(digest(report)==command['report_sha256'],'report changed')
        if command['format']=='junit':
            cases=list(ET.parse(report).getroot().iter('testcase'))
            require(cases,'empty report')
            for tc in cases:
                require(tc.find('skipped') is None,'skipped test')
                state='fail' if tc.find('failure') is not None or tc.find('error') is not None else 'pass'
                for id in re.findall(r'R\d-\d+',tc.get('name','')):require(id not in statuses,'duplicate testcase ID');statuses[id]=state
        else:
            report_data=load(report);require(report_data.get('tests'),'empty report')
            for tc in report_data['tests']:
                require(tc['status'] in ['pass','fail'],'skip/unknown test status')
                require(tc['id'] not in statuses,'duplicate testcase ID');statuses[tc['id']]=tc['status']
    require(all(x=='pass' for x in statuses.values()),'machine report contains failed tests')
    require(expected<=statuses.keys(),'mandatory IDs not in machine reports')
    require(all(statuses[x]=='pass' for x in expected),'machine tests failed')
    return {'status':'READY_FOR_REVIEW','stage':stage,'run_id':result['run_id'],'release_approved':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('stage');p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=p.parse_args()
    try:out=check(args.root,args.stage);code=0
    except (ValueError,KeyError,OSError,ET.ParseError,jsonschema.ValidationError) as e:out={'status':'BLOCKED_OR_FAILED','reason':str(e)};code=2
    print(json.dumps(out,ensure_ascii=False));return code
if __name__=='__main__':sys.exit(main())
