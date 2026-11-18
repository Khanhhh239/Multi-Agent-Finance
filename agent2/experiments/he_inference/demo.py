"""Real HE smoke test with two enterprise keys and a separate ciphertext worker."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
try:
    import tenseal as ts
except ImportError:  # pragma: no cover - optional wheel on Windows Python 3.12+
    ts = None
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .enterprise import EnterpriseSession
from .protocol import (ABS_TOLERANCE, HEUnavailable, REL_TOLERANCE, canonical, public_hex,
                       sha, unb64, MAX_CONTEXT, MAX_CIPHER)


def fixtures(company):
    rng = np.random.default_rng(1201 if company == 'C001' else 1202)
    center = [4, 8] if company == 'C001' else [7, 2]
    history = rng.normal(center, [.7, 1.2], size=(32, 2)).tolist()
    query = [[center[0] + a, center[1] + b] for a, b in [(.1, .2), (-.3, .4), (.8, -.5), (-1., -1.), (1.5, 2.)]]
    return history, query


def worker_environment():
    # Do not forward Portal tokens, cloud credentials, arbitrary PYTHONPATH or
    # other enterprise environment secrets across the worker boundary.
    allowed = ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'SYSTEMDRIVE',
               'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS')
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[2]),
               PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    return env


def worker_process(packet, policy, key, folder):
    folder.mkdir()
    (folder / 'request.json').write_bytes(canonical(packet))
    (folder / 'policy.json').write_bytes(canonical(policy))
    # This is a worker response-signing key, never an HE decryption key.
    (folder / 'worker-signing-key.hex').write_text(key.private_bytes_raw().hex())
    env = worker_environment()
    command = [sys.executable, '-X', 'utf8', '-B', '-m', 'experiments.he_inference.cloud_worker',
               '--request', 'request.json', '--policy', 'policy.json',
               '--signing-key', 'worker-signing-key.hex', '--replay-db', 'replay.sqlite3', '--output', 'result.json',
               '--metrics-output', 'metrics.json']
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=folder, env=env, capture_output=True, timeout=45)
    elapsed = time.perf_counter() - started
    response = json.loads((folder / 'result.json').read_bytes())
    return response, completed.returncode, elapsed


def run(output):
    if ts is None:
        raise HEUnavailable('tenseal_unavailable')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    summary = dict(status='passed', data='synthetic_only', actual_cloud_deployment=False,
                   active_model_changed=False, queue_written=False,
                   backend='TenSEAL 0.3.18 / Microsoft SEAL CKKS',
                   tolerance=dict(absolute=ABS_TOLERANCE, relative=REL_TOLERANCE), companies=[])
    context_ids = []
    with tempfile.TemporaryDirectory(prefix='agent2-he-') as temporary:
        for company in ('C001', 'C002'):
            history, query = fixtures(company)
            started = time.perf_counter()
            session = EnterpriseSession('demo', company, history, history_end=100, evaluation_start=200)
            fit_key_seconds = time.perf_counter() - started
            signer = Ed25519PrivateKey.generate()
            started = time.perf_counter()
            packet, policy = session.prepare(query, public_hex(signer), event_times=[201] * 5)
            encryption_seconds = time.perf_counter() - started
            response, code, elapsed = worker_process(packet, policy, signer, Path(temporary) / company)
            metrics = json.loads((Path(temporary) / company / 'metrics.json').read_bytes())
            if code:
                raise AssertionError(response)
            public = ts.context_from(unb64(packet['payload']['context'], MAX_CONTEXT), n_threads=1)
            assert not public.has_secret_key()
            public_result = ts.ckks_vector_from(public, unb64(response['payload']['ciphertext'], MAX_CIPHER))
            try:
                public_result.decrypt()
            except ValueError:
                public_decrypt_rejected = True
            else:
                raise AssertionError('Cloud can decrypt')
            started = time.perf_counter()
            scores = np.asarray(session.open(response, packet['payload']['nonce']))
            decrypt_seconds = time.perf_counter() - started
            original = session.model.score(np.asarray(query))
            clear = session.clear_circuit(query)
            assert np.allclose(original, clear, atol=1e-10, rtol=1e-10)
            assert np.allclose(clear, scores, atol=ABS_TOLERANCE, rtol=REL_TOLERANCE)
            assert response['payload']['worker'] == dict(has_decryption_key=False, enterprise_imported=False, sklearn_imported=False)
            context_ids.append(session.binding['context_sha256'])
            report = dict(company_id=company, rows=5, fit_rows=32,
                          history_end=100, evaluation_start=200,
                          original_scores=original.tolist(), clear_circuit_scores=clear.tolist(), decrypted_scores=scores.tolist(),
                          max_abs_original_vs_circuit=float(np.max(np.abs(original - clear))),
                          max_abs_circuit_vs_he=float(np.max(np.abs(clear - scores))),
                          ciphertext_only_worker=True, worker_without_private_key_cannot_decrypt=public_decrypt_rejected,
                          worker=response['payload']['worker'], subprocess_exit_code=code,
                          fit_and_key_seconds=fit_key_seconds, encryption_seconds=encryption_seconds,
                          worker_seconds=elapsed, decryption_seconds=decrypt_seconds,
                          worker_metrics=metrics,
                          request_bytes=len(canonical(packet)), result_bytes=len(canonical(response)),
                          public_context_bytes=len(session.public_context),
                          request_sha256=sha(canonical(packet)), model_id=session.binding['model_id'])
            (output / (company + '-parity.json')).write_bytes(canonical(report))
            summary['companies'].append(report)
    assert len(set(context_ids)) == 2
    summary['separate_company_keys'] = True
    summary['fit_location'] = 'enterprise only, before worker request'
    summary['score_semantics'] = 'raw squared Mahalanobis distance; not probability or alert'
    (output / 'summary.json').write_bytes(canonical(summary))
    print(json.dumps(dict(status='passed', companies=2, rows=10,
                         max_error=max(r['max_abs_circuit_vs_he'] for r in summary['companies']),
                         output=str(output)), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    run(parser.parse_args().output_dir)
