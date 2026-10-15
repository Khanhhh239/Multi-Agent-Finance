"""Start/stop the local review service without altering PowerShell policies."""
import argparse
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


def launch(port=8765, stop=False):
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
    try:
        health = request(url + '/api/health')
        if health.get('application') == 'sme-case-review' and not health.get('qa'):
            print(f'Already running: {url}')
            return
    except OSError:
        pass
    instance_id = secrets.token_urlsafe(24)
    stdout_path, stderr_path = runtime / f'server_{port}.out.log', runtime / f'server_{port}.err.log'
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        process = subprocess.Popen([sys.executable, '-u', '-m', 'sme_fraud.review_server', '--port', str(port),
            '--instance-id', instance_id], cwd=root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
    record_path.write_text(json.dumps(dict(pid=process.pid, port=port, instance_id=instance_id, url=url), indent=2), encoding='utf-8')
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
    args = parser.parse_args()
    launch(args.port, args.stop)


if __name__ == '__main__':
    main()
