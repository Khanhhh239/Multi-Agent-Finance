"""Exercise maintenance commands against disposable data, never real artifacts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
PWSH = shutil.which('pwsh')
pytestmark = pytest.mark.skipif(PWSH is None, reason='PowerShell 7 is required')


@pytest.fixture
def workspace(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in ('manage_duplicates.ps1', 'archive_common.psm1',
                 'restore_cleanup_duplicates.ps1', 'restore_benchrec_archive.ps1'):
        shutil.copyfile(SCRIPTS / name, scripts / name)
    (tmp_path / 'outputs/maintenance').mkdir(parents=True)
    return tmp_path


def invoke(workspace, script='manage_duplicates.ps1', *args, ok=True):
    result = subprocess.run(
        [PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
         str(workspace / 'scripts' / script), *args],
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    if ok:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result


def manifest(workspace, dataset):
    name, method, count, stage, prefix, retained = {
        'T0': ('t0_staging_cleanup_20261105.json',
               'hardlink_t0_payloads_and_remove_disposable_staging', 186, None,
               'data/T0/processed/old/', 'data/T0/processed/final/'),
        'UnifiedV2': ('unified_v2_hardlink_dedup_20261105.json', 'hardlink_to_r3',
                      108, None, 'outputs/data/unified_collection_v2_20261104/',
                      'outputs/data/unified_collection_v2_20261104_r3/'),
        'Research': ('research_hardlink_dedup_20261105.json',
                     'hardlink_research_stages_8_9_10', 333, 8,
                     'data/synthetic/hc_old/', 'data/synthetic/hc_final/'),
        'Small': ('small_hardlink_dedup_20261105.json',
                  'hardlink_small_stages_11_12_13_14', 1641, 11,
                  'data/T0/processed/old/', 'data/T0/processed/final/'),
    }[dataset]
    payload = b'x' * (65536 if dataset == 'Research' else 5)
    digest = hashlib.sha256(payload).hexdigest()
    entries = [dict(path=f'{prefix}{i}.parquet', retained_path=f'{retained}{i}.parquet',
                    stage=stage, bytes=len(payload), sha256=digest,
                    original_creation_time_utc='2025-01-01T00:00:00Z',
                    original_last_write_time_utc='2025-02-01T00:00:00Z',
                    original_attributes=32) for i in range(count)]
    data = dict(method=method, duplicate_payloads=entries)
    path = workspace / 'outputs/maintenance' / name
    path.write_text(json.dumps(data), encoding='utf-8')
    for entry in entries[:2]:
        for key in ('path', 'retained_path'):
            target = workspace / entry[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    return path, data, payload


@pytest.mark.parametrize('dataset', ['T0', 'UnifiedV2', 'Research', 'Small'])
def test_verify_preview_compact_and_restore(workspace, dataset):
    _, data, payload = manifest(workspace, dataset)
    entry = data['duplicate_payloads'][0]
    source, destination = (workspace / entry[key] for key in ('retained_path', 'path'))
    args = ('-Dataset', dataset, '-RelativePath', entry['path'])
    original_id = destination.stat().st_ino
    invoke(workspace, 'manage_duplicates.ps1', *args)
    invoke(workspace, 'manage_duplicates.ps1', *args, '-Action', 'Compact', '-WhatIf')
    assert destination.stat().st_ino == original_id
    assert not os.path.samefile(source, destination)
    invoke(workspace, 'manage_duplicates.ps1', *args, '-Action', 'Compact')
    assert os.path.samefile(source, destination)
    invoke(workspace, 'manage_duplicates.ps1', *args, '-Action', 'Restore')
    assert not os.path.samefile(source, destination)
    assert source.read_bytes() == destination.read_bytes() == payload
    assert int(destination.stat().st_mtime) == 1738368000  # 2025-02-01 UTC
    assert not list(workspace.rglob('*dedup-backup'))


def test_preflight_failure_does_not_change_any_selected_file(workspace):
    _, data, _ = manifest(workspace, 'T0')
    # Keep the manifest size valid; the second file is corrupt. All other
    # destinations need not exist because preflight must stop before any writes.
    first, second = data['duplicate_payloads'][:2]
    destination = workspace / first['path']
    original_id = destination.stat().st_ino
    (workspace / second['path']).write_bytes(b'wrong')
    result = invoke(workspace, 'manage_duplicates.ps1', '-Dataset', 'T0',
                    '-Action', 'Compact', ok=False)
    assert 'File differs from manifest' in result.stderr
    assert destination.stat().st_ino == original_id
    assert not os.path.samefile(destination, workspace / first['retained_path'])
    assert not list(workspace.rglob('*dedup-backup'))


@pytest.mark.parametrize('change, message', [
    ('scope', 'Unexpected payload scope'),
    ('destination', 'Retained source is also a replacement destination'),
    ('stage', 'does not belong to dataset'),
    ('backup', 'Recovery backup already exists'),
])
def test_reject_invalid_requests_before_writing(workspace, change, message):
    path, data, payload = manifest(workspace, 'T0')
    entry = data['duplicate_payloads'][0]
    args = ['-Dataset', 'T0', '-RelativePath', entry['path'], '-Action', 'Compact']
    if change == 'scope':
        entry['retained_path'] = 'data/T0/processed/../../outside.parquet'
    elif change == 'destination':
        entry['retained_path'] = data['duplicate_payloads'][1]['path']
    elif change == 'stage':
        args += ['-Stage', '8']
    else:
        (workspace / (entry['path'] + '.dedup-backup')).write_bytes(b'keep backup')
    path.write_text(json.dumps(data), encoding='utf-8')
    result = invoke(workspace, 'manage_duplicates.ps1', *args, ok=False)
    assert message in result.stderr
    assert (workspace / entry['path']).read_bytes() == payload


def test_archive_restore_uses_shared_checks_and_refuses_overwrite(workspace):
    source = workspace / 'data/T0/processed/final/record.json'
    destination = workspace / 'data/T0/processed/old/record.json'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'original')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    data = dict(duplicate_payloads=[dict(path=destination.relative_to(workspace).as_posix(),
                retained_path=source.relative_to(workspace).as_posix(), sha256=digest)])
    (workspace / 'outputs/maintenance/cleanup_2026-10-31.json').write_text(json.dumps(data))
    invoke(workspace, 'restore_cleanup_duplicates.ps1', '-VerifyOnly')
    invoke(workspace, 'restore_cleanup_duplicates.ps1', '-WhatIf')
    assert not destination.exists()
    invoke(workspace, 'restore_cleanup_duplicates.ps1')
    assert source.read_bytes() == destination.read_bytes()
    destination.write_bytes(b'different')
    result = invoke(workspace, 'restore_cleanup_duplicates.ps1', ok=False)
    assert 'refusing to overwrite' in result.stderr
    assert destination.read_bytes() == b'different'


def test_restore_failure_rolls_back_original_file(workspace):
    path, data, payload = manifest(workspace, 'T0')
    entry = data['duplicate_payloads'][0]
    entry['original_creation_time_utc'] = 'invalid timestamp'
    path.write_text(json.dumps(data), encoding='utf-8')
    destination = workspace / entry['path']
    original_id = destination.stat().st_ino
    invoke(workspace, 'manage_duplicates.ps1', '-Dataset', 'T0',
           '-RelativePath', entry['path'], '-Action', 'Restore', ok=False)
    assert destination.read_bytes() == payload
    assert destination.stat().st_ino == original_id
    assert not list(workspace.rglob('*dedup-backup'))


def test_zip_restore_preserves_hash_and_utc_metadata(workspace):
    prefix = 'data/T0/raw/benchrec_kaggle/2026-10-19-v3/'
    names = ['BenchRec_cash_v1.0_eval.csv', 'BenchRec_cash_v1.0_solution.csv',
             'BenchRec_cash_v1.0_train.csv', 'MatcherByChatGPT_submission.csv']
    archive = workspace / prefix / 'dataset.zip'
    archive.parent.mkdir(parents=True)
    payload = b'column\nvalue\n'
    digest = hashlib.sha256(payload).hexdigest()
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name in names:
            zipped.writestr(name, payload)
    entries = [dict(path=prefix + name, zip_member=name, bytes=len(payload),
                    sha256=digest, original_creation_time_utc='2025-01-01T07:00:00+07:00',
                    original_last_write_time_utc='2025-02-01T07:00:00+07:00',
                    original_attributes=32) for name in names]
    data = dict(method='remove_extracted_csv_keep_verified_zip',
                archive_path=prefix + 'dataset.zip',
                archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                archived_csv_files=entries)
    (workspace / 'outputs/maintenance/benchrec_zip_cleanup_20261106.json').write_text(json.dumps(data))
    invoke(workspace, 'restore_benchrec_archive.ps1')
    invoke(workspace, 'restore_benchrec_archive.ps1', '-Action', 'Restore', '-WhatIf')
    assert not (archive.parent / names[0]).exists()
    invoke(workspace, 'restore_benchrec_archive.ps1', '-Action', 'Restore')
    for name in names:
        target = archive.parent / name
        assert target.read_bytes() == payload
        assert int(target.stat().st_mtime) == 1738368000
    (archive.parent / names[0]).write_bytes(b'keep edited data')
    result = invoke(workspace, 'restore_benchrec_archive.ps1', '-Action', 'Restore', ok=False)
    assert 'refusing overwrite' in result.stderr
    assert (archive.parent / names[0]).read_bytes() == b'keep edited data'
