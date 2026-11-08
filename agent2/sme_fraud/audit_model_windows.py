"""Audit chronological model partitions against actual source rows without fitting/scoring."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import uuid

from .feature_contract import digest, require_model, sha, validate_cache
from .shadow_scoring import (guarded, instant, output_guard, selected_matrix,
                             source_checks, joblib, sklearn)
from .train_source_model import training_plan, verify_scoring_window, window_summary

VERSION = 'model-time-partition-audit-v1'
PARTITIONS = ('train', 'calibration', 'evaluation')


def partition_rows(rows, plan):
    """Assign each stable ID once using UTC instants and half-open intervals."""
    plan, windows = training_plan(plan)
    seen, memberships = set(), []
    for row in rows:
        tid = row['transaction_id']
        if not tid or tid in seen:
            raise ValueError('Duplicate or empty transaction ID in temporal partition')
        seen.add(tid)
        when = instant(row['posted_at'])
        matches = [name for name, (start, end) in windows.items() if start <= when < end]
        if len(matches) > 1:
            raise ValueError('An observation belongs to overlapping windows')
        partition = ('outside_company_scope' if row['company_id'] not in plan['company_ids'] else
                     matches[0] if matches else 'outside_time_windows')
        memberships.append(dict(transaction_id=tid, company_id=row['company_id'],
                                posted_at=row['posted_at'], posted_at_utc=when.isoformat(), partition=partition))
    return sorted(memberships, key=lambda r: (r['posted_at_utc'], r['company_id'], r['transaction_id']))


def audit_model_windows(dataset, model_path, output, *, model_sha256):
    dataset, model_path, output = (guarded(p) for p in (dataset, model_path, output))
    output_guard(output, dataset, model_path)
    manifest_bytes = (dataset/'manifest.json').read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    metadata = json.loads(manifest_bytes)
    if metadata.get('role') == 'holdout':
        raise ValueError('Holdout sources are excluded from this temporal audit')
    contract = validate_cache(metadata)
    model_bytes = model_path.read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != model_sha256:
        raise ValueError('Model checksum differs from the selected frozen artifact')
    artifact = joblib.load(io.BytesIO(model_bytes))
    require_model(artifact, metadata, sklearn.__version__)
    proof = artifact.get('temporal_provenance')
    if not isinstance(proof, dict):
        raise ValueError('Temporal audit requires recorded training provenance')
    plan, windows = training_plan(proof['plan'])
    scope = dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'], **plan['evaluation'])
    if not verify_scoring_window(artifact, scope, *windows['evaluation']):
        raise ValueError('Temporal audit requires verified window declarations')
    inputs = source_checks(dataset, metadata)
    if proof.get('source_manifest_sha256') != manifest_sha or proof.get('input_sha256') != inputs:
        raise ValueError('Audit source differs from the original frozen training cache')
    record_path = guarded(model_path.parent/'training_run.json')
    record_bytes = record_path.read_bytes()
    record_sha = hashlib.sha256(record_bytes).hexdigest()
    training_record = json.loads(record_bytes)
    if (training_record.get('model_sha256') != model_sha256
            or training_record.get('temporal_provenance') != proof
            or training_record.get('calibration', {}).get('threshold') != artifact.get('threshold')):
        raise ValueError('Frozen model, threshold or provenance differs from its training record')
    with (dataset/'transactions.csv').open(encoding='utf-8-sig', newline='') as stream:
        memberships = partition_rows(csv.DictReader(stream), plan)
    selection = dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'],
                     start_at=plan['train']['start_at'], end_at=plan['evaluation']['end_at'])
    rows, matrix = selected_matrix(dataset, contract['columns'], selection,
                                   windows['train'][0], windows['evaluation'][1])
    assigned = {r['transaction_id']: r['partition'] for r in memberships}
    summaries, identities = {}, {}
    for name in PARTITIONS:
        mask = [assigned[r['transaction_id']] == name for r in rows]
        selected = [r for r, keep in zip(rows, mask) if keep]
        if not selected or set(r['company_id'] for r in selected) != set(plan['company_ids']):
            raise ValueError('Every declared company needs observations in each audited window')
        summaries[name] = window_summary(selected, matrix[mask],
            dict(company_ids=plan['company_ids'], source_ref=plan['source_ref'], **plan[name]))
        identities[name] = {r['transaction_id'] for r in selected}
        if name in ('train', 'calibration') and summaries[name] != proof[name]:
            raise ValueError('Actual '+name+' rows/features do not match the frozen training provenance')
    overlaps = {left+'__'+right: len(identities[left] & identities[right])
                for left, right in (('train', 'calibration'), ('train', 'evaluation'), ('calibration', 'evaluation'))}
    if any(overlaps.values()):
        raise ValueError('Actual observation IDs overlap between model windows')
    counts = Counter(r['partition'] for r in memberships)
    report = dict(version=VERSION, status='actual_source_partitions_verified',
                  dataset=str(dataset), dataset_version=metadata['version'],
                  data_origin=metadata.get('data_origin', 'not_attested'), plan=plan,
                  partition_time_field='posted_at', comparison_timezone='UTC',
                  window_end_exclusive=True, model_sha256=model_sha256,
                  source_manifest_sha256=manifest_sha, training_record_sha256=record_sha,
                  temporal_provenance_fingerprint=proof['fingerprint'],
                  feature_contract_fingerprint=contract['fingerprint'],
                  windows=summaries, actual_id_overlaps=overlaps,
                  membership_rows=len(memberships), partition_counts=dict(sorted(counts.items())),
                  membership_fingerprint=digest(memberships),
                  actual_train_calibration_features_match_model=True,
                  frozen_calibration_threshold=artifact['threshold'],
                  threshold_matches_training_record=True,
                  models_fitted=0, observations_scored=0, labels_loaded=False,
                  splits_loaded=False, oracle_loaded=False, queue_changed=False,
                  holdout_005_loaded_or_scored=False, external_notifications=0,
                  operational_benefit_measured=False,
                  limitations=['Audits a trusted model and its original cache; does not rebuild raw-source features',
                               'Evaluation scores from earlier technical runs are not an untouched future benchmark',
                               'Real SME acceptance and independent operational review remain pending'])

    def unchanged():
        if (sha(dataset/'manifest.json') != manifest_sha or sha(model_path) != model_sha256
                or sha(record_path) != record_sha or source_checks(dataset, metadata) != inputs):
            raise ValueError('Frozen audit inputs changed during verification')
    unchanged()
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.parent/('.temporal-audit-'+uuid.uuid4().hex)
    staged.mkdir()
    try:
        with (staged/'temporal_partitions.csv').open('w', encoding='utf-8', newline='') as stream:
            fields = ['transaction_id', 'company_id', 'posted_at', 'posted_at_utc', 'partition']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(memberships)
        report['membership_csv_sha256'] = sha(staged/'temporal_partitions.csv')
        (staged/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        unchanged()
        if output.exists():
            raise FileExistsError('Audit output appeared during verification; refusing to replace it')
        staged.rename(output)
    finally:
        if staged.exists():
            for name in ('temporal_partitions.csv', 'audit.json'):
                (staged/name).unlink(missing_ok=True)
            staged.rmdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--model-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit_model_windows(args.dataset, args.model, args.output, model_sha256=args.model_sha256)
    print(json.dumps(dict(status=report['status'], partitions=report['partition_counts'],
                         actual_id_overlaps=report['actual_id_overlaps'], output=str(args.output))))


if __name__ == '__main__':
    main()
