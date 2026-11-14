"""Two HTTP services in separate processes and allowlisted worker directory."""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import http.client
import io
import json
import os
import secrets
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
import joblib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .demo import worker_environment
from .protocol import canonical, public_hex, read_json, sign, ABS_TOLERANCE, REL_TOLERANCE
from .registry_demo import setup_demo, source_for, commit, database_dump
from .registry_export import ReadOnlySnapshots
from sme_fraud.method_store import MethodStore
from sme_fraud.snapshot_features import build_from_snapshot
from .worker_bundle import build
from .key_manager import protect_key, create_key, PROVIDER

ROOT = Path(__file__).resolve().parents[2]


def request(port, path, payload=None, *, headers=None, method=None, raw=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=45)
    try:
        extra = dict(headers or {})
        body = canonical(payload) if payload is not None else raw
        if body is not None:
            extra.setdefault('Content-Type', 'application/json')
        connection.request(method or ('POST' if body is not None else 'GET'), path, body, extra)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class Pair:
    def __init__(self, folder, *,state_key_file=None):
        self.root = Path(folder)
        self.enterprise = self.root / 'enterprise'; self.enterprise.mkdir()
        self.worker_root = self.root / 'worker'; self.worker_root.mkdir()
        self.bundle = build(self.worker_root / 'bundle')
        self.env = setup_demo(self.enterprise)
        self.worker_key = Ed25519PrivateKey.generate()
        self.node_key = Ed25519PrivateKey.generate()
        self.grants_file = self.worker_root / 'grants.json'
        self.grants = dict(version='he-worker-grants/1.0.0', grants=[dict(
            tenant_id='demo', company_id=c, node_verify_key=public_hex(self.node_key), active=True) for c in ('C001', 'C002')])
        self.grants_file.write_bytes(canonical(self.grants))
        self.worker_key_path = self.worker_root / 'response-signing.hex'
        self.worker_key_path.write_text(self.worker_key.private_bytes_raw().hex())
        self.node_key_path = self.enterprise / 'provisioning.dpapi.json'
        protect_key(self.node_key.private_bytes_raw(), self.node_key_path, purpose='node-signing')
        self.state_key_path = Path(state_key_file).resolve() if state_key_file else self.enterprise / 'state-wrapping.dpapi.json'
        if not self.state_key_path.exists():create_key(self.state_key_path)
        self.worker_config = self.worker_root / 'service.json'
        self.worker_config.write_bytes(canonical(dict(version='he-worker-service/1.0.0',
            state_dir=str(self.worker_root / 'state'), grants_file=str(self.grants_file),
            response_signing_key_file=str(self.worker_key_path))))
        self.stack = ExitStack()
        self.worker_process = None; self.node_process = None

    def _start(self, module, config, ready, cwd, package_root,port=0):
        env = worker_environment(); env['PYTHONPATH'] = str(package_root)
        args = [sys.executable, '-X', 'utf8', '-B', '-m', module, '--config', str(config),
                '--port', str(port), '--ready-file', str(ready)]
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.stack.callback(self._stop, process)
        deadline = time.monotonic() + 25
        while not ready.exists():
            if process.poll() is not None:
                raise RuntimeError(process.stderr.read().decode('utf-8', errors='replace'))
            if time.monotonic() >= deadline:
                raise RuntimeError('Service startup timed out')
            time.sleep(.03)
        port = read_json(ready)['port']
        return process, port

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            if os.name=='nt':
                stopped=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
                if stopped.returncode and process.poll() is None:process.terminate()
            else:process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()

    def start(self):
        self.worker_process, self.worker_port = self._start('experiments.he_inference.worker_server',
            self.worker_config, self.worker_root / 'ready.json', self.bundle, self.bundle)
        self.node_config = self.enterprise / 'service.json'
        self.node_config.write_bytes(canonical(dict(version='he-enterprise-service/1.2.0', key_protection=PROVIDER,
            auth_file=str(self.env['policy']), model_db=str(self.env['model_db']), snapshot_db=str(self.env['snapshot_db']),
            worker_url=f'http://127.0.0.1:{self.worker_port}', worker_verify_key=public_hex(self.worker_key),
            provisioning_key_file=str(self.node_key_path), state_dir=str(self.enterprise / 'state'),
            state_key_file=str(self.state_key_path))))
        self.node_process, self.node_port = self._start('experiments.he_inference.enterprise_server',
            self.node_config, self.enterprise / 'ready.json', self.enterprise, ROOT)
        return self

    def close(self):
        self.stack.close()

    def restart_node(self):
        self._stop(self.node_process)
        ready = self.enterprise / 'ready.json'; ready.unlink(missing_ok=True)
        config = read_json(self.node_config)
        config['worker_url'] = f'http://127.0.0.1:{self.worker_port}'
        self.node_config.write_bytes(canonical(config))
        self.node_process, self.node_port = self._start('experiments.he_inference.enterprise_server',
            self.node_config, ready, self.enterprise, ROOT)

    def restart_worker(self):
        self._stop(self.worker_process)
        ready = self.worker_root / 'ready.json'; ready.unlink(missing_ok=True)
        self.worker_process, self.worker_port = self._start('experiments.he_inference.worker_server',
            self.worker_config, ready, self.bundle, self.bundle,port=self.worker_port)

    def body(self, company='C001', **values):
        result = dict(artifact_id=self.env['artifacts'][company], snapshot_id=self.env['queries'][company],
                      as_of='2026-10-03T00:00:00+07:00')
        result.update(values)
        return result

    def analyze(self, company='C001', key='demo-request-C001', body=None, authorization=None):
        return request(self.node_port, f'/v1/companies/{company}/he/analyze', self.body(company) if body is None else body,
                       headers={'Authorization': self.env['header'] if authorization is None else authorization, 'Idempotency-Key': key})


def run(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def check(name, passed):
        if not passed:
            raise AssertionError(name)
        checks.append(dict(check=name, passed=True))
    with tempfile.TemporaryDirectory(prefix='he-services-') as folder:
        pair = Pair(folder)
        try:
            before = {name: database_dump(pair.env[name]) for name in ('model_db', 'snapshot_db')}
            pair.start()
            node_status, node_health = request(pair.node_port, '/health')
            worker_status, worker_health = request(pair.worker_port, '/health')
            check('two distinct HTTP processes and separate working directories', pair.worker_process.pid != pair.node_process.pid and pair.bundle != pair.enterprise)
            check('worker distribution cannot import enterprise or business model code', worker_status == 200 and worker_health['enterprise_module_available'] is False and worker_health['business_module_available'] is False)
            check('node declares enterprise-only raw data and HE decryption', node_status == 200 and node_health['he_decryption_location'] == 'enterprise')
            company_results = []
            for company in ('C001', 'C002'):
                status, result = pair.analyze(company, 'demo-http-' + company)
                check(company + ': five source rows return five decrypted scores', status == 200 and result['row_count'] == 5 and all(r['available'] for r in result['rows']))
                scope = pair.env['auth'].authorize(pair.env['header'], company)
                artifact = MethodStore(pair.env['model_db'], read_only=True).get_artifact(scope, pair.env['artifacts'][company])
                model, _ = joblib.load(io.BytesIO(artifact.payload))
                manifest = json.loads(artifact.manifest)
                frame = build_from_snapshot(ReadOnlySnapshots(pair.env['snapshot_db']), scope, pair.env['queries'][company], '2026-10-03T00:00:00+07:00')
                values = [[v[frame['contract']['columns'].index(c)] for c in manifest['selected_columns']] for v in frame['features']]
                expected = model.score(np.asarray(values))
                actual = np.asarray([r['score'] for r in result['rows']])
                check(company + ': HTTP-decrypted scores match original company model', bool(np.allclose(expected, actual, atol=ABS_TOLERANCE, rtol=REL_TOLERANCE)))
                check(company + ': public node DTO excludes technical receipt/model/features', not any(k in canonical(result).decode() for k in ('selected_columns', 'preprocess', 'origin_salt_hex', 'client_verify_key', 'ciphertext')))
                again_status, again = pair.analyze(company, 'demo-http-' + company)
                check(company + ': duplicate request returns same run and same scores', again_status == 200 and result == again)
                (output / (company + '-node-result.json')).write_bytes(canonical(result))
                company_results.append(dict(company_id=company, row_count=result['row_count'], scores=actual.tolist(),
                                            max_abs_error=float(np.max(np.abs(expected - actual)))))
            check('worker has no fit, plaintext upload or decrypt endpoint', all(request(pair.worker_port, path, dict(features=[[1, 2]]))[0] == 404 for path in ('/decrypt', '/fit', '/imports/upload')))
            check('worker rejects unregistered/self-authorized plaintext envelope', request(pair.worker_port, '/v1/evaluate', dict(features=[[1, 2]]))[0] == 400)
            check('node rejects caller-supplied raw feature payload', pair.analyze(body=dict(pair.body(), features=[[1, 2]]), key='reject-raw-input')[0] == 400)
            check('node denies invalid credential', pair.analyze(authorization='Bearer wrong-token', key='bad-node-token')[0] == 401)
            check('model and source stores unchanged by both HTTP services', before == {name: database_dump(pair.env[name]) for name in before})
            summary = dict(status='passed', data='synthetic_only', checks=checks, count=len(checks),
                           companies=company_results, worker_health=worker_health, node_health=node_health,
                           actual_remote_cloud_deployment=False, live_portal_changed=False)
            (output / 'summary.json').write_bytes(canonical(summary))
            manifest = json.loads((pair.bundle / 'worker-manifest.json').read_bytes())
            (output / 'worker-bundle-manifest.json').write_bytes(canonical(manifest))
        finally:
            pair.close()
    print(json.dumps(dict(status='passed', checks=len(checks), companies=2, rows=10, output=str(output))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    run(parser.parse_args().output_dir)
