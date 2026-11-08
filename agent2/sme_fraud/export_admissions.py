"""Versioned provenance export from frozen queues; no scoring, fitting or writes to inputs."""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path

from .admission_export import VERSION, FIELDS, explain_admissions, digest
from .case_identity import values
from .feature_contract import sha
from .generate import write_csv
from .run_rule_repairs import write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def membership(cases):
    members = [tid for case in cases for tid in values(case.get('transaction_ids'))]
    if len(members) != len(set(members)):
        raise ValueError('Duplicate operational member in frozen queue')
    return set(members)


def run(output, *, baseline_root=ROOT/'reports/feature_model_sync_20261017',
        snapshot_root=ROOT/'reports/split_pattern_admission_20261017_v2', tags=('001', '003', '005')):
    output, baseline_root, snapshot_root = map(lambda path: Path(path).resolve(), (output, baseline_root, snapshot_root))
    if output.exists():
        raise FileExistsError('Use a fresh export directory; frozen reports are never overwritten')
    for source in (baseline_root, snapshot_root):
        if output == source or source in output.parents or output in source.parents:
            raise ValueError('Output must be separate from all source report trees')
    protected = {}
    for source in (baseline_root, snapshot_root):
        for path in source.rglob('*'):
            if path.is_file() and path.name != '.feedback.lock':
                protected[str(path)] = sha(path)
    for tag in tags:
        folder = snapshot_root/f'sme_fraud_{tag}'
        frozen = read_json(folder/'predictions_frozen.json')
        for name, expected in frozen['sha256'].items():
            if sha(folder/name) != expected:
                raise ValueError(f'Frozen commitment differs: {tag}/{name}')
        comparison = read_json(folder/'comparison.json')
        for name, expected in comparison.get('protected_sha256', {}).items():
            path = Path(name)
            path = path if path.is_absolute() else ROOT/path
            if sha(path) != expected:
                raise ValueError(f'Protected source differs: {path}')
            protected[str(path.resolve())] = expected
    code = {str(ROOT/'sme_fraud'/name): sha(ROOT/'sme_fraud'/name) for name in
        ('export_admissions.py', 'admission_export.py', 'case_queue.py', 'case_admission.py',
         'case_identity.py', 'generate.py', 'run_split_pattern_review.py')}
    output.mkdir(parents=True)
    write_json(output/'export_plan.json', dict(version=VERSION,
        baseline=str(baseline_root), snapshot=str(snapshot_root), tags=list(tags),
        policy='Explain the exact frozen membership delta; retain row observations verbatim',
        no_detector_or_model_run=True, no_queue_rebuild=True, no_feedback_migration=True,
        source_sha256=protected, code_sha256=code))
    summaries = []
    for tag in tags:
        before = baseline_root/f'sme_fraud_{tag}'
        source, target = snapshot_root/f'sme_fraud_{tag}', output/f'sme_fraud_{tag}'
        target.mkdir()
        old_members = membership(read_rows(before/'case_queue.csv'))
        cases = read_rows(source/'case_queue.csv')
        current_members = membership(cases)
        gained, removed = current_members-old_members, old_members-current_members
        legacy = read_rows(source/'added_admissions.csv')
        metadata = {row['transaction_id']: row for row in legacy}
        if len(metadata) != len(legacy) or set(metadata) != gained:
            raise ValueError('Legacy delta does not match actual queue membership change')
        result = dict(scores=read_rows(source/'rule_scores.csv'), hits=read_jsonl(source/'rule_hits.jsonl'),
            batch_events=read_jsonl(source/'batch_events.jsonl'), config=read_json(source/'rule_config.json'))
        relative_source = os.path.relpath(source, target).replace(os.sep, '/')
        rows, evidence = explain_admissions(result, cases, gained, source_directory=relative_source, metadata=metadata)
        if {row['transaction_id'] for row in rows} != gained or len(rows) != len(gained):
            raise ValueError('New export altered membership')
        for row in rows:
            if str(row['rule_score']) != str(metadata[row['transaction_id']]['rule_score']):
                raise ValueError('New export altered a frozen row score')
        write_csv(target/'added_admissions_v2.csv', rows, list(FIELDS))
        write_jsonl(target/'admission_evidence.jsonl', evidence)
        only_batch = [row for row in rows if row['admission_source'] == 'batch_closed']
        comparison = dict(tag=tag, version=VERSION, baseline_members=len(old_members),
            snapshot_members=len(current_members), added_members=len(gained), removed_members=len(removed),
            exported_rows=len(rows), evidence_records=len(evidence),
            added_members_sha256=digest(sorted(gained)), exported_members_sha256=digest(sorted(row['transaction_id'] for row in rows)),
            removed_ids=sorted(removed), row_observations_unchanged=True,
            membership_unchanged=True, all_added_ids_explained=True,
            admission_sources=dict(Counter(row['admission_source'] for row in rows)),
            effective_bases=dict(Counter(row['effective_admission_basis'] for row in rows)),
            batch_only_rows=only_batch, numeric_score_changed=False,
            hard_trigger_changed=False, operational_flag_changed=False,
            detector_scored=False, model_refitted=False, user_history_written=False,
            source_directory=relative_source)
        write_json(target/'membership_comparison.json', comparison)
        write_json(target/'export_commitment.json', dict(version=VERSION,
            files={name: sha(target/name) for name in ('added_admissions_v2.csv', 'admission_evidence.jsonl', 'membership_comparison.json')},
            source_commitment_sha256=sha(source/'predictions_frozen.json'),
            legacy_delta_sha256=sha(source/'added_admissions.csv')))
        summaries.append(comparison)
        print(f'{tag}: {len(rows)} added members, {len(only_batch)} batch-only, all linked to evidence', flush=True)
    if any(sha(Path(name)) != expected for name, expected in {**protected, **code}.items()):
        raise ValueError('An input or implementation changed during export')
    summary = dict(successful=True, version=VERSION, datasets=summaries,
        added_members=sum(row['added_members'] for row in summaries),
        protected_files=len(protected), protected_inputs_unchanged=True,
        frozen_reports_unchanged=True, detector_scored=False, model_refitted=False,
        row_scores_flags_hard_triggers_unchanged=True, queue_membership_unchanged=True)
    write_json(output/'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/admission_export_20261017_v1')
    parser.add_argument('--baseline-root', type=Path, default=ROOT/'reports/feature_model_sync_20261017')
    parser.add_argument('--snapshot-root', type=Path, default=ROOT/'reports/split_pattern_admission_20261017_v2')
    args = parser.parse_args()
    run(args.output, baseline_root=args.baseline_root, snapshot_root=args.snapshot_root)


if __name__ == '__main__':
    main()
