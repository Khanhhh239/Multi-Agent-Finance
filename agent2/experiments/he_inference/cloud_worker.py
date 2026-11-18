"""Ciphertext-only subprocess. No enterprise module, sklearn, fit or decrypt call.

The policy is installed through the trusted operator channel, never from the
request. Native ciphertext parsing still requires an OS sandbox in deployment.
"""
import argparse
from pathlib import Path
import sqlite3
import sys
import time

try:
    import tenseal as ts
except ImportError:
    ts = None
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .protocol import (BINDING, CONTRACT, MAX_CIPHER, MAX_CONTEXT, MAX_ROWS,
                       PAIRS, PROFILE, VERSION, HEUnavailable, canonical,
                       identifier, read_json, require, sha, sign, unb64)

APP_ID = 0x48455031


def peak_rss_bytes():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]

        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        api.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        api.restype = wintypes.BOOL
        if not api(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize)
    import resource
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(maximum if sys.platform == 'darwin' else maximum * 1024)


def reserve(path, payload, *, request_hash=None,resuming=False):
    """Standalone calls burn a nonce; managed retries require its exact hash.

    Only the worker's exclusive, fenced job owner enables managed resumption.
    Existing unbound/legacy reservations remain burned, including for retries.
    """
    path = Path(path)
    existing = path.exists()
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('BEGIN IMMEDIATE')
        application = conn.execute('PRAGMA application_id').fetchone()[0]
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        require(application == APP_ID if existing else application == 0 and not tables,
                'REPLAY_STORE_INCOMPATIBLE')
        if not existing:
            conn.execute(f'PRAGMA application_id={APP_ID}')
            conn.execute('CREATE TABLE requests (tenant TEXT, company TEXT, session TEXT, nonce TEXT, PRIMARY KEY(tenant,company,session,nonce))')
        key=tuple(payload[k] for k in ('tenant_id','company_id','session_id','nonce'))
        if request_hash is not None:
            require(isinstance(request_hash,str) and len(request_hash)==64 and all(c in '0123456789abcdef' for c in request_hash),'REPLAY_REQUEST_HASH')
            conn.execute('CREATE TABLE IF NOT EXISTS managed_requests (tenant TEXT,company TEXT,session TEXT,nonce TEXT,request_hash TEXT NOT NULL,PRIMARY KEY(tenant,company,session,nonce))')
        old=conn.execute('SELECT 1 FROM requests WHERE tenant=? AND company=? AND session=? AND nonce=?',key).fetchone()
        if old:
            require(request_hash is not None and resuming,'REPLAY_REJECTED')
            bound=conn.execute('SELECT request_hash FROM managed_requests WHERE tenant=? AND company=? AND session=? AND nonce=?',key).fetchone()
            require(bound is not None,'REPLAY_REJECTED')
            require(bound[0]==request_hash,'REPLAY_REQUEST_CONFLICT')
        else:
            conn.execute('INSERT INTO requests VALUES (?,?,?,?)',key)
            if request_hash is not None:conn.execute('INSERT INTO managed_requests VALUES (?,?,?,?,?)',(*key,request_hash))
        conn.commit()
    finally:
        conn.close()


def evaluate(packet, policy, signing_key, replay_db, *, now=None,reservation=None):
    from .protocol import verify, b64
    require(policy.get('enabled') is True, 'HE_POLICY_DISABLED')
    p = verify(packet, policy['client_verify_key'])
    expected = set(BINDING) | {'nonce', 'created_at', 'expires_at', 'row_handles',
                               'context', 'columns', 'quadratic'}
    require(set(p) == expected, 'REQUEST_FIELDS')
    require((p['version'], p['profile'], p['contract']) == (VERSION, PROFILE, CONTRACT), 'PROFILE_UNSUPPORTED')
    for key in BINDING:
        require(p[key] == policy.get(key), 'BINDING_MISMATCH')
    require(all(identifier(p[k]) for k in ('tenant_id', 'company_id', 'session_id', 'model_id', 'key_epoch', 'nonce')), 'INVALID_IDENTIFIER')
    clock = int(time.time()) if now is None else now
    require(type(p['created_at']) is int and type(p['expires_at']) is int
            and p['created_at'] <= clock < p['expires_at'] <= p['created_at'] + 300, 'REQUEST_EXPIRED')
    rows = p['row_handles']
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS
            and all(identifier(r) for r in rows) and len(set(rows)) == len(rows), 'ROW_HANDLES')
    require(isinstance(p['columns'], list) and len(p['columns']) == 2
            and isinstance(p['quadratic'], list) and len(p['quadratic']) == len(PAIRS), 'CIPHER_LAYOUT')
    context_bytes = unb64(p['context'], MAX_CONTEXT)
    require(sha(context_bytes) == p['context_sha256'], 'CONTEXT_HASH')
    columns = [unb64(v, MAX_CIPHER) for v in p['columns']]
    weights = [unb64(v, MAX_CIPHER) for v in p['quadratic']]
    require([sha(v) for v in weights] == policy.get('quadratic_sha256'), 'MODEL_BINDING')
    # Reject private contexts before loading any ciphertext. One thread bounds
    # native parallelism; public context/cipher hashes were authenticated first.
    if ts is None:
        raise HEUnavailable('tenseal_unavailable')
    context = ts.context_from(context_bytes, n_threads=1)
    require(not context.has_secret_key() and context.has_public_key()
            and context.has_relin_keys(), 'PRIVATE_OR_INCOMPLETE_CONTEXT')
    if reservation is None:reserve(replay_db, p)
    else:reservation(p,sha(canonical(packet)))
    xs = [ts.ckks_vector_from(context, v) for v in columns]
    ws = [ts.ckks_vector_from(context, v) for v in weights]
    require(all(v.size() == len(rows) for v in xs + ws), 'CIPHER_LAYOUT')
    score = None
    for (i, j), weight in zip(PAIRS, ws):
        term = xs[i] * xs[j] * weight
        score = term if score is None else score + term
    result = {k: p[k] for k in BINDING}
    result.update(nonce=p['nonce'], row_handles=rows,
                  request_sha256=sha(canonical(packet)), ciphertext=b64(score.serialize()),
                  worker=dict(has_decryption_key=context.has_secret_key(),
                              enterprise_imported='experiments.he_inference.enterprise' in sys.modules,
                              sklearn_imported='sklearn' in sys.modules))
    return sign(result, signing_key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('request', 'policy', 'signing-key', 'replay-db', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--metrics-output')
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(args.signing_key).read_text().strip()))
        response = evaluate(read_json(args.request), read_json(args.policy), key, args.replay_db)
        code = 0
    except HEUnavailable as exc:
        response = dict(status='unavailable', reason=dict(code=exc.code)); code = 2
    except Exception:
        response = dict(status='unavailable', reason=dict(code='HE_EVALUATION_FAILED')); code = 2
    Path(args.output).write_bytes(canonical(response))
    if args.metrics_output:
        Path(args.metrics_output).write_bytes(canonical(dict(
            elapsed_seconds=time.perf_counter() - started, peak_rss_bytes=peak_rss_bytes())))
    return code


if __name__ == '__main__':
    sys.exit(main())
