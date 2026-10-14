"""Loopback-only local demo launcher, persistent credentials and queue worker.

No secret is embedded in frontend assets, URLs or process command arguments.
Uses the existing PLAN_06 demo database; never provisions over an existing master.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from .config import PROJECT, Settings
from .domain.taxpayer import TaxpayerMaster
from .ingestion.auth import authenticate
from .jobs.service import CaptureJobs
from .extraction.contracts import ExtractionProfile

LOCAL=PROJECT/'data/local_web'
TENANT='demo-tenant'
PAYER='demo-payer'


def credential():
    LOCAL.mkdir(parents=True,exist_ok=True)
    path=LOCAL/'credentials.json'
    if not path.exists():
        try:
            with path.open('x',encoding='utf-8') as output:
                json.dump({'token':secrets.token_urlsafe(48)},output)
        except FileExistsError:
            pass
    value=json.loads(path.read_text(encoding='utf-8'))['token']
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',value):
        raise ValueError('Invalid local credential file')
    return value


def configure(token,database=None):
    # Dedicated known demo paths, independent of inherited production settings.
    os.environ['CAPTURE_DATABASE_PATH']=str(Path(database).resolve() if database else PROJECT.parent/'data invoice/plan06_local/demo.sqlite3')
    os.environ['CAPTURE_STAGING_DIRECTORY']=str(PROJECT.parent/'data invoice/plan06_local/demo_staging')
    os.environ['CAPTURE_WORKER_TOKEN']=token
    os.environ['CAPTURE_AUTH_GRANTS_JSON']=json.dumps([dict(token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        actor_id='local-reviewer',tenant_id=TENANT,taxpayer_ids=[PAYER],permissions=['READ','WRITE','ADMIN'])])
    settings=Settings.from_env();ctx=authenticate(settings,'Bearer '+token)
    return settings,ctx


def provision(settings,ctx):
    jobs=CaptureJobs(settings);jobs.base.initialize()
    try:jobs.base.taxpayer(ctx,PAYER,1)
    except KeyError:
        master=TaxpayerMaster.model_validate_json((PROJECT/'configs/examples/taxpayer_master.synthetic.json').read_text(encoding='utf-8'))
        jobs.base.add_taxpayer(ctx,master)
    return jobs


def request_runtime(port,token,path='/v1/local-runtime',method='GET'):
    if not isinstance(port,int) or not 1024<=port<=65535:raise ValueError('Invalid local port')
    request=urllib.request.Request(f'http://127.0.0.1:{port}{path}',method=method,
        headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=2) as response:return json.load(response)


def clipboard(token):
    if os.name!='nt':return False
    # Secret goes through stdin, not command line or console output.
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        '$value = [Console]::In.ReadToEnd(); Set-Clipboard -Value $value'],input=token.encode('ascii'),
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode==0


def worker_loop(locale):
    settings=Settings.from_env();ctx=authenticate(settings,'Bearer '+os.environ['CAPTURE_WORKER_TOKEN'])
    jobs=CaptureJobs(settings)
    if os.name=='nt':
        def interrupted(*_):raise KeyboardInterrupt()
        signal.signal(signal.SIGBREAK,interrupted)
    from .adapters.ocr.bridge import OCRBridge
    bridge=OCRBridge(settings)
    try:
        while True:
            with jobs.ingestion.db() as db:
                row=db.execute("SELECT job_id FROM capture_jobs WHERE tenant_id=? AND taxpayer_id=? AND state='QUEUED' ORDER BY rowid LIMIT 1",(ctx.tenant_id,PAYER)).fetchone()
            if row:
                result=jobs.work_one(ctx,PAYER,row['job_id'],bridge,ExtractionProfile(number_locale=locale))
                print(json.dumps({'job':row['job_id'][-8:],'state':result['state'],'error_code':result.get('error_code')}),flush=True)
            else:time.sleep(1)
    except KeyboardInterrupt:
        return 0


def stop_worker(process):
    if process is None or process.poll() is not None:return
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
        process.wait(timeout=8)
    except (OSError,subprocess.TimeoutExpired):
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:process.kill()
        process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description='Open Agent 3 local review UI with an automatic worker.')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--stop',action='store_true')
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--no-clipboard',action='store_true')
    parser.add_argument('--no-worker',action='store_true');parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--database',type=Path,help='Explicit separate demo/test foundation database')
    parser.add_argument('--number-locale',choices=('VI','EN','AUTO'),default='VI')
    args=parser.parse_args()
    if args.worker:return worker_loop(args.number_locale)
    token=credential();session=LOCAL/'session.json'
    if session.exists() and args.database is None:
        try:
            saved=json.loads(session.read_text(encoding='utf-8'))
            expected=str((PROJECT.parent/'data invoice/plan06_local/demo.sqlite3').resolve())
            if not args.stop and saved.get('database')!=expected:raise ValueError('Different demo database')
            port=saved['port']
            runtime=request_runtime(port,token)
            if runtime.get('launcher')=='agent3-local-v1':
                if args.stop:
                    request_runtime(port,token,'/v1/local-shutdown','POST');print('Agent 3 is stopping.');return 0
                if not args.no_clipboard:clipboard(token)
                url=f'http://127.0.0.1:{port}/review'
                print('Already running: '+url)
                if not args.no_browser:webbrowser.open(url)
                return 0
        except (OSError,ValueError,KeyError,urllib.error.URLError):pass
    if args.stop:print('No running local launcher found.');return 0
    if not 1024<=args.port<=65515:parser.error('port must be between 1024 and 65515')
    settings,ctx=configure(token,args.database);provision(settings,ctx)
    port=None
    for candidate in range(args.port,args.port+20):
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',candidate))
            except OSError:continue
            port=candidate;break
    if port is None:raise RuntimeError('No available local port')
    import uvicorn
    from fastapi import Request
    from .app import create_app
    app=create_app(settings);process=None;log=None
    if not args.no_worker:
        log=(LOCAL/'worker.log').open('ab')
        process=subprocess.Popen([sys.executable,'-m','src.local_web','--worker','--number-locale',args.number_locale],
            cwd=PROJECT,env=os.environ.copy(),stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))

    @app.get('/v1/local-runtime')
    def runtime(request:Request):
        actor=authenticate(settings,request.headers.get('Authorization'));actor.require(TENANT,PAYER)
        return dict(launcher='agent3-local-v1',auto_worker=process is not None and process.poll() is None,
                    number_locale=args.number_locale)

    @app.post('/v1/local-shutdown')
    def shutdown(request:Request):
        actor=authenticate(settings,request.headers.get('Authorization'));actor.require(TENANT,PAYER,'ADMIN')
        server.should_exit=True
        return {'status':'stopping'}

    session.write_text(json.dumps({'port':port,'database':str(settings.database_path.resolve())}),encoding='utf-8')
    url=f'http://127.0.0.1:{port}/review'
    print('\nAgent 3: '+url,flush=True)
    print('Demo taxpayer: demo-payer | number locale: '+args.number_locale,flush=True)
    copied=False if args.no_clipboard else clipboard(token)
    print('Access code copied. Click "Dan ma va ket noi" in the browser.' if copied else
          'Paste the token from agent3_tax_compliance/data/local_web/credentials.json into the UI.',flush=True)
    print('Keep this window open. Ctrl+C stops the server and its worker. OPEN_AGENT3.cmd reopens an existing session.',flush=True)

    def open_when_ready():
        for _ in range(100):
            if server.started:
                if not args.no_browser:webbrowser.open(url)
                return
            if server.should_exit:return
            time.sleep(.1)
    threading.Thread(target=open_when_ready,daemon=True).start()
    try:server.run()
    finally:
        stop_worker(process)
        if log:log.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
