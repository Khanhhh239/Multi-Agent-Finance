#!/usr/bin/env python3
import datetime,hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
from check_evidence import check
root=Path(__file__).resolve().parents[1]
stage=sys.argv[1] if len(sys.argv)==2 else ''
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def run(argv,cwd,timeout):return subprocess.run(argv,cwd=cwd,timeout=timeout,capture_output=True,text=True)
def main():
    if stage=='R0':print(json.dumps(check(root,stage),ensure_ascii=False));return 0
    config=json.loads((root/'stage_commands.json').read_text()).get(stage)
    if not config or not config.get('cwd') or not config.get('commands'):raise ValueError('missing verified command mapping')
    cwd=config['cwd'];folder=root/'evidence'/stage;folder.mkdir(parents=True,exist_ok=True)
    commit=run(['git','rev-parse','HEAD'],cwd,15);dirty=run(['git','status','--porcelain'],cwd,15)
    if commit.returncode or dirty.returncode:raise ValueError('cannot record git provenance')
    # Hash tracked diff plus untracked file bytes; avoids treating a dirty commit as exact source.
    diff=run(['git','diff','HEAD','--binary'],cwd,30).stdout.encode();tree=hashlib.sha256(diff)
    untracked=run(['git','ls-files','--others','--exclude-standard'],cwd,15)
    for name in sorted(untracked.stdout.splitlines()):
        file=Path(cwd)/name
        if file.is_file():tree.update(name.encode());tree.update(file.read_bytes())
    tools={}
    for argv in config.get('tool_version_commands',[]):
        v=run(argv,cwd,15);tools[' '.join(argv)]={'exit_code':v.returncode,'output':v.stdout+v.stderr}
    if not tools:raise ValueError('tool_version_commands required')
    result={'spec_version':'2.1','stage':stage,'run_id':str(uuid.uuid4()),'commit':commit.stdout.strip(),'dirty':bool(dirty.stdout),'working_tree_sha256':tree.hexdigest(),'started_at':now(),'tool_versions':tools,'commands':[]}
    for i,c in enumerate(config['commands']):
        argv=c['argv'];timeout=c['timeout_seconds'];fmt=c['format']
        if not isinstance(argv,list) or not argv or not 0<timeout<=3600 or fmt not in ['junit','json']:raise ValueError('invalid command mapping')
        source=Path(cwd)/c['report_path'];source.unlink(missing_ok=True) # Only explicitly configured test report; no stale acceptance.
        start=now();timed=False
        try:v=run(argv,cwd,timeout);code=v.returncode;log=v.stdout+'\n'+v.stderr
        except subprocess.TimeoutExpired:timed=True;code=124;log='TIMEOUT'
        dest=folder/f'machine_report_{i}.{ "xml" if fmt=="junit" else "json"}'
        if source.exists():dest.write_bytes(source.read_bytes())
        elif dest.exists():dest.unlink()
        (folder/f'command_{i}.log').write_text(log)
        result['commands'].append({'argv':argv,'cwd':cwd,'started_at':start,'finished_at':now(),'exit_code':code,'timed_out':timed,'format':fmt,'report_file':dest.name,'report_sha256':hashlib.sha256(dest.read_bytes()).hexdigest() if dest.exists() else None})
    result['finished_at']=now();(folder/'commands_result.json').write_text(json.dumps(result,indent=2))
    print('Recorded run_id='+result['run_id']+'. Fill acceptance from machine results, then run check_evidence.py '+stage)
    return 0 if all(c['exit_code']==0 and c['report_sha256'] for c in result['commands']) else 1
if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError,OSError,subprocess.TimeoutExpired) as e:print('BLOCKED:',e);sys.exit(2)
