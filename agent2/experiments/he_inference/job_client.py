"""Enterprise CLI: stable receipt -> submit -> poll -> fetch decrypted result."""
import argparse
import http.client
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from sme_fraud.snapshot_features import utc
from .http_common import ServiceError, decode, worker_address
from .protocol import canonical, sha


def atomic(path, value, *, create=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.he-receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        if create:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def call(url, method, path, header, value=None, key=None):
    host, port = worker_address(url)
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        headers = {'Authorization': header}
        if key:
            headers['Idempotency-Key'] = key
        if value is not None:
            headers['Content-Type'] = 'application/json'
        connection.request(method, path, canonical(value) if value is not None else None, headers)
        response = connection.getresponse()
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ServiceError(502, 'NODE_RESPONSE_LIMIT')
        data = decode(raw)
        if response.status not in (200, 202):
            raise ServiceError(response.status, data.get('reason', {}).get('code', 'NODE_REQUEST_FAILED'))
        return data
    except (OSError, http.client.HTTPException) as exc:
        raise ServiceError(503, 'NODE_CONNECTION_UNAVAILABLE') from exc
    finally:
        connection.close()


def run(url, header, company, body, receipt_path, output_path, *, key=None, wait_seconds=60):
    worker_address(url)
    body = dict(body, as_of=utc(body['as_of']).isoformat())
    receipt_path = Path(receipt_path); output_path = Path(output_path)
    fingerprint = sha(canonical(dict(company_id=company, request=body)))
    if not receipt_path.exists():
        candidate = dict(version='he-client-receipt/1.0.0', request_fingerprint=fingerprint,
                         company_id=company, idempotency_key=key or 'client_' + uuid.uuid4().hex, job_id=None)
        try:
            atomic(receipt_path, candidate, create=True)
        except FileExistsError:
            pass
    receipt = decode(receipt_path.read_bytes())
    if (receipt.get('version') != 'he-client-receipt/1.0.0' or receipt.get('request_fingerprint') != fingerprint
            or receipt.get('company_id') != company or key is not None and key != receipt.get('idempotency_key')):
        raise ServiceError(409, 'CLIENT_RECEIPT_CONFLICT')
    deadline = time.monotonic() + wait_seconds
    base = f'/v1/companies/{company}/he/jobs'
    while time.monotonic() < deadline:
        try:
            if receipt['job_id'] is None:
                state = call(url, 'POST', base, header, body, receipt['idempotency_key'])
                receipt['job_id'] = state['job_id']
                atomic(receipt_path, receipt)
            job_path = base + '/' + receipt['job_id']
            state = call(url, 'GET', job_path, header)
            if state['phase'] == 'waiting_authorization':
                call(url, 'POST', job_path + '/resume', header, {})
            elif state['phase'] == 'completed':
                result = call(url, 'GET', job_path + '/result', header)
                if output_path.exists():
                    if decode(output_path.read_bytes()) != result:
                        raise ServiceError(409, 'CLIENT_OUTPUT_CONFLICT')
                else:
                    try:
                        atomic(output_path, result, create=True)
                    except FileExistsError:
                        if decode(output_path.read_bytes()) != result:
                            raise ServiceError(409, 'CLIENT_OUTPUT_CONFLICT')
                return dict(status='completed', job_id=receipt['job_id'], row_count=result['row_count'])
            elif state['phase'] in ('failed', 'expired'):
                return dict(status=state['phase'], job_id=receipt['job_id'], reason=state['reason'])
        except ServiceError as exc:
            if exc.status != 503:
                raise
        time.sleep(.25)
    return dict(status='pending', job_id=receipt['job_id'], receipt=str(receipt_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('node-url', 'token-file', 'company', 'artifact-id', 'snapshot-id', 'as-of', 'receipt', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--idempotency-key'); parser.add_argument('--wait-seconds', type=float, default=60)
    args = parser.parse_args()
    try:
        result = run(args.node_url, 'Bearer ' + Path(args.token_file).read_text().strip(), args.company,
                     dict(artifact_id=args.artifact_id, snapshot_id=args.snapshot_id, as_of=args.as_of),
                     args.receipt, args.output, key=args.idempotency_key, wait_seconds=args.wait_seconds)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['status'] == 'completed' else 3
    except (ServiceError, OSError, ValueError) as exc:
        print(getattr(exc, 'code', 'CLIENT_LOCAL_ERROR'))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
