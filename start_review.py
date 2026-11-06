"""Start/stop the local review service without altering PowerShell policies."""
import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


def request(url, body=None, token=None):
    payload = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'} if body is not None else {}
    if token:
        headers['X-CSRF-Token'] = token
    with urlopen(Request(url, data=payload, headers=headers), timeout=2) as response:
        return json.load(response)


def configured_command(root,port,instance_id,config_path=None):
    """Use one saved local profile for the same data, runtime and permissions."""
    profile=Path(config_path) if config_path else root/'.runtime/review'/f'server_{port}.config.json'
    if not profile.is_absolute():profile=root/profile
    value=json.loads(profile.read_text(encoding='utf-8-sig')) if profile.is_file() else {}
    if config_path and not value:raise ValueError('Local session config is missing or empty')
    allowed={'version','python_executable','python_path','data_root','reports_root','database','qa','demo_ml_manager','ml_review_comparison'}
    if value and (value.get('version')!='review-local-session-v1' or set(value)-allowed):
        raise ValueError('Invalid local session configuration')
    for key in ('qa','demo_ml_manager'):
        if key in value and type(value[key]) is not bool:raise ValueError('Invalid local session flag: '+key)
    if value.get('demo_ml_manager') and not value.get('qa'):raise ValueError('Demo identity requires qa=true')
    def path_setting(key,default=None):
        text=value.get(key,default)
        if not isinstance(text,str) or not text:raise ValueError('Invalid local session path: '+key)
        path=Path(text);return str(path if path.is_absolute() else root/path)
    executable=path_setting('python_executable',sys.executable)
    if not Path(executable).is_file():raise ValueError('Configured Python executable is missing')
    command=[executable,'-u','-B','-m','sme_fraud.review_server','--port',str(port),'--instance-id',instance_id]
    for key in ('data_root','reports_root','database'):
        if key in value:command.extend(['--'+key.replace('_','-'),path_setting(key)])
    for key in ('qa','demo_ml_manager'):
        if value.get(key):command.append('--'+key.replace('_','-'))
    packets=value.get('ml_review_comparison',[]);extra_paths=value.get('python_path',[])
    if (not isinstance(packets,list) or not isinstance(extra_paths,list)
            or any(not isinstance(p,str) or not p for p in packets+extra_paths)):
        raise ValueError('Configured packets and Python paths must be lists of paths')
    for packet in packets:command.extend(['--ml-review-comparison',str((root/packet).resolve())])
    env=os.environ.copy()
    if extra_paths:env['PYTHONPATH']=os.pathsep.join(str((root/p).resolve()) for p in extra_paths)
    env['PYTHONDONTWRITEBYTECODE']='1'
    checksum=hashlib.sha256(profile.read_bytes()).hexdigest() if value else None
    return command,env,checksum,str(profile.resolve()) if value else None


def launch(port=8765, stop=False,config_path=None):
    if not 1 <= port <= 65535:
        raise ValueError('Invalid local port')
    root = Path(__file__).resolve().parent
    runtime = root / '.runtime/review'
    runtime.mkdir(parents=True, exist_ok=True)
    record_path = runtime / f'server_{port}.json'
    url = f'http://127.0.0.1:{port}'
    if stop:
        if not record_path.exists():
            raise ValueError('No record for a service launched by this script')
        record = json.loads(record_path.read_text(encoding='utf-8'))
        health = request(url + '/api/health')
        if health.get('application') != 'sme-case-review' or health.get('instance_id') != record['instance_id']:
            raise ValueError('Service identity differs; refusing to stop another process')
        token = request(url + '/api/meta')['csrf_token']
        request(url + '/api/shutdown', {}, token)
        print('Stopped local review service.')
        return
    instance_id = secrets.token_urlsafe(24)
    command,env,profile_hash,profile_path=configured_command(root,port,instance_id,config_path)
    try:
        health = request(url + '/api/health')
        if health.get('application') == 'sme-case-review':
            record=json.loads(record_path.read_text(encoding='utf-8')) if record_path.is_file() else {}
            if ((record.get('instance_id')==health.get('instance_id') and record.get('config_sha256')==profile_hash)
                    or (profile_hash is None and not health.get('qa'))):
                print(f'Already running: {url}');return
            raise ValueError('Port already serves another local session. Stop that verified session before starting this profile.')
        raise ValueError('Port already serves a different application')
    except OSError:
        pass
    stdout_path, stderr_path = runtime / f'server_{port}.out.log', runtime / f'server_{port}.err.log'
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        process = subprocess.Popen(command, cwd=root, env=env,stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
    record_path.write_text(json.dumps(dict(pid=process.pid, port=port, instance_id=instance_id, url=url,
        config_sha256=profile_hash,config_path=profile_path), indent=2), encoding='utf-8')
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError(f'Startup failed; see {stderr_path}')
        try:
            health = request(url + '/api/health')
            if health.get('instance_id') == instance_id:
                print(f'Review UI ready: {url}\nLog: {stdout_path}')
                return
        except OSError:
            pass
        time.sleep(.2)
    print(f'Still preparing data; open {url} shortly. Log: {stdout_path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--config',type=Path,help='Saved data/runtime/QA profile; defaults to .runtime/review/server_PORT.config.json')
    args = parser.parse_args()
    launch(args.port, args.stop,args.config)


if __name__ == '__main__':
    main()
