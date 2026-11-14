"""Verify Windows venv process-tree stop/restart without touching live services."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def run(output):
    output.mkdir(parents=True,exist_ok=True);workspace=Path(__file__).resolve().parents[2]
    portal_port,agent_port=free_port(),free_port()
    while agent_port==portal_port:agent_port=free_port()
    base=f'http://127.0.0.1:{portal_port}'
    with tempfile.TemporaryDirectory() as directory:
        temp=Path(directory)
        config=dict(portal_port=portal_port,agent_port=agent_port,workspace=str(workspace),temp=str(temp),python=str(workspace/'agent2/.venv/Scripts/python.exe'))
        cfg=temp/'test.json';cfg.write_text(json.dumps(config),encoding='utf-8')
        source='''import sys,json
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text('utf-8'));sys.path.insert(0,c['workspace'])
from portal import server as s
s.CFG={'port':c['portal_port'],'agents':{'agent2':{'port':c['agent_port'],'python':c['python'],'snapshot_db':str(Path(c['temp'])/'snapshots.sqlite3'),'access_file':str(Path(c['temp'])/'access.json')}}}
s.ORIGIN='http://127.0.0.1:'+str(c['portal_port']);s.ORIGINS=(s.ORIGIN,)
s.WORK=Path(c['temp']);s.PENDING=s.WORK/'pending';s.LOGS=s.WORK/'logs';s.PENDING.mkdir();s.LOGS.mkdir()
s.SECURITY_FILE=s.WORK/'security.json';s.AUDIT_FILE=s.WORK/'audit.jsonl';s.BATCH_FILE=s.WORK/'batches.json';s.COMPANY_FILE=s.WORK/'company.json'
s.main()
'''
        with (temp/'server.log').open('wb') as log:
            proc=subprocess.Popen([sys._base_executable,'-X','utf8','-u','-B','-c',source,str(cfg)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def request(path,body=None):
                req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-Platform':'1','Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
            def wait_port(port,want_open):
                for _ in range(50):
                    with socket.socket() as sock:sock.settimeout(.1);opened=sock.connect_ex(('127.0.0.1',port))==0
                    if opened==want_open:return
                    time.sleep(.1)
                raise AssertionError(f'Port {port} state not {want_open}')
            try:
                wait_port(portal_port,True)
                request('/api/agents/agent2/start',{});wait_port(agent_port,True)
                stopped=request('/api/agents/agent2/stop',{});assert stopped['state']=='stopped',stopped;wait_port(agent_port,False)
                request('/api/agents/agent2/start',{});wait_port(agent_port,True)
                with urllib.request.urlopen(f'http://127.0.0.1:{agent_port}/api/v1/ui/settings',timeout=10) as response:assert json.load(response)['auth_mode']=='portal'
                request('/api/agents/agent2/stop',{});wait_port(agent_port,False)
            finally:
                try:request('/api/agents/agent2/stop',{})
                except (OSError,urllib.error.HTTPError):pass
                proc.terminate();proc.wait(timeout=10)
    result=dict(status='passed',scope='isolated OS Portal/Agent2 subprocesses only',start_stop_restart=True,agent_port_closed_after_stop=True,restart_auth_mode='portal',live_services_touched=False)
    (output/'isolated_lifecycle.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
