"""Build an exact public-worker distribution without enterprise sources."""
from pathlib import Path
import hashlib
import json
import shutil

FILES=('experiments/__init__.py','experiments/he4/__init__.py','experiments/he4/blob_store.py',
       'experiments/he4/public_worker.py','experiments/he4/service.py','experiments/he4/runner.py',
       'experiments/he_inference/__init__.py','experiments/he_inference/protocol.py',
       'experiments/he_inference/http_common.py','experiments/he_inference/worker_store.py')


def build(output):
    source=Path(__file__).resolve().parents[2];output=Path(output).resolve()
    if output.exists():raise ValueError('new bundle directory required')
    output.mkdir(parents=True);hashes={}
    for name in FILES:
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
        hashes[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    manifest=dict(version='he4-public-bundle/0.1.0',files=hashes)
    (output/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.output)))
