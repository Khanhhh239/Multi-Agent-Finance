"""Persist fit artifacts, then export from a fresh read-only registry connection."""
import argparse
from contextlib import ExitStack, closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import io
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import joblib
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical, digest
from sme_fraud.method_store import MethodStore
from sme_fraud.snapshots import SnapshotStore
from .demo import worker_process
from .protocol import ABS_TOLERANCE, REL_TOLERANCE, public_hex
from .registry_export import export_snapshot
from .registry_fit import run_fit_job, CONFIG_VERSION, METHOD

ROOT = Path(__file__).resolve().parents[2]
VN = timezone(timedelta(hours=7))


def source_for(company, section):
    # Reuse the valid R1 input shape, not its labels or generator-only columns.
    sys.path.insert(0, str(ROOT / 'scripts'))
    from demo_method_scores import canonical_source
    source = canonical_source()
    tx_template = source['transactions'][0]; alloc_template = source['payment_allocations'][0]
    source['transactions'] = []; source['payment_allocations'] = []
    groups = [('H', 32, datetime(2026, 9, 2, 8, tzinfo=VN)), ('R', 8, datetime(2026, 9, 15, 8, tzinfo=VN))] if section == 'training' else [('T', 5, datetime(2026, 10, 1, 8, tzinfo=VN))]
    factor = 1 if company == 'C001' else 3
    for prefix, count, origin in groups:
        for i in range(count):
            at = (origin + timedelta(hours=6 * i)).isoformat()
            amount = (700003 + i * 17239 + (i % 5) * 47003) * factor
            if prefix == 'T':
                amount = (950003 + i * 29039) * factor
            tx = deepcopy(tx_template); identity = prefix + str(i)
            tx.update(record_id=identity, effective_at=at, observed_at=at, amount_vnd=amount,
                      description='Synthetic HE registry demo ' + identity,
                      accounting_lines=[dict(account='331', debit_vnd=amount, credit_vnd=0),
                                        dict(account='112', debit_vnd=0, credit_vnd=amount)])
            tx['source']['record_id'] = identity
            alloc = deepcopy(alloc_template)
            alloc.update(record_id='A_' + identity, effective_at=at, observed_at=at, amount_vnd=amount,
                         transaction_ref=dict(record_id=identity, revision=1))
            alloc['source']['record_id'] = 'A_' + identity
            source['transactions'].append(tx); source['payment_allocations'].append(alloc)
    for table, rows in source.items():
        if isinstance(rows, list):
            for row in rows:
                row['company_id'] = company
                if table == 'companies':
                    row['record_id'] = company; row['source']['record_id'] = company
    return source


def commit(store, scope, source, key):
    draft = store.upload(scope, canonical(source), 'he-demo.json', key)
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise AssertionError(preview['errors'])
    body = {k: preview[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
    body.update(expected_revision=1, acknowledge=True)
    return store.commit(scope, draft['import_id'], body, key + '-save')['snapshot']['snapshot_id']


def setup_demo(folder):
    folder = Path(folder)
    fit_token = secrets.token_urlsafe(32); read_token = secrets.token_urlsafe(32)
    principals = []
    for actor, token, fit in [('fit-worker', fit_token, True), ('read-worker', read_token, False)]:
        principals.append(dict(actor_id=actor, tenant_id='demo', token_sha256=digest(token.encode()), status='active',
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), memberships=[dict(
                company_id=c, role='director' if fit else 'accountant', status='active',
                permissions=['data.import', 'model.fit'] if fit else ['data.import']) for c in ('C001', 'C002')]))
    policy = folder / 'auth.json'; policy.write_bytes(canonical(dict(policy_version='1.0.0', principals=principals)))
    auth = FileAuthorizer(policy)
    snapshot_db = folder / 'snapshots.sqlite3'; model_db = folder / 'models.sqlite3'
    snapshots = SnapshotStore(snapshot_db); models = MethodStore(model_db)
    artifacts = {}; queries = {}; training = {}; configs = {}
    for company in ('C001', 'C002'):
        scope = auth.authorize('Bearer ' + fit_token, company)
        training[company] = commit(snapshots, scope, source_for(company, 'training'), company + '-training')
        queries[company] = commit(snapshots, scope, source_for(company, 'query'), company + '-query')
        config = dict(version=CONFIG_VERSION, snapshot_id=training[company], method_id=METHOD,
                      missing_policy='strict', minimum_history=20, profile_id='he-registry-synthetic-only', evaluation_mode='backtest',
                      selected_columns=['log_abs_amount', 'event_hour_sin'],
                      history_start='2026-09-02T00:00:00+07:00', history_end='2026-09-12T00:00:00+07:00',
                      reference_start='2026-09-15T00:00:00+07:00', reference_end='2026-09-20T00:00:00+07:00',
                      evaluation_start='2026-10-01T00:00:00+07:00')
        configs[company] = config
        fit = run_fit_job(snapshots, models, auth, 'Bearer ' + fit_token, company, config, company + '-offline-fit')
        artifacts[company] = fit['job']['artifact_id']
    return dict(auth=auth, fit_header='Bearer ' + fit_token, header='Bearer ' + read_token,
                model_db=model_db, snapshot_db=snapshot_db, artifacts=artifacts, queries=queries,
                training=training, configs=configs, snapshots=snapshots, models=models, policy=policy)


def database_dump(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        return '\n'.join(conn.iterdump())


def run(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='he-registry-demo-') as temporary:
        root = Path(temporary); env = setup_demo(root)
        before = {name: database_dump(env[name]) for name in ('snapshot_db', 'model_db')}
        signer = Ed25519PrivateKey.generate()
        for company in ('C001', 'C002'):
            scope = env['auth'].authorize(env['header'], company)
            artifact = MethodStore(env['model_db'], read_only=True).get_artifact(scope, env['artifacts'][company])
            model, _ = joblib.load(io.BytesIO(artifact.payload))
            # Fit/publish are forbidden after offline preparation is complete.
            with ExitStack() as stack:
                for target in ('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',
                               'sme_fraud.ml_estimators.CompanyEstimator.fit',
                               'sme_fraud.method_store.MethodStore.begin_fit', 'sme_fraud.method_store.MethodStore.publish'):
                    stack.enter_context(patch(target, side_effect=AssertionError('No fit/write during export')))
                export = export_snapshot(env['model_db'], env['snapshot_db'], env['auth'], env['header'], company,
                    env['artifacts'][company], env['queries'][company], '2026-10-03T00:00:00+07:00', public_hex(signer))
                assert export.ready, export.local_result()
                package = export.cloud_package()
                cloud_json = canonical(package).decode()
                for private in (env['artifacts'][company], env['queries'][company], export.receipt['feature_contract_fingerprint']):
                    assert private not in cloud_json
                response, code, seconds = worker_process(package['request'], package['policy'], signer, root / ('cloud-' + company))
                assert code == 0, response
                result = export.open(response)
            assert result['row_count'] == 5 and all(r['available'] for r in result['rows'])
            # Original scores use exactly the same R1 snapshot feature order.
            from sme_fraud.snapshot_features import build_from_snapshot
            from .registry_export import ReadOnlySnapshots
            frame = build_from_snapshot(ReadOnlySnapshots(env['snapshot_db']), scope, env['queries'][company], '2026-10-03T00:00:00+07:00')
            values = [[v[frame['contract']['columns'].index(c)] for c in result['receipt']['selected_columns']] for v in frame['features']]
            clear = model.score(np.asarray(values))
            encrypted = np.asarray([r['raw_score'] for r in result['rows']])
            np.testing.assert_allclose(clear, encrypted, atol=ABS_TOLERANCE, rtol=REL_TOLERANCE)
            (output / (company + '-local-result.json')).write_bytes(canonical(result))
            results.append(dict(company_id=company, rows=5, registry_artifact_id=env['artifacts'][company],
                                feature_count=33, model_columns=2, max_abs_error=float(np.max(np.abs(clear - encrypted))),
                                worker_seconds=seconds, worker=response['payload']['worker']))
        assert before == {name: database_dump(env[name]) for name in before}
    summary = dict(status='passed', companies=results, data='synthetic_only', fit_during_export=0,
                   registry_writes_during_export=0, snapshot_writes_during_export=0, actual_cloud_deployment=False)
    (output / 'summary.json').write_bytes(canonical(summary))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    run(parser.parse_args().output_dir)
