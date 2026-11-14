"""Submit/poll/result/restart recovery demo for durable enterprise HE jobs."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time

from .protocol import canonical
from .services_demo import Pair, request
from .registry_demo import database_dump


def submit(pair, company, key, body=None):
    return request(pair.node_port, f'/v1/companies/{company}/he/jobs', body or pair.body(company),
                   headers={'Authorization': pair.env['header'], 'Idempotency-Key': key})


def state(pair, company, job_id, result=False):
    return request(pair.node_port, f'/v1/companies/{company}/he/jobs/{job_id}' + ('/result' if result else ''),
                   headers={'Authorization': pair.env['header']})


def wait(pair, company, job_id, phases=('completed',), seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status, value = state(pair, company, job_id)
        if status != 200:
            raise AssertionError(value)
        if value['phase'] in phases:
            return value
        if value['phase'] in ('failed', 'expired'):
            raise AssertionError(value)
        time.sleep(.1)
    raise AssertionError('Job did not reach expected state')


def worker_count(pair):
    with closing(sqlite3.connect(pair.worker_root / 'state/jobs.sqlite3')) as conn:
        return conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]


def run(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(dict(check=name, passed=True))
    with tempfile.TemporaryDirectory(prefix='he-job-demo-') as folder:
        pair = Pair(folder)
        try:
            before = {k: database_dump(pair.env[k]) for k in ('model_db', 'snapshot_db')}
            pair.start()
            for company in ('C001', 'C002'):
                status, job = submit(pair, company, 'lifecycle-' + company)
                check(company + ': submit returns trackable stable job ID', status in (200, 202) and job['job_id'].startswith('herun_'))
                done = wait(pair, company, job['job_id'])
                status, result = state(pair, company, job['job_id'], True)
                check(company + ': fetch returns all five decrypted results', status == 200 and result['row_count'] == 5 and all(r['available'] for r in result['rows']))
                phases = {event['phase'] for event in done['events']}
                check(company + ': persisted history contains send/receive/decrypt', {'queued', 'ready', 'waiting_worker', 'received', 'decrypting', 'completed'} <= phases)
                count = worker_count(pair)
                _, repeated = submit(pair, company, 'lifecycle-' + company)
                check(company + ': repeated click reuses same job without second worker run', repeated['job_id'] == job['job_id'] and worker_count(pair) == count)
                (output / (company + '-status.json')).write_bytes(canonical(done))
                (output / (company + '-result.json')).write_bytes(canonical(result))
            pair._stop(pair.worker_process)
            _, interrupted = submit(pair, 'C001', 'recover-node-and-network')
            paused = wait(pair, 'C001', interrupted['job_id'], ('retryable',))
            check('network outage is visible and recoverable', paused['phase'] == 'retryable')
            # Node owns the encrypted checkpoint; the worker never sees this DB.
            db = pair.enterprise / 'state/jobs.sqlite3'
            raw = db.read_bytes()
            check('node state contains neither raw token nor private-context JSON', pair.env['header'].encode() not in raw and b'"private_context"' not in raw)
            pair.restart_worker(); pair.restart_node()
            status, restarted = state(pair, 'C001', interrupted['job_id'])
            check('node restart preserves job but requires fresh owner authorization', status == 200 and restarted['phase'] == 'waiting_authorization')
            count = worker_count(pair)
            _, resumed = submit(pair, 'C001', 'recover-node-and-network')
            check('submit retry after node restart keeps the original job ID', resumed['job_id'] == interrupted['job_id'])
            done = wait(pair, 'C001', resumed['job_id'])
            status, recovered = state(pair, 'C001', resumed['job_id'], True)
            check('saved HE key decrypts result after node restart', status == 200 and all(r['available'] for r in recovered['rows']))
            check('recovery computes exactly one worker job', worker_count(pair) == count + 1)
            pair.restart_node()
            status, persisted = state(pair, 'C001', resumed['job_id'], True)
            check('completed plaintext result remains encrypted locally and retrievable', status == 200 and persisted == recovered)
            check('domain snapshot/model stores never changed', before == {k: database_dump(pair.env[k]) for k in before})
            (output / 'recovered-status.json').write_bytes(canonical(done))
            (output / 'recovered-result.json').write_bytes(canonical(recovered))
            summary = dict(status='passed', data='synthetic_only', checks=checks, count=len(checks),
                actual_remote_cloud_deployment=False, live_portal_changed=False,
                checkpoint_storage='enterprise AES-256-GCM; wrapping key file outside DB',
                bearer_credentials_persisted=False)
            (output / 'summary.json').write_bytes(canonical(summary))
        finally:
            pair.close()
    print(json.dumps(dict(status='passed', checks=len(checks), output=str(output))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    run(parser.parse_args().output_dir)
