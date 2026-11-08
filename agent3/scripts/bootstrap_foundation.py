"""Create an isolated, minimal environment offline from installed distributions.

Run with the existing prototype interpreter. Never modifies its packages.
Only files under site-packages of explicitly pinned distributions are copied;
models, datasets, caches, scripts and the old environment itself are not copied.
"""
import hashlib
from datetime import datetime, timezone
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'agent3_tax_compliance'
TARGET = PROJECT / '.venv'
LOCK = PROJECT / 'requirements-foundation.lock'
REPORT = ROOT / 'docs/agent3/plans/evidence/plan01/environment_snapshot.json'


def main():
    pins = [line.split('==') for line in LOCK.read_text().splitlines() if line and not line.startswith('#')]
    distributions = []
    for name, version in pins:
        dist = metadata.distribution(name)
        if dist.version != version:
            raise RuntimeError(f'locked version unavailable: {name}=={version}')
        distributions.append(dist)
    if TARGET.exists():
        raise RuntimeError('target already exists; verify it instead of overwriting')
    if sys.version_info[:3] != (3, 10, 5) or sys.platform != 'win32':
        raise RuntimeError('offline binary snapshot requires Python 3.10.5 / Windows')
    venv.EnvBuilder(with_pip=False).create(TARGET)
    destination = TARGET / 'Lib/site-packages'
    copied = {}
    for dist in distributions:
        site = Path(dist.locate_file('')).resolve()
        for entry in dist.files or ():
            rel = Path(str(entry))
            if rel.is_absolute() or '..' in rel.parts or '__pycache__' in rel.parts or rel.suffix == '.pyc':
                continue
            source = Path(dist.locate_file(entry)).resolve()
            if not source.is_relative_to(site) or not source.is_file():
                continue
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied[rel.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {
        'schema_version': '1.0.0', 'creator': 'bootstrap_foundation', 'stage': 'environment',
        'created_at': datetime.now(timezone.utc).isoformat(), 'config_version': 'foundation-v1',
        'python': sys.version, 'platform': sys.platform,
        'lock_sha256': hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        'packages': dict(pins), 'method': 'offline_selected_distribution_files',
        'files': copied,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'Created isolated .venv; {len(pins)} pinned distributions, {len(copied)} verified files; no network/model initialization')


if __name__ == '__main__':
    main()
