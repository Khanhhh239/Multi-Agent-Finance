"""Linux supervisor: owns one worker session; stdin EOF stops its whole group."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


def run(config,port):
    first=sys.stdin.buffer.readline(4097)
    owner=json.loads(first)
    if set(owner)!={'token'} or not isinstance(owner['token'],str) or len(owner['token'])!=64:raise ValueError('owner token')
    env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','LANG','TMPDIR'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1')
    child=subprocess.Popen([sys.executable,'-B','-m','experiments.he4.service','--config',str(config),'--port',str(port)],stdin=subprocess.DEVNULL,env=env,start_new_session=True)
    control=config.resolve().parent/f'he4-owner-{port}.json'
    stat=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()
    record=dict(pid=child.pid,start=stat[19],command_sha256=hashlib.sha256(Path(f'/proc/{child.pid}/cmdline').read_bytes()).hexdigest(),token_sha256=hashlib.sha256(owner['token'].encode()).hexdigest(),config=str(config.resolve()))
    temporary=control.with_suffix('.pending');temporary.write_text(json.dumps(record));os.replace(temporary,control)
    try:
        while True:
            # Observe exit without reaping: keeping PID reserved makes it safe
            # to kill this exact session's descendants even after parent death.
            exited=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if exited is not None:return
            ready,_,_=select.select([sys.stdin],[],[],.2)
            if not ready:continue
            line=sys.stdin.buffer.readline(4097)
            if not line:return  # Portal died/closed its owned pipe.
            command=json.loads(line)
            if command==dict(action='stop',token=owner['token']):return
    finally:
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        time.sleep(.2)
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        child.wait(timeout=5)
        if control.exists() and json.loads(control.read_text()).get('token_sha256')==record['token_sha256']:control.unlink()


def kill_owned(config,port):
    request=json.loads(sys.stdin.buffer.readline(4097));record=json.loads((config.resolve().parent/f'he4-owner-{port}.json').read_text())
    if set(request)!={'token'} or hashlib.sha256(request['token'].encode()).hexdigest()!=record['token_sha256'] or record['config']!=str(config.resolve()):raise ValueError('not owned')
    pid=record['pid'];stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();command=Path(f'/proc/{pid}/cmdline').read_bytes()
    if stat[19]!=record['start'] or int(stat[2])!=pid or hashlib.sha256(command).hexdigest()!=record['command_sha256'] or b'experiments.he4.service\x00' not in command:raise ValueError('process identity changed')
    os.killpg(pid,signal.SIGKILL)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--kill-owned',action='store_true');a=p.parse_args()
    if a.kill_owned:kill_owned(a.config,a.port)
    else:run(a.config,a.port)
