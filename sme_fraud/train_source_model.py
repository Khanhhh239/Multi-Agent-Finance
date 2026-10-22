"""Fit a new IF artifact on an attested cache with explicit chronological windows.

No labels, split files, oracle, rule scores or review databases are dependencies.
The existing semantic/version compatibility checks are deliberately unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import uuid

from .shadow_scoring import (guarded, instant, scoring_scope, output_guard,
                             source_checks, selected_matrix, np, joblib, sklearn)
from .feature_contract import digest, require_model, sha, validate_cache
from sklearn.ensemble import IsolationForest

VERSION = 'source-cache-if-v1'
TEMPORAL_VERSION = 'chronological-model-windows-v1'


def training_plan(raw):
    if not isinstance(raw, dict) or set(raw) != {'company_ids', 'source_ref', 'train', 'calibration', 'evaluation'}:
        raise ValueError('Plan requires company_ids, source_ref, train, calibration and evaluation only')
    windows = {}
    normalized = dict(company_ids=raw['company_ids'], source_ref=raw['source_ref'])
    for name in ('train', 'calibration', 'evaluation'):
        window = raw[name]
        if not isinstance(window, dict) or set(window) != {'start_at', 'end_at'}:
            raise ValueError('Each window requires start_at and exclusive end_at only')
        scope, start, end = scoring_scope(dict(company_ids=raw['company_ids'], source_ref=raw['source_ref'], **window))
        normalized['company_ids'] = scope['company_ids']
        normalized[name] = dict(window)
        windows[name] = (start, end)
    if not (windows['train'][1] <= windows['calibration'][0]
            and windows['calibration'][1] <= windows['evaluation'][0]):
        raise ValueError('Train, calibration and evaluation must be chronological and nonoverlapping')
    return normalized, windows


def matrix_fingerprint(rows, matrix):
    identities = [r['transaction_id'] for r in rows]
    return digest([identities, hashlib.sha256(np.ascontiguousarray(matrix, dtype=np.float32).tobytes()).hexdigest()])


def window_summary(rows, matrix, scope):
    return dict(scope=scope, rows=len(rows), company_rows=dict(sorted(Counter(r['company_id'] for r in rows).items())),
                min_posted_at=min(rows, key=lambda r: instant(r['posted_at']))['posted_at'],
                max_posted_at=max(rows, key=lambda r: instant(r['posted_at']))['posted_at'],
                feature_fingerprint=matrix_fingerprint(rows, matrix),
                transaction_ids_sha256=digest(sorted(r['transaction_id'] for r in rows)))


def verify_scoring_window(artifact, scope, start, end):
    """Validate declared fit/calibration provenance for new artifacts, before scoring.

    Legacy artifacts remain technical replays with unverified time provenance.
    This checks a trusted artifact's recorded training windows, not field efficacy.
    """
    proof = artifact.get('temporal_provenance')
    if proof is None:
        if artifact.get('training_runner_version') == VERSION:
            raise ValueError('New source model is missing temporal provenance')
        return False
    if not isinstance(proof, dict) or proof.get('version') != TEMPORAL_VERSION:
        raise ValueError('Unsupported temporal model provenance')
    content = {k: v for k, v in proof.items() if k != 'fingerprint'}
    if proof.get('fingerprint') != digest(content):
        raise ValueError('Temporal model provenance fingerprint mismatch')
    plan, _ = training_plan(proof['plan'])
    evaluation = plan['evaluation']
    if (not set(scope['company_ids']) <= set(plan['company_ids'])
            or not instant(evaluation['start_at']) <= start < end <= instant(evaluation['end_at'])):
        raise ValueError('Scoring scope must be inside the declared evaluation window and companies')
    for name, field in (('train', 'training_feature_fingerprint'), ('calibration', 'calibration_feature_fingerprint')):
        summary = proof[name]
        expected_scope = dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'], **plan[name])
        if (summary.get('scope') != expected_scope or summary.get('feature_fingerprint') != artifact.get(field)
                or type(summary.get('rows')) is not int or summary['rows'] < 2
                or set(summary.get('company_rows', {})) != set(plan['company_ids'])
                or any(type(n) is not int or n <= 0 for n in summary['company_rows'].values())
                or sum(summary['company_rows'].values()) != summary['rows']
                or not instant(plan[name]['start_at']) <= instant(summary['min_posted_at'])
                <= instant(summary['max_posted_at']) < instant(plan[name]['end_at'])):
            raise ValueError('Temporal model provenance does not bind its fitted windows')
    return True


def train_source_model(dataset, output, *, plan, alert_budget=.003,
                       n_estimators=300, max_samples=2048, random_state=20261022, jobs=4):
    dataset, output = (guarded(p) for p in (dataset, output))
    plan, windows = training_plan(plan)
    if (type(alert_budget) not in (int, float) or not np.isfinite(alert_budget) or not 0 < alert_budget < 1):
        raise ValueError('Calibration alert budget must be between 0 and 1')
    if (type(n_estimators) is not int or n_estimators < 1 or type(max_samples) is not int or max_samples < 2
            or type(jobs) is not int or jobs < 1 or type(random_state) is not int
            or not 0 <= random_state <= 2**32 - 1):
        raise ValueError('Invalid IF training parameters')
    output_guard(output, dataset, dataset / 'unused-model-path')
    manifest_bytes = (dataset / 'manifest.json').read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    metadata = json.loads(manifest_bytes)
    if metadata.get('role') == 'holdout':
        raise ValueError('Holdout source role is excluded from model training')
    contract = validate_cache(metadata)
    inputs = source_checks(dataset, metadata)
    # Only train/calibration rows enter matrices used by the estimator. Feature
    # width/coverage/finiteness of the cache are checked without reading labels.
    selection = dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'],
                     start_at=plan['train']['start_at'], end_at=plan['calibration']['end_at'])
    rows, matrix = selected_matrix(dataset, contract['columns'], selection,
                                   windows['train'][0], windows['calibration'][1])
    partitions = {}
    for name in ('train', 'calibration'):
        start, end = windows[name]
        mask = np.array([start <= instant(r['posted_at']) < end for r in rows])
        selected = [r for r, keep in zip(rows, mask) if keep]
        if len(selected) < 2 or set(r['company_id'] for r in selected) != set(plan['company_ids']):
            raise ValueError('Every requested company needs observations in train and calibration')
        partitions[name] = (selected, matrix[mask])
    train_rows, train_x = partitions['train']
    cal_rows, cal_x = partitions['calibration']
    if set(r['transaction_id'] for r in train_rows) & set(r['transaction_id'] for r in cal_rows):
        raise ValueError('Training and calibration IDs overlap')
    params = dict(n_estimators=n_estimators, max_samples=min(max_samples, len(train_rows)),
                  contamination='auto', random_state=random_state, n_jobs=jobs)
    model = IsolationForest(**params).fit(train_x)
    calibration_scores = -np.asarray(model.score_samples(cal_x), dtype=np.float64)
    if calibration_scores.shape != (len(cal_rows),) or not np.isfinite(calibration_scores).all():
        raise ValueError('Estimator returned invalid calibration scores')
    provenance = dict(version=TEMPORAL_VERSION, plan=plan, window_end_exclusive=True,
                      source_manifest_sha256=manifest_sha, input_sha256=inputs,
                      train=window_summary(train_rows, train_x, dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'], **plan['train'])),
                      calibration=window_summary(cal_rows, cal_x, dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'], **plan['calibration'])),
                      evaluation_rows_used_for_fit_or_calibration=0)
    provenance['fingerprint'] = digest(provenance)
    artifact = dict(model=model, dataset_version=metadata['version'], feature_columns=contract['columns'],
                    sklearn_version=sklearn.__version__, feature_contract_fingerprint=contract['fingerprint'],
                    training_feature_fingerprint=provenance['train']['feature_fingerprint'],
                    calibration_feature_fingerprint=provenance['calibration']['feature_fingerprint'],
                    score_direction='higher_is_more_anomalous', training_runner_version=VERSION,
                    temporal_provenance=provenance, model_parameters=params,
                    requested_validation_alert_budget=alert_budget,
                    threshold=float(np.quantile(calibration_scores, 1-alert_budget, method='higher')))
    compatibility = require_model(artifact, metadata, sklearn.__version__)
    eval_scope = dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'], **plan['evaluation'])
    verify_scoring_window(artifact, eval_scope, *windows['evaluation'])
    if sha(dataset / 'manifest.json') != manifest_sha or source_checks(dataset, metadata) != inputs:
        raise ValueError('Training inputs changed during the run')
    report = dict(version=VERSION, dataset=str(dataset), dataset_version=metadata['version'],
                  data_origin=metadata.get('data_origin', 'not_attested'),
                  feature_contract_fingerprint=contract['fingerprint'], sklearn_version=sklearn.__version__,
                  compatibility=compatibility, model_parameters=params, temporal_provenance=provenance,
                  calibration=dict(alert_budget=alert_budget, threshold=artifact['threshold'],
                                   method='higher_quantile_of_unlabelled_calibration_scores'),
                  models_fitted=1, labels_loaded=False, splits_loaded=False, oracle_loaded=False,
                  feature_rebuild=False, existing_model_or_manifest_modified=False,
                  evaluation_rows_scored=0, queue_changed=False, external_notifications=0,
                  holdout_005_loaded_or_scored=False, operational_benefit_measured=False,
                  gates=dict(real_source='awaiting_accepted_real_data', benefit='not_measured'))
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.parent / ('.train-source-' + uuid.uuid4().hex)
    staged.mkdir()
    try:
        model_path = staged / 'isolation_forest.joblib'
        joblib.dump(artifact, model_path)
        restored = joblib.load(io.BytesIO(model_path.read_bytes()))
        require_model(restored, metadata, sklearn.__version__)
        verify_scoring_window(restored, eval_scope, *windows['evaluation'])
        if not np.array_equal(-restored['model'].score_samples(cal_x), calibration_scores):
            raise ValueError('Serialized model calibration replay differs')
        report['model_sha256'] = sha(model_path)
        (staged / 'training_run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if sha(dataset / 'manifest.json') != manifest_sha or source_checks(dataset, metadata) != inputs:
            raise ValueError('Training inputs changed before publication')
        if output.exists():
            raise FileExistsError('Output appeared during training; refusing to replace it')
        staged.rename(output)
    finally:
        if staged.exists():
            for name in ('isolation_forest.joblib', 'training_run.json'):
                (staged / name).unlink(missing_ok=True)
            staged.rmdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--alert-budget', type=float, default=.003)
    parser.add_argument('--n-estimators', type=int, default=300)
    parser.add_argument('--max-samples', type=int, default=2048)
    parser.add_argument('--random-state', type=int, default=20261022)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    plan = json.loads(guarded(args.plan).read_text(encoding='utf-8'))
    report = train_source_model(args.dataset, args.output, plan=plan, alert_budget=args.alert_budget,
                                n_estimators=args.n_estimators, max_samples=args.max_samples,
                                random_state=args.random_state, jobs=args.jobs)
    print(json.dumps(dict(output=str(args.output), model_sha256=report['model_sha256'],
                         dataset_version=report['dataset_version'], compatible=report['compatibility']['compatible'],
                         train_rows=report['temporal_provenance']['train']['rows'],
                         calibration_rows=report['temporal_provenance']['calibration']['rows'])))


if __name__ == '__main__':
    main()
