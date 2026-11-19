"""Build the exact public (ciphertext-only) training-worker distribution: no enterprise sources, no secret keys."""
from pathlib import Path
import hashlib
import json
import shutil

FILES = ('experiments/__init__.py', 'experiments/he_training/__init__.py', 'experiments/he_training/protocol.py',
         'experiments/he_training/store.py', 'experiments/he_training/batch_protocol.py', 'experiments/he_training/batch_store.py',
         'experiments/he_training/runtime.py', 'experiments/he_training/circuit.py',
         'experiments/he_training/worker.py', 'experiments/he_training/runner.py')


def build(output):
    source = Path(__file__).resolve().parents[2]
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('new bundle directory required')
    output.mkdir(parents=True)
    hashes = {}
    for name in FILES:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = dict(version='he-training-public-bundle/0.1.0', files=hashes)
    (output / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.output)))
