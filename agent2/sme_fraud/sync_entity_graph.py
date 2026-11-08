"""Batch/poll entity graph synchronization with immutable snapshots and an atomic pointer."""
import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .entity_graph import EntityGraph, GRAPH_VERSION, VN, as_of, digest


def read_sources(directory):
    directory = Path(directory)
    manifest_bytes = (directory/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    tables, hashes = {}, {}
    for name in ('companies', 'employees', 'vendors', 'entity_links'):
        path = directory/f'{name}.csv'
        if name == 'entity_links' and not path.exists() and path.name not in manifest['files']:
            tables[name] = []
            continue
        entry = manifest['files'].get(path.name)
        if entry is None:
            raise ValueError(f'Graph source missing from manifest: {path.name}')
        expected = entry.get('sha256') if isinstance(entry, dict) else entry
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            raise ValueError(f'Graph source checksum mismatch: {path.name}')
        hashes[path.name] = actual
        tables[name] = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    if (directory/'manifest.json').read_bytes() != manifest_bytes:
        raise RuntimeError('Graph source manifest changed during batch read; retry the batch')
    return tables, hashes, hashlib.sha256(manifest_bytes).hexdigest()


def atomic_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.graph-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return hashlib.sha256(data).hexdigest()


def load_snapshot(output):
    output = Path(output)
    state = json.loads((output/'latest.json').read_text(encoding='utf-8'))
    if state.get('schema_version') != GRAPH_VERSION or not re.fullmatch(r'[0-9a-f]{64}\.json', state.get('snapshot', '')):
        raise ValueError('Invalid graph snapshot pointer')
    content = (output/'snapshots'/state['snapshot']).read_bytes()
    if hashlib.sha256(content).hexdigest() != state['sha256']:
        raise ValueError('Graph snapshot checksum mismatch')
    payload = json.loads(content)
    if payload.get('schema_version') != GRAPH_VERSION or payload.get('as_of') != state['as_of']:
        raise ValueError('Graph snapshot metadata mismatch')
    return payload


def sync(directory, output, cutoff, companies=None):
    directory, output = Path(directory), Path(output)
    cutoff = as_of(cutoff)
    if directory.resolve() == output.resolve() or directory.resolve() in output.resolve().parents:
        raise ValueError('Graph output must be separate from the source dataset')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.graph-sync.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        previous = load_snapshot(output) if (output/'latest.json').exists() else None
        if previous and previous['as_of'] > cutoff:
            raise ValueError('Refusing to move the graph watermark backward; use a separate output for history')
        tables, hashes, manifest_hash = read_sources(directory)
        known = {r['company_id'] for r in tables['companies']}
        selected = sorted(known if companies is None else set(companies))
        if not selected or set(selected)-known:
            raise ValueError('Unknown or empty graph company scope')
        graphs = {company: EntityGraph(tables, company, cutoff).to_json(max_nodes=None) for company in selected}
        payload = dict(schema_version=GRAPH_VERSION, as_of=cutoff, source_manifest_sha256=manifest_hash,
                       source_sha256=hashes, companies=graphs,
                       summary=dict(companies=len(graphs), nodes=sum(len(g['nodes']) for g in graphs.values()),
                                    links=sum(len(g['links']) for g in graphs.values()),
                                    findings=sum(len(g['findings']) for g in graphs.values())))
        fingerprint = digest(payload)
        if previous is not None and digest(previous) == fingerprint:
            return dict(changed=False, fingerprint=fingerprint, as_of=cutoff, **payload['summary'])
        snapshots = output/'snapshots'
        snapshots.mkdir(exist_ok=True)
        snapshot = snapshots/f'{fingerprint}.json'
        checksum = atomic_json(snapshot, payload)
        # Publish only after the entire artifact is flushed. A failed batch
        # cannot leave readers with a half-new set of companies.
        atomic_json(output/'latest.json', dict(schema_version=GRAPH_VERSION, as_of=cutoff,
                                              snapshot=snapshot.name, sha256=checksum))
        return dict(changed=True, fingerprint=fingerprint, as_of=cutoff, **payload['summary'])
    finally:
        os.close(descriptor)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of')
    parser.add_argument('--company', action='append')
    parser.add_argument('--watch', action='store_true', help='Run batches periodically until stopped')
    parser.add_argument('--interval-seconds', type=int, default=3600)
    args = parser.parse_args()
    if args.interval_seconds < 5:
        parser.error('Polling interval must be at least five seconds')
    if args.watch and args.as_of:
        parser.error('--watch advances the cutoff clock; use --as-of for a single reproducible batch')
    while True:
        try:
            result = sync(args.data, args.output, args.as_of or datetime.now(VN).isoformat(timespec='seconds'), args.company)
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
