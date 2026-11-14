"""Authorized enterprise-side registry -> snapshot features -> HE envelope.

Only encrypted model coefficients cross the worker boundary. No fit, migration,
latest selection, pickle upload, or plaintext inference fallback exists here.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import io
import pickle
import secrets
import sqlite3
from pathlib import Path

import joblib
import numpy as np
from finance_input.json_io import loads

from sme_fraud.import_files import ImportFailure, canonical, digest, fail
from sme_fraud.method_adapters import ARTIFACT_VERSION, _frame, _scope, _versions
from sme_fraud.method_preprocess import VERSION as PREPROCESS, row_values, validate_preprocess
from sme_fraud.method_store import MethodStore
from sme_fraud.snapshot_features import build_from_snapshot, feature_contract, utc
from sme_fraud.snapshots import SnapshotStore, APPLICATION_ID
from .enterprise import EnterpriseSession
from .protocol import HEUnavailable, MAX_NORMALIZED, MAX_ROWS, require, canonical as wire_canonical
from .registry_fit import METHOD, REGISTRY_VERSION, implementation_hash, validate_config

VERSION = 'he-registry-export/1.0.0'


class ReadOnlySnapshots(SnapshotStore):
    """Use the existing checksum/scope reader without DDL or write transactions."""
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.clock = lambda: datetime.now(timezone.utc)
        if not self.path.is_file():
            fail(404, 'SNAPSHOT_NOT_FOUND', 'Chưa có kho snapshot.', 'Dùng snapshot đã lưu; không tạo kho khi xuất model.')

    def _connect(self):
        conn = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        return conn

    @contextmanager
    def _transaction(self, scope, recheck=None):
        self._scope(scope)
        conn = self._connect()
        try:
            conn.execute('BEGIN')
            if recheck is not None and recheck() != scope:
                fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Chạy lại theo quyền hiện hành.')
            if conn.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or conn.execute('PRAGMA user_version').fetchone()[0] != 1:
                fail(503, 'STORAGE_VERSION', 'Kho snapshot không tương thích.', 'Chọn kho snapshot hiện hành.')
            yield conn
            if recheck is not None and recheck() != scope:
                fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Chạy lại theo quyền hiện hành.')
            conn.commit()
        finally:
            conn.close()


def _load_model(model_db, scope, artifact_id, check, *, metadata_only=False):
    """All format/compatibility gates run before trusted-local joblib.load."""
    try:
        store = MethodStore(model_db, read_only=True)
        artifact = store.get_artifact(scope, artifact_id, check)
    except ImportFailure as exc:
        reason = {'MODEL_ARTIFACT_NOT_FOUND': 'artifact_missing', 'MODEL_ARTIFACT_INTEGRITY': 'artifact_invalid',
                  'MODEL_STORAGE_VERSION': 'model_store_unavailable'}.get(exc.code)
        if reason:
            raise HEUnavailable(reason) from exc
        raise
    m = loads(artifact.manifest)
    require(artifact.artifact_id == artifact_id == 'mth_' + digest(artifact.manifest)
            and (m.get('tenant_id'), m.get('company_id')) == _scope(scope), 'artifact_invalid')
    require(m.get('method_id') == METHOD, 'he_adapter_unsupported')
    require(m.get('version') == ARTIFACT_VERSION and m.get('he_registry_version') == REGISTRY_VERSION, 'artifact_incompatible')
    require(m.get('feature_contract') == feature_contract()
            and m.get('feature_contract_fingerprint') == feature_contract()['fingerprint']
            and m.get('versions') == _versions(), 'artifact_incompatible')
    require(m.get('payload_sha256') == digest(artifact.payload)
            and m.get('model_version') == 'mdl_' + digest(artifact.payload)
            and len(artifact.payload) <= 16 * 1024 * 1024, 'artifact_invalid')
    pre = m['preprocess']
    validate_preprocess(dict(contract=feature_contract()), pre)
    require(m.get('preprocess_version') == PREPROCESS and pre['policy'] == 'strict'
            and m.get('selected_columns') == pre['selected_columns'] == pre['output_columns']
            and len(pre['output_columns']) == 2 and m.get('preprocess_sha256') == digest(canonical(pre)), 'artifact_incompatible')
    context = m['fit_context']
    config = validate_config(context['config'])
    require(config['selected_columns'] == m['selected_columns'] and config['minimum_history'] == m['minimum_history']
            and context['evaluation_start'] == config['evaluation_start']
            and context['evaluation_mode'] == config['evaluation_mode']
            and context['job_implementation_sha256'] == implementation_hash(), 'artifact_incompatible')
    require(utc(m['train_end']) < utc(m['reference_start']) <= utc(m['reference_end']) < utc(config['evaluation_start'])
            and m['history_rows'] >= config['minimum_history'] and m['reference_rows'] > 0
            and isinstance(m['fitted_identity_hashes'], list), 'artifact_invalid')
    require(context['evaluation_mode'] != 'prospective'
            or utc(context['created_at']) < utc(context['evaluation_start']), 'artifact_from_future')
    require(m['score_kind'] == 'squared_mahalanobis' and m['higher_is_more_unusual'] is True, 'artifact_incompatible')
    # Reading fit provenance must not require the permission to launch a fit.
    # Reuse the store's scoped/hash-checked internal read transaction, not the
    # fit-manager get_job API (which intentionally requires model.fit).
    try:
        with store._transaction(scope, check) as conn:
            job = store._job(conn, scope, context['job_id'])
            request = loads(job['request_json'])
            require(job['status'] == 'succeeded' and job['artifact_id'] == artifact_id
                    and job['request_hash'] == context['request_hash']
                    and request['version'] == REGISTRY_VERSION
                    and request['config'] == config and request['feature_contract'] == m['feature_contract']
                    and request['versions'] == m['versions']
                    and request['snapshot'] == m['history_binding'] == m['reference_binding']
                    and request['job_implementation_sha256'] == context['job_implementation_sha256'], 'artifact_invalid')
    except ImportFailure as exc:
        if exc.code in ('FIT_JOB_NOT_FOUND', 'MODEL_ARTIFACT_INTEGRITY'):
            raise HEUnavailable('artifact_invalid') from exc
        raise
    check()
    if metadata_only:
        return artifact, m, None
    # Only a scope/hash/version-checked immutable local registry entry reaches
    # this loader. It is not a safe parser for arbitrary uploaded pickle files.
    model, reference = joblib.load(io.BytesIO(artifact.payload))
    require(isinstance(reference, list) and len(reference) == m['reference_rows']
            and reference == sorted(reference) and np.isfinite(reference).all()
            and digest(canonical(reference)) == m['reference_version'], 'artifact_invalid')
    return artifact, m, model


class RegistryExport:
    def __init__(self, rows, receipt, check, *, session=None, packet=None, policy=None, positions=()):
        self.rows = rows
        self.receipt = receipt
        self._check = check
        self._session = session
        self._packet = packet
        self._policy = policy
        self._positions = list(positions)

    @property
    def ready(self):
        return self._packet is not None

    def cloud_package(self):
        self._check()
        require(self.ready, 'HE_EXPORT_UNAVAILABLE')
        return dict(request=deepcopy(self._packet), policy=deepcopy(self._policy))

    def local_result(self):
        self._check()
        rows = deepcopy(self.rows)
        return dict(version=VERSION, status='partial' if any(r['status'] == 'unavailable' for r in rows)
                    and any(r['status'] == 'available' for r in rows) else
                    'available' if rows and all(r['status'] == 'available' for r in rows) else
                    'pending' if self.ready and any(r['status'] == 'pending' for r in rows) else 'unavailable',
                    rows=rows, row_count=len(rows), receipt=deepcopy(self.receipt))

    def open(self, response):
        self._check()
        require(self.ready, 'HE_EXPORT_UNAVAILABLE')
        scores = self._session.open(response, self._packet['payload']['nonce'])
        self._check()
        require(len(scores) == len(self._positions), 'RESULT_LAYOUT')
        for index, score in zip(self._positions, scores):
            self.rows[index].update(status='available', available=True, raw_score=float(score), reason=None)
        return self.local_result()


def export_snapshot(model_db, snapshot_db, authorizer, authorization, company,
                    artifact_id, snapshot_id, as_of, worker_verify_key):
    # Authorization precedes opening either database, even for malformed IDs.
    scope = authorizer.authorize(authorization, company)
    tenant, company = _scope(scope)

    def check():
        if authorizer.authorize(authorization, company) != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi trong lúc xuất/nhận model.', 'Chạy lại theo quyền hiện hành.')
        return scope

    check()
    snapshots = ReadOnlySnapshots(snapshot_db)
    frame = build_from_snapshot(snapshots, scope, snapshot_id, as_of, check)
    _frame(frame, scope)
    require(len(frame['rows']) <= 200, 'HE_EXPORT_ROW_LIMIT')
    rows = [dict(row_index=i, record_id=r['record_id'], revision=r['revision'],
                 status='unavailable', available=False, raw_score=None, score_kind='squared_mahalanobis',
                 reason='artifact_missing', missing_features=[]) for i, r in enumerate(frame['rows'])]
    receipt = dict(version=VERSION, tenant_id=tenant, company_id=company, artifact_id=artifact_id,
                   snapshot=frame['snapshot'], as_of=frame['as_of'],
                   feature_contract_fingerprint=frame['contract']['fingerprint'])

    def unavailable(code):
        for row in rows:
            row['reason'] = code
        check()
        return RegistryExport(rows, receipt, check)

    try:
        artifact, manifest, model = _load_model(model_db, scope, artifact_id, check)
    except HEUnavailable as exc:
        return unavailable(exc.code)
    except (ValueError, KeyError, TypeError, AttributeError, EOFError, ImportError, OSError, sqlite3.Error, pickle.UnpicklingError):
        return unavailable('artifact_invalid')
    receipt.update(model_version=manifest['model_version'], method_id=METHOD,
                   selected_columns=manifest['selected_columns'], preprocess_sha256=manifest['preprocess_sha256'],
                   evaluation_mode=manifest['fit_context']['evaluation_mode'], reference_version=manifest['reference_version'],
                   fit_job_id=manifest['fit_context']['job_id'], history_binding=manifest['history_binding'],
                   reference_end=manifest['reference_end'])
    check()
    values = []; positions = []; events = []
    # No inference fit: from_fitted_model only validates arrays and makes keys.
    try:
        session = EnterpriseSession.from_fitted_model(tenant, company, model,
                    evaluation_start=int(utc(manifest['fit_context']['evaluation_start']).timestamp()))
    except HEUnavailable as exc:
        return unavailable(exc.code)
    for index, (row, features) in enumerate(zip(frame['rows'], frame['features'])):
        point = min(utc(row['event_at']), utc(row['as_of']))
        prepared, missing, reason = row_values(frame, features, manifest['preprocess'])
        if utc(manifest['reference_end']) >= point:
            reason = 'artifact_from_future'
        elif digest(canonical(row['record_id'])) in manifest['fitted_identity_hashes']:
            reason = 'artifact_training_overlap'
        elif point < utc(manifest['fit_context']['evaluation_start']):
            reason = 'before_evaluation_period'
        elif manifest['fit_context']['evaluation_mode'] == 'prospective' and utc(manifest['fit_context']['created_at']) >= point:
            reason = 'artifact_not_yet_created'
        if reason is None:
            z = (np.asarray(prepared, dtype=float) - model.mean_) / model.std_ - model.cov_.location_
            if not np.isfinite(z).all() or np.max(np.abs(z)) > MAX_NORMALIZED:
                reason = 'input_out_of_domain'
        rows[index].update(reason=reason, missing_features=missing)
        if reason is None:
            rows[index]['status'] = 'pending'
            values.append(prepared); positions.append(index); events.append(int(point.timestamp()))
    if len(values) > MAX_ROWS:
        return unavailable('he_batch_limit')
    if not values:
        check()
        return RegistryExport(rows, receipt, check)
    # Hide the low-entropy/guessable artifact/feature hashes from the worker.
    # Random salt stays local; the opaque model_id binds exact private origin.
    origin = dict(artifact_id=artifact.artifact_id, model_version=manifest['model_version'],
                  feature_contract=frame['contract'], preprocess=manifest['preprocess'])
    salt = secrets.token_bytes(32)
    session.binding['model_id'] = 'mdl_' + digest(salt + canonical(origin))
    receipt.update(opaque_model_id=session.binding['model_id'],
                   origin_salt_hex=salt.hex(), exporter_sha256=digest(Path(__file__).read_bytes()))
    check()
    packet, policy = session.prepare(values, worker_verify_key, event_times=events)
    check()
    for index, handle in zip(positions, packet['payload']['row_handles']):
        rows[index]['row_handle'] = handle
    receipt['request_sha256'] = digest(wire_canonical(packet))
    return RegistryExport(rows, receipt, check, session=session, packet=packet, policy=policy, positions=positions)
