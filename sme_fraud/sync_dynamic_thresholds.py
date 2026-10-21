"""Publish company-specific rolling thresholds from verified full accounting sources."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time

from .dynamic_thresholds import DynamicThresholds, ThresholdPolicy, VERSION, VN, digest, timestamp
from .threshold_sources import extract_observations
from .threshold_artifacts import write_parameters


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.threshold-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return hashlib.sha256(data).hexdigest()


def read_sources(directory):
    directory = Path(directory)
    manifest_bytes = (directory/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    tables, hashes = {}, {}
    for name in ('companies', 'transactions', 'journal_documents', 'journal_lines'):
        path = directory/f'{name}.csv'
        if name.startswith('journal_') and not path.exists() and path.name not in manifest['files']:
            tables[name] = []
            continue
        entry = manifest['files'].get(path.name)
        if entry is None:
            raise ValueError(f'Threshold source missing from manifest: {path.name}')
        expected = entry.get('sha256') if isinstance(entry, dict) else entry
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            raise ValueError(f'Threshold source checksum mismatch: {path.name}')
        hashes[path.name] = actual
        tables[name] = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    if (directory/'manifest.json').read_bytes() != manifest_bytes:
        raise RuntimeError('Threshold source manifest changed during read; retry the batch')
    return tables, hashes, hashlib.sha256(manifest_bytes).hexdigest()


def _load_version(output, state):
    if state.get('schema_version') != VERSION or not re.fullmatch(r'[0-9a-f]{64}', state.get('snapshot', '')):
        raise ValueError('Invalid threshold snapshot pointer')
    folder = Path(output)/'snapshots'/state['snapshot']
    if sha(folder/'commit.json') != state['sha256']:
        raise ValueError('Threshold commit checksum mismatch')
    commit = json.loads((folder/'commit.json').read_text(encoding='utf-8'))
    if commit.get('as_of') != state['as_of'] or commit.get('fingerprint') != state['snapshot'] or commit.get('schema_version') != VERSION:
        raise ValueError('Threshold snapshot metadata mismatch')
    for name, checksum in commit['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid threshold artifact path')
        if sha(folder/relative) != checksum:
            raise ValueError(f'Threshold artifact checksum mismatch: {name}')
    return commit, folder


def load_snapshot(output):
    """A reader pins one atomic pointer and verifies the complete batch."""
    state = json.loads((Path(output)/'latest.json').read_text(encoding='utf-8'))
    commit, folder = _load_version(output, state)
    return dict(commit, parameters=json.loads((folder/'dynamic_threshold_parameters.json').read_text(encoding='utf-8')))


def sync(directory, output, cutoff, companies=None, policy=None):
    directory, output = Path(directory), Path(output)
    cutoff = timestamp(cutoff)
    policy = policy or ThresholdPolicy()
    if directory.resolve() == output.resolve() or directory.resolve() in output.resolve().parents:
        raise ValueError('Threshold output must be separate from source data')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.threshold-sync.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        previous = load_snapshot(output) if (output/'latest.json').exists() else None
        if previous and previous['as_of'] > cutoff:
            raise ValueError('Refusing to move threshold watermark backward; use a separate output for replay')
        tables, hashes, manifest_hash = read_sources(directory)
        known = {r['company_id'] for r in tables['companies']}
        selected = sorted(known if companies is None else set(companies))
        if not selected or set(selected)-known:
            raise ValueError('Unknown or empty threshold company scope')
        for name in ('transactions', 'journal_documents', 'journal_lines'):
            if any(r['company_id'] not in known for r in tables[name]):
                raise ValueError('Threshold source contains an unknown company')
            tables[name] = [r for r in tables[name] if r['company_id'] in selected]
        code_hashes = {name: sha(Path(__file__).with_name(name)) for name in
                       ('dynamic_thresholds.py', 'threshold_sources.py', 'threshold_artifacts.py', 'sync_dynamic_thresholds.py')}
        identity = dict(schema_version=VERSION, as_of=cutoff, policy=policy.as_dict(),
                        company_scope=selected, source_sha256=hashes,
                        source_manifest_sha256=manifest_hash, code_sha256=code_hashes)
        fingerprint = digest(identity)
        if previous and previous['fingerprint'] == fingerprint:
            return dict(changed=False, fingerprint=fingerprint, as_of=cutoff, **previous['summary'])
        observations, source_summary = extract_observations(tables)
        engine = DynamicThresholds(observations, policy)
        rows = engine.parameter_table(cutoff)
        summary = dict(companies=len(selected), observations_known_at_cutoff=engine.index,
                       parameter_rows=len(rows), status_counts=dict(Counter(r['status'] for r in rows)))
        folder = output/'snapshots'/fingerprint
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder/'commit.json').exists():
            write_parameters(folder, rows, policy.as_dict(), source_summary)
            company_files = {}
            for company in selected:
                name = 'company_'+digest(company)[:20]+'.csv'
                company_files[company] = name
                company_rows = [r for r in rows if r['company_id'] == company]
                with (folder/name).open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['company_id', 'status', 'threshold_vnd'])
                    writer.writeheader()
                    writer.writerows(company_rows)
            files = {p.name: sha(p) for p in folder.iterdir() if p.is_file() and p.name != 'commit.json'}
            atomic_json(folder/'commit.json', dict(identity, fingerprint=fingerprint,
                        summary=summary, source_summary=source_summary, company_files=company_files, files=files))
        state = dict(schema_version=VERSION, as_of=cutoff, snapshot=fingerprint, sha256=sha(folder/'commit.json'))
        _load_version(output, state)
        # No reader sees a new company table until all files have been verified.
        atomic_json(output/'latest.json', state)
        return dict(changed=True, fingerprint=fingerprint, as_of=cutoff, **summary)
    finally:
        os.close(descriptor)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, help='Rule config JSON containing dynamic_* policy keys')
    parser.add_argument('--as-of')
    parser.add_argument('--company', action='append')
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval-seconds', type=int, default=3600)
    args = parser.parse_args()
    if args.interval_seconds < 5:
        parser.error('Polling interval must be at least five seconds')
    if args.watch and args.as_of:
        parser.error('Use --as-of for one reproducible batch; --watch advances the clock')
    while True:
        try:
            config = json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else {}
            result = sync(args.data, args.output, args.as_of or datetime.now(VN).isoformat(timespec='seconds'),
                          args.company, ThresholdPolicy.from_config(config))
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as error:
            if not args.watch:
                raise
            print(json.dumps(dict(status='batch_failed', error=str(error)), ensure_ascii=False), flush=True)
        if not args.watch:
            break
        time.sleep(args.interval_seconds)


if __name__ == '__main__':
    main()
