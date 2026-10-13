"""Add only pinned ingestion distributions to the existing isolated environment."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'agent3_tax_compliance'


def main():
    if sys.version_info[:3] != (3,10,5) or sys.platform != 'win32':
        raise RuntimeError('offline binaries require Python 3.10.5 Windows')
    destination=PROJECT/'.venv/Lib/site-packages'
    if not destination.is_dir():
        raise RuntimeError('bootstrap foundation first')
    lock=PROJECT/'requirements-ingestion.lock'
    pins=[line.split('==') for line in lock.read_text().splitlines() if line and not line.startswith('#')]
    sources=[]
    for name, version in pins:
        distribution=metadata.distribution(name)
        if distribution.version != version:
            raise RuntimeError(f'locked distribution unavailable: {name}')
        site=Path(distribution.locate_file('')).resolve()
        for entry in distribution.files or ():
            relative=Path(str(entry))
            if relative.is_absolute() or '..' in relative.parts or '__pycache__' in relative.parts or relative.suffix=='.pyc':
                continue
            source=Path(distribution.locate_file(entry)).resolve()
            if source.is_file() and source.is_relative_to(site):
                target=destination/relative
                value=hashlib.sha256(source.read_bytes()).hexdigest()
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=value:
                    raise RuntimeError(f'refusing to overwrite differing package file: {relative}')
                sources.append((source,target,relative,value))
    hashes={}
    for source,target,relative,value in sources:
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
        hashes[relative.as_posix()]=value
    output=ROOT/'docs/agent3/plans/evidence/plan02'
    output.mkdir(parents=True,exist_ok=True)
    (output/'environment_snapshot.json').write_text(json.dumps(dict(
        schema_version='1.0.0',config_version='ingestion-v1',creator='bootstrap_ingestion',stage='environment',
        created_at=datetime.now(timezone.utc).isoformat(),python=sys.version,platform=sys.platform,
        lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),packages=dict(pins),files=hashes),indent=2)+'\n',encoding='utf-8')
    print(f'Provisioned {len(pins)} additive distributions; {len(hashes)} files; old environments unchanged')


if __name__=='__main__':
    main()
