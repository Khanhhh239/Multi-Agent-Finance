"""Compare extraction changes on frozen OCR observations, without model inference."""
import argparse
import hashlib
import re
import sqlite3
import time
from datetime import datetime, timezone

import ocr_quality as quality
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.canonicalization.derive import sha
from src.domain.taxpayer import TaxpayerMaster
from src.extraction.contracts import ExtractionArtifact
from src.extraction.service import extract, implementation_sha
from src.quality.ocr_evaluation import validate_labels


def frozen_inputs(folder, artifact):
    """Read only the original case database; bind every replay to its artifact."""
    scope = (artifact.tenant_id, artifact.taxpayer_id, artifact.ingestion_id)
    with sqlite3.connect((folder / 'capture.sqlite3').resolve().as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute('SELECT payload,sha256 FROM ocr_jobs WHERE tenant_id=? '
                          'AND taxpayer_id=? AND ingestion_id=? AND payload IS NOT NULL', scope).fetchall()
        matches = []
        for payload, digest in rows:
            if hashlib.sha256(payload.encode()).hexdigest() != digest:
                raise ValueError('Cached OCR payload integrity failure')
            document = NormalizedDocumentExtraction.model_validate_json(payload)
            if sha(document.model_dump(mode='json')) == artifact.normalized_input_sha256:
                matches.append(document)
        if len(matches) != 1:
            raise ValueError('Expected exactly one OCR observation bound to the artifact')
        document = matches[0]
        if (document.tenant_id, document.taxpayer_id, document.ingestion_id,
                document.source_id, document.document_id, document.input_sha256) != (
                *scope, artifact.source_id, artifact.document_id, artifact.input_sha256):
            raise ValueError('Artifact source identity mismatch')
        row = db.execute('SELECT payload FROM taxpayer_masters WHERE tenant_id=? '
                         'AND taxpayer_id=? AND revision=?',
                         (*scope[:2], document.taxpayer_master_revision)).fetchone()
        if not row:
            raise ValueError('Missing original taxpayer master')
        return document, TaxpayerMaster.model_validate_json(row[0])


def reference_report(run_id, inputs, manifest, hashes):
    """Rescore a previous fix on the exact same frozen observations/labels."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('Use a plain comparison run ID')
    folder=quality.OUTPUT/run_id;path=folder/'report.json'
    report=quality.read(path);hashes[str(path)]=quality.file_hash(path)
    expected={before['case_id'] for before,_,_,_,_ in inputs}
    if (report.get('manifest_sha256')!=manifest['manifest_sha256']
            or set(report.get('expected_cases',()))!=expected
            or {c['case_id'] for c in report.get('cases',())}!=expected):
        raise ValueError('Previous fix must cover the same dataset cases')
    if report.get('run_state')!='COMPLETED' or report.get('dataset_validated_at_end') is not True:
        raise ValueError('Previous fix must be completed and validated')
    bindings={before['case_id']:(labels,original,doc) for before,labels,original,doc,_ in inputs}
    cases=[]
    for case in report['cases']:
        labels,original,document=bindings[case['case_id']]
        path=folder/case['case_id']/'extraction.json'
        hashes[str(path)]=quality.file_hash(path)
        artifact=ExtractionArtifact.model_validate_json(path.read_bytes())
        if (artifact.tenant_id,artifact.taxpayer_id,artifact.ingestion_id,artifact.input_sha256,
                artifact.source_id,artifact.document_id,artifact.normalized_input_sha256)!=(
                original.tenant_id,original.taxpayer_id,original.ingestion_id,original.input_sha256,
                original.source_id,original.document_id,sha(document.model_dump(mode='json'))):
            raise ValueError('Previous fix observation/source identity mismatch')
        cases.append({**case,'score':quality.score_record(artifact.record,labels)})
    return {**report,'cases':cases,'summary':quality.summarize(cases,False)}


def run(args):
    for name in (args.baseline_run, args.run_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
            raise ValueError('Use plain run IDs')
    baseline_folder = quality.OUTPUT / args.baseline_run
    baseline_path = baseline_folder / 'report.json'
    original = quality.read(baseline_path)
    if original.get('run_state') != 'COMPLETED' or original.get('dataset_validated_at_end') is not True:
        raise ValueError('Replay requires a completed, validated baseline')
    manifest = quality.read(baseline_folder / 'manifest.json')
    quality.verify_dataset(manifest, quality.ROOT)
    supplied = quality.read(args.labels)
    if supplied.get('run_id') != args.baseline_run:
        raise ValueError('Labels belong to another baseline run')
    entries = {entry['case_id']: entry for entry in manifest['entries']}
    expected = set(original['expected_cases'])
    if set(supplied['cases']) != expected or {c['case_id'] for c in original['cases']} != expected:
        raise ValueError('Replay requires identical complete case coverage')
    if original['manifest_sha256'] != manifest['manifest_sha256']:
        raise ValueError('Baseline manifest mismatch')
    hashes = {str(path): quality.file_hash(path) for path in (baseline_path, args.labels, baseline_folder / 'manifest.json')}
    inputs = []
    for before in original['cases']:
        identifier = before['case_id']; entry = entries[identifier]
        annotation = supplied['cases'][identifier]
        if annotation['sha256'] != entry['sha256'] or before['sha256'] != entry['sha256']:
            raise ValueError('Labels/source hash mismatch')
        validate_labels(annotation['labels'])
        path = baseline_folder / identifier / 'extraction.json'
        hashes[str(path)] = quality.file_hash(path)
        database = path.parent / 'capture.sqlite3'
        hashes[str(database)] = quality.file_hash(database)
        artifact = ExtractionArtifact.model_validate_json(path.read_bytes())
        if artifact.input_sha256 != entry['sha256']:
            raise ValueError('Artifact/source hash mismatch')
        document, master = frozen_inputs(path.parent, artifact)
        inputs.append((before, annotation['labels'], artifact, document, master))
    previous_fix=reference_report(args.compare_run,inputs,manifest,hashes) if getattr(args,'compare_run',None) else None
    out = quality.fresh_directory(args.run_id)
    quality.write(out / 'state.json', {'state': 'RUNNING'})
    quality.write(out / 'manifest.json', manifest)
    quality.write(out / 'labels.json', {**supplied, 'run_id': args.run_id})
    baseline = {**original, 'cases': []}
    report = {key: original[key] for key in ('version', 'manifest_sha256', 'split', 'expected_cases')}
    report.update(run_state='RUNNING', created_at=datetime.now(timezone.utc).isoformat(),
                  evaluation_mode='FROZEN_OCR_EXTRACTION_REPLAY', baseline_run=args.baseline_run,
                  model_inference_calls=0, latency_evaluated=False, workload_controlled=False,
                  extractor_sha256=implementation_sha(), runner_sha256=quality.file_hash(__file__), cases=[])
    report['frozen_input_hashes'] = {str(quality.Path(path).resolve().relative_to(quality.ROOT)): digest
                                     for path, digest in hashes.items()}
    for before, labels, previous, document, master in inputs:
        start = time.perf_counter()
        artifact = extract(document, previous.record.source_format if previous.record else 'PDF',
                           master, previous.profile)
        duration = time.perf_counter() - start
        folder = out / before['case_id']; folder.mkdir()
        quality.write(folder / 'extraction.json', artifact.model_dump(mode='json'))
        quality.write(folder / 'normalized.json', document.model_dump(mode='json'))
        row = {key: before[key] for key in ('case_id', 'sha256', 'input_kind', 'group_id', 'derived_render')}
        row.update(state='REVIEW' if artifact.record else artifact.segmentation.status,
                   elapsed_seconds=None, extraction_elapsed_seconds=duration, timings=[], page_count=None,
                   source_page_count=len(document.pages), score=quality.score_record(artifact.record, labels))
        baseline['cases'].append({**before, 'score': quality.score_record(previous.record, labels)})
        report['cases'].append(row)
        print(before['case_id'], row['state'], row['score']['correct'], '/', row['score']['labeled'], flush=True)
    quality.verify_dataset(manifest, quality.ROOT)
    if any(quality.file_hash(path) != digest for path, digest in hashes.items()):
        raise ValueError('Baseline or labels changed during replay')
    if implementation_sha() != report['extractor_sha256']:
        raise ValueError('Extractor changed during replay')
    report.update(run_state='COMPLETED', dataset_validated_at_end=True)
    baseline['summary'] = quality.summarize(baseline['cases'], baseline.get('workload_controlled', False))
    report['summary'] = quality.summarize(report['cases'], False)
    report['summary']['latency_gate'] = 'NOT_EVALUATED_FROZEN_OCR'
    quality.write(out / 'baseline_scored_report.json', baseline)
    quality.write(out / 'report.json', report)
    comparison = quality.compare_runs(baseline, report)
    quality.write(out / 'comparison.json', comparison)
    if previous_fix is not None:
        quality.write(out / 'previous_fix_scored_report.json',previous_fix)
        quality.write(out / 'comparison_previous.json',quality.compare_runs(previous_fix,report))
    quality.write(out / 'state.json', {'state': 'COMPLETED', 'release_approved': False})
    print(str(out / 'comparison.json'))
    print(comparison)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run', required=True)
    parser.add_argument('--labels', type=quality.Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--compare-run', help='Also compare against the previous completed extraction fix')
    args = parser.parse_args()
    destination = quality.OUTPUT / args.run_id
    safe = bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.run_id))
    existed = destination.exists()
    try:
        code = run(args)
    except Exception as error:
        if safe and not existed and destination.is_dir():
            quality.write(destination / 'state.json', {'state': 'FAILED', 'error_code': type(error).__name__,
                                                       'release_approved': False})
        raise
    raise SystemExit(code)
