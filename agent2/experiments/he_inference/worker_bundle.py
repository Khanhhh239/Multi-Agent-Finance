"""Build an allowlisted worker source bundle, excluding enterprise code/data."""
import argparse
import hashlib
from pathlib import Path

from .protocol import canonical

FILES = ('__init__.py', 'protocol.py', 'cloud_worker.py', 'http_common.py', 'worker_store.py', 'worker_server.py')


def build(destination):
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Worker destination must be a new empty directory')
    package = destination / 'experiments' / 'he_inference'
    package.mkdir(parents=True, exist_ok=True)
    (destination / 'experiments/__init__.py').write_text('"""Ciphertext worker distribution only."""\n')
    for name in FILES:
        (package / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    (destination / 'requirements-worker.txt').write_text('tenseal==0.3.18\ncryptography==50.0.2\n', encoding='utf-8')
    manifest = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in destination.rglob('*') if p.is_file()}
    (destination / 'worker-manifest.json').write_bytes(canonical(dict(version='he-worker-bundle/1.0.0', sha256=manifest)))
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    print(build(parser.parse_args().output_dir))
