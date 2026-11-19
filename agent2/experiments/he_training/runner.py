"""Linux supervisor for the ciphertext-only training worker (owned by the Portal, or run standalone by a cloud operator).

Portal mode  : first stdin line is {"token": <64 hex>}; stdin EOF or {"action":"stop","token":...} stops the whole group.
Cloud mode   : `--standalone` keeps running until SIGTERM; no stdin protocol (used by scripts/he_cloud.py serve).
"""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


def _spawn(config, port, bind_host):
    env = {k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'LANG', 'TMPDIR', 'AGENT2_HE_AGGREGATOR_URL'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', OMP_NUM_THREADS=os.environ.get('OMP_NUM_THREADS', '4'), OPENBLAS_NUM_THREADS='1')
    ready = config.resolve().parent / f'he-training-ready-{port}.json'
    if ready.exists():
        ready.unlink()
    return subprocess.Popen(
        [sys.executable, '-B', '-m', 'experiments.he_training.worker', '--config', str(config), '--port', str(port),
         '--bind-host', bind_host, '--ready', str(ready)],
        stdin=subprocess.DEVNULL, env=env, start_new_session=True,
    )


def _terminate(child):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    time.sleep(.3)
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def run(config, port, bind_host='127.0.0.1', standalone=False):
    owner = None
    if not standalone:
        owner = json.loads(sys.stdin.buffer.readline(4097))
        if set(owner) != {'token'} or not isinstance(owner['token'], str) or len(owner['token']) != 64:
            raise ValueError('owner token')
    child = _spawn(config, port, bind_host)
    try:
        while True:
            if os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                return
            if standalone:
                time.sleep(.5)
                continue
            ready, _, _ = select.select([sys.stdin], [], [], .2)
            if not ready:
                continue
            line = sys.stdin.buffer.readline(4097)
            if not line:
                return
            if json.loads(line) == dict(action='stop', token=owner['token']):
                return
    finally:
        _terminate(child)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--bind-host', default='127.0.0.1')
    p.add_argument('--standalone', action='store_true')
    a = p.parse_args()
    run(a.config, a.port, a.bind_host, a.standalone)
