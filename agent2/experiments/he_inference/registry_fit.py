"""Opt-in enterprise offline fit into the existing immutable MethodStore.

This experimental method is deliberately absent from the web ML catalog.
No export or scoring function imports or calls run_fit_job.
"""
from datetime import timedelta
import io
from pathlib import Path
import re

import joblib
import numpy as np
from finance_input.json_io import loads

from sme_fraud.import_files import canonical, digest
from sme_fraud.method_adapters import ARTIFACT_VERSION, LocalArtifact, _frame, _scope, _versions
from sme_fraud.method_jobs import _window
from sme_fraud.method_preprocess import VERSION as PREPROCESS, fit_preprocess, transform_frame
from sme_fraud.method_store import require_fit
from sme_fraud.snapshot_features import build_from_snapshot, feature_contract, utc
from sme_fraud.unsupervised_statistics import ShrunkMahalanobis
from .protocol import HEUnavailable, MAX_WEIGHT, PAIRS, require

METHOD = 'he_mahalanobis_2d'
REGISTRY_VERSION = 'experimental-he-registry/1.0.0'
CONFIG_VERSION = 'experimental-he-fit-config/1.0.0'
PERIODS = ('history_start', 'history_end', 'reference_start', 'reference_end', 'evaluation_start')


def implementation_hash():
    import sme_fraud.method_jobs as jobs
    import sme_fraud.snapshot_features as features
    return digest(canonical({name: digest(Path(path).read_bytes()) for name, path in
        [('registry_fit', __file__), ('window_job', jobs.__file__), ('snapshot_replay', features.__file__)]}))


def validate_config(config):
    fields = {'version', 'snapshot_id', 'method_id', 'missing_policy', 'minimum_history',
              'profile_id', 'evaluation_mode', 'selected_columns', *PERIODS}
    require(isinstance(config, dict) and set(config) == fields, 'HE_FIT_CONFIG')
    require(config['version'] == CONFIG_VERSION and config['method_id'] == METHOD
            and config['missing_policy'] == 'strict', 'HE_FIT_PROFILE')
    require(type(config['minimum_history']) is int and config['minimum_history'] >= 20
            and isinstance(config['profile_id'], str) and bool(config['profile_id'].strip()), 'HE_FIT_HISTORY')
    require(config['evaluation_mode'] in ('backtest', 'prospective'), 'HE_FIT_PERIOD')
    require(isinstance(config['snapshot_id'], str) and re.fullmatch(r'snp_[a-f0-9]{32}', config['snapshot_id']), 'HE_FIT_SNAPSHOT')
    columns = config['selected_columns']
    require(isinstance(columns, list) and len(columns) == 2 and all(isinstance(c, str) for c in columns)
            and len(set(columns)) == 2 and all(c in feature_contract()['columns'] for c in columns), 'HE_FIT_COLUMNS')
    result = dict(config, selected_columns=list(columns))
    for key in PERIODS:
        require(isinstance(config[key], str), 'HE_FIT_PERIOD')
        result[key] = utc(config[key]).isoformat()
    a, b, c, d, e = [utc(result[k]) for k in PERIODS]
    require(a < b <= c < d <= e, 'HE_FIT_PERIOD')
    return result


def run_fit_job(snapshots, models, authorizer, authorization, company, config, key):
    scope = authorizer.authorize(authorization, company)
    require_fit(scope)
    check = lambda: authorizer.authorize(authorization, company)
    config = validate_config(config)
    snapshot = snapshots.get_snapshot(scope, config['snapshot_id'], check)
    binding = {k: snapshot[k] for k in ('snapshot_id', 'tenant_id', 'company_id', 'checksum', 'data_checksum', 'contract_version')}
    request = dict(version=REGISTRY_VERSION, config=config, snapshot=binding,
                   feature_contract=feature_contract(), versions=_versions(), job_implementation_sha256=implementation_hash())
    job, claimed = models.begin_fit(scope, request, key, check)
    if not claimed:
        artifact = models.get_artifact(scope, job['artifact_id'], check) if job['status'] == 'succeeded' else None
        return dict(job=job, manifest=loads(artifact.manifest) if artifact else None, reused=True)
    try:
        if config['evaluation_mode'] == 'prospective':
            require(utc(job['created_at']) < utc(config['evaluation_start']), 'HE_FIT_PERIOD_STARTED')
        history = build_from_snapshot(snapshots, scope, config['snapshot_id'],
                    (utc(config['history_end']) - timedelta(microseconds=1)).isoformat(), check)
        reference = build_from_snapshot(snapshots, scope, config['snapshot_id'],
                    (utc(config['reference_end']) - timedelta(microseconds=1)).isoformat(), check)
        history = _window(history, config['history_start'], config['history_end'])
        reference = _window(reference, config['reference_start'], config['reference_end'])
        _frame(history, scope); _frame(reference, scope)
        require(len(history['rows']) >= config['minimum_history'] and bool(reference['rows']), 'HE_FIT_HISTORY')
        history_ids = {r['record_id'] for r in history['rows']}
        reference_ids = {r['record_id'] for r in reference['rows']}
        require(not history_ids & reference_ids, 'HE_FIT_IDENTITY_OVERLAP')
        train_end = max(max(utc(r['event_at']), utc(r['as_of'])) for r in history['rows'])
        reference_start = min(min(utc(r['event_at']), utc(r['as_of'])) for r in reference['rows'])
        reference_end = max(max(utc(r['event_at']), utc(r['as_of'])) for r in reference['rows'])
        require(train_end < reference_start <= reference_end < utc(config['evaluation_start']), 'HE_FIT_PERIOD')
        preprocess = fit_preprocess(history, config['selected_columns'], 'strict')
        model = ShrunkMahalanobis().fit(transform_frame(history, preprocess))
        weights = [float(model.cov_.precision_[i, j]) * (1 if i == j else 2) for i, j in PAIRS]
        require(all(np.isfinite(w) and abs(w) <= MAX_WEIGHT for w in weights), 'MODEL_OUT_OF_DOMAIN')
        scores = np.asarray(model.score(transform_frame(reference, preprocess)), dtype=float)
        require(scores.shape == (len(reference['rows']),) and np.isfinite(scores).all(), 'HE_REFERENCE_INVALID')
        scores = sorted(scores.tolist())
        stream = io.BytesIO(); joblib.dump((model, scores), stream); payload = stream.getvalue()
        context = dict(job_id=job['job_id'], request_hash=job['request_hash'], actor_id=scope.actor_id,
                       created_at=models._now(), job_started_at=job['created_at'], config=config,
                       job_implementation_sha256=implementation_hash(), evaluation_mode=config['evaluation_mode'],
                       evaluation_start=config['evaluation_start'])
        tenant, company = _scope(scope)
        manifest = dict(version=ARTIFACT_VERSION, he_registry_version=REGISTRY_VERSION,
            tenant_id=tenant, company_id=company, method_id=METHOD, profile_id=config['profile_id'],
            minimum_history=config['minimum_history'], selected_columns=config['selected_columns'],
            feature_contract=feature_contract(), feature_contract_fingerprint=feature_contract()['fingerprint'],
            preprocess=preprocess, preprocess_sha256=digest(canonical(preprocess)), preprocess_version=PREPROCESS,
            model_version='mdl_' + digest(payload), payload_sha256=digest(payload), versions=_versions(),
            fit_context=context, score_kind='squared_mahalanobis', higher_is_more_unusual=True,
            train_end=train_end.isoformat(), reference_start=reference_start.isoformat(), reference_end=reference_end.isoformat(),
            history_hash=digest(canonical(history)), reference_data_hash=digest(canonical(reference)),
            history_binding=binding, reference_binding=binding, history_rows=len(history['rows']), reference_rows=len(reference['rows']),
            reference_version=digest(canonical(scores)),
            fitted_identity_hashes=sorted(digest(canonical(identity)) for identity in history_ids | reference_ids))
        encoded = canonical(manifest)
        artifact = LocalArtifact('mth_' + digest(encoded), encoded, payload)
        finished = models.publish(scope, job['job_id'], artifact, check)
        return dict(job=finished, manifest=manifest, reused=False)
    except Exception as exc:
        # Failed jobs remain auditable, and authorization revocation propagates.
        from sme_fraud.auth import AuthError
        from sme_fraud.import_files import ImportFailure
        try:
            models.fail_job(scope, job['job_id'], getattr(exc, 'code', 'HE_FIT_FAILED'), check)
        except (AuthError, ImportFailure):
            pass  # Revocation cannot authorize even a failed-job write.
        raise
