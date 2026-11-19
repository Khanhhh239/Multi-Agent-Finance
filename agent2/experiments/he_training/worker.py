"""Ciphertext-only HTTP worker (`HomomorphicAggregator`) for encrypted SGD training.

The worker bundle contains ONLY this module, protocol/store, public circuit,
evaluation keys (`evk`), and the worker's own signing key — NEVER enterprise
secret keys (`sk`) or plaintext `X, y, W`.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import EXECUTION_MODE_NATIVE, EXECUTION_MODE_VERIFIED, resolve_quantization_profile
from .protocol import MAX_PACKET, TrainingError, atomic, canonical, require, sha, strict_json
from .runtime import ENV_HE_AGGREGATOR_URL, HomomorphicAggregator, has_native_concrete
from .store import CloudStore


class NativeEvaluator:
    """Homomorphic circuit evaluator dispatching to native Concrete TFHE or verified LUT circuit."""

    def __init__(self, build, grants):
        self.build = Path(build)
        self.grants = grants
        self.manifest = json.loads((self.build / 'manifest.json').read_bytes())
        require(
            self.manifest.get('all_inputs_encrypted') is True and self.manifest.get('composable') is True,
            'BUILD_NOT_ENCRYPTED',
        )
        for name, digest in self.manifest['files'].items():
            require(sha((self.build / name).read_bytes()) == digest, 'BUILD_TAMPERED')
        self.profile = resolve_quantization_profile(self.manifest)
        self.profile_version = self.profile['profile_version']

        self.use_native = (
            self.manifest.get('execution_mode', EXECUTION_MODE_NATIVE) == EXECUTION_MODE_NATIVE
            and has_native_concrete()
        )
        self.execution_mode = EXECUTION_MODE_NATIVE if self.use_native else EXECUTION_MODE_VERIFIED
        if self.use_native:
            from concrete import fhe
            self.fhe = fhe
            self.server = fhe.Server.load(self.build / 'server.zip')
        else:
            self.fhe = None
            self.server = None
        self.keys = {}
        self.aggregators = {}

    def __call__(self, x, y, weights, body):
        owner = (body['tenant_id'], body['company_id'])
        grant = self.grants[owner]
        if self.use_native:
            if owner not in self.keys:
                raw = Path(grant['evaluation_keys_file']).read_bytes()
                require(sha(raw) == grant['evaluation_keys_sha256'], 'EVALUATION_KEYS_TAMPERED')
                self.keys.clear()  # one company's ~1.3 GB key domain resident at a time (bounded worker memory)
                self.keys[owner] = self.fhe.EvaluationKeys.deserialize(raw)
            values = [self.fhe.Value.deserialize(raw) for raw in (x, y, weights)]
            return self.server.run(*values, evaluation_keys=self.keys[owner]).serialize()

        if owner not in self.aggregators:
            raw = Path(grant['evaluation_keys_file']).read_bytes()
            require(sha(raw) == grant['evaluation_keys_sha256'], 'EVALUATION_KEYS_TAMPERED')
            evk_bundle = strict_json(raw)
            self.aggregators[owner] = HomomorphicAggregator(evk_bundle)
        return self.aggregators[owner].step_bytes(x, y, weights)


def make_server(port, store, batch_store=None, *, bind_host='127.0.0.1', allowed_hosts=None, health=None):
    configured_remote = os.environ.get(ENV_HE_AGGREGATOR_URL, '').strip()
    extra_hosts = set(allowed_hosts or ())
    if configured_remote:
        parsed = urlsplit(configured_remote)
        if parsed.hostname:
            extra_hosts.add(parsed.hostname)
            if parsed.port:
                extra_hosts.add(f'{parsed.hostname}:{parsed.port}')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            try:
                hosts = self.headers.get_all('Host', [])
                valid = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}', *extra_hosts,
                         *(f'{h}:{self.server.server_port}' for h in extra_hosts if ':' not in h)}
                require(len(hosts) == 1 and hosts[0] in valid and not self.headers.get_all('Origin'), 'HOST_DENIED')
                require(self.path == '/health', 'ROUTE_NOT_FOUND')
                status = 200
                result = dict(role='he_training_worker', version='he-training-worker/0.1.0', batch_training=batch_store is not None, **(health or {}))
            except TrainingError as error:
                status = 404 if error.code == 'ROUTE_NOT_FOUND' else 403
                result = dict(error=error.code)
            body = canonical(result)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                valid_hosts = {
                    f'127.0.0.1:{self.server.server_port}',
                    f'localhost:{self.server.server_port}',
                    *extra_hosts,
                    *(f'{h}:{self.server.server_port}' for h in extra_hosts if ':' not in h),
                }
                hosts = self.headers.get_all('Host', [])
                require(len(hosts) == 1 and hosts[0] in valid_hosts, 'HOST_DENIED')
                require(
                    not self.headers.get_all('Origin') and not self.headers.get_all('Transfer-Encoding'),
                    'TRANSPORT_DENIED',
                )
                require(self.headers.get_all('Content-Type') == ['application/json'], 'JSON_REQUIRED')
                sizes = self.headers.get_all('Content-Length', [])
                require(len(sizes) == 1 and sizes[0].isascii() and sizes[0].isdigit(), 'LENGTH_REQUIRED')
                size = int(sizes[0])
                require(0 < size <= MAX_PACKET, 'PACKET_LIMIT')
                raw = self.rfile.read(size)
                require(len(raw) == size, 'BODY_INCOMPLETE')
                packet = strict_json(raw)
                if self.path == '/v1/datasets':
                    result = store.upload(packet)
                elif self.path == '/v1/confirm':
                    result = store.confirm(packet)
                elif self.path == '/v1/jobs':
                    result = store.access(packet)
                elif self.path in ('/v2/datasets', '/v2/confirm', '/v2/jobs'):
                    require(batch_store is not None, 'BATCH_TRAINING_NOT_CONFIGURED')
                    result = {
                        '/v2/datasets': batch_store.upload,
                        '/v2/confirm': batch_store.confirm,
                        '/v2/jobs': batch_store.access,
                    }[self.path](packet)
                else:
                    raise TrainingError('ROUTE_NOT_FOUND')
                status = 200
            except TrainingError as error:
                status = 409
                result = dict(error=error.code)
            except Exception:
                status = 503
                result = dict(error='TRAINING_WORKER_UNAVAILABLE')
            body = canonical(result)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def setup(self):
            super().setup()
            self.connection.settimeout(600)

    server = ThreadingHTTPServer((bind_host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--bind-host', default='127.0.0.1')
    p.add_argument('--ready', type=Path, required=True)
    a = p.parse_args()
    cfg = strict_json(a.config.read_bytes())
    grants = {(g['tenant_id'], g['company_id']): g for g in cfg['grants']}
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(cfg['worker_signing_key']).read_text().strip()))
    evaluator = NativeEvaluator(cfg['build'], grants)
    store = CloudStore(cfg['state'], grants, key, evaluator.manifest['files']['server.zip'], evaluator)
    batches = None
    if cfg.get('batch_training') is True:
        from .batch_store import BatchCloudStore
        batches = BatchCloudStore(
            Path(cfg['state']) / 'batch',
            grants,
            key,
            evaluator.manifest['files']['server.zip'],
            evaluator,
            max_updates=evaluator.manifest['max_steps'],
        )
    server = make_server(a.port, store, batches, bind_host=a.bind_host, allowed_hosts=cfg.get('allowed_hosts'),
                         health=dict(execution_mode=evaluator.execution_mode, profile_version=evaluator.profile_version,
                                     worker_verify_key=key.public_key().public_bytes_raw().hex()))
    atomic(a.ready, canonical(dict(
        port=server.server_port,
        pid=os.getpid(),
        execution_mode=evaluator.execution_mode,
        profile_version=evaluator.profile_version,
        worker_verify_key=key.public_key().public_bytes_raw().hex(),
    )))
    print(f'Encrypted training worker ready ({evaluator.execution_mode})', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
