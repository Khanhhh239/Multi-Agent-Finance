"""Immutable provenance and split registry for synthetic training worlds."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import pandas as pd

from .contracts import SCHEMAS, validate_world
from ..paths import RAW, ROOT, SYNTH

TABLES = tuple(sorted(SCHEMAS))
SOURCES = {
    'calibration': SYNTH / 'calibration_fit.json',
    'oxcgrt': RAW / 'oxcgrt' / 'OxCGRT_compact_national_v1.csv',
    'wdi': RAW / 'wdi_vn' / 'wdi_vietnam.csv',
}
ROLES = ('train', 'validation', 'test')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def code_provenance(*, root=ROOT) -> dict:
    root = Path(root)
    code_files = sorted(path for base in ('agent1', 'scripts')
                        for path in (root / base).rglob('*.py'))
    code_hashes = {path.relative_to(root).as_posix(): sha256_file(path) for path in code_files}
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True,
                            capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Cannot identify Git commit')
    return {'commit': commit, 'source_code_sha256': canonical_hash(code_hashes)}


def source_provenance(*, root=ROOT, sources=None) -> dict:
    """Hash generator code and every external input, including explicit absence."""
    selected = SOURCES if sources is None else sources
    calibration = Path(selected['calibration'])
    if not calibration.is_file():
        raise FileNotFoundError(f'Missing calibration source: {calibration}')
    fit = json.loads(calibration.read_text(encoding='utf-8'))
    if not {'ontime_shift', 'pd_mult'} <= set(fit):
        raise ValueError('Calibration source lacks ontime_shift/pd_mult')
    data_hashes = {name: sha256_file(Path(path)) if Path(path).is_file() else None
                   for name, path in selected.items()}
    return {**code_provenance(root=root), 'source_data_sha256': data_hashes}


def check_world_files(directory: Path) -> dict[str, str]:
    directory = Path(directory)
    missing = [f'{table}.parquet' for table in TABLES
               if not (directory / f'{table}.parquet').is_file()]
    if missing:
        raise FileNotFoundError(f'{directory}: missing Parquet: {missing}')
    return {path.name: sha256_file(path) for path in sorted(directory.glob('*.parquet'))}


def create_world_manifest(directory: Path, provenance: dict) -> dict:
    directory = Path(directory)
    hashes = check_world_files(directory)
    config_path = directory / 'config.json'
    if not config_path.is_file():
        raise FileNotFoundError(f'{directory}: missing config.json')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config.get('name') != directory.name:
        raise ValueError(f'{directory}: config name differs from directory')
    validate_world(directory)
    expected = {'schema_version': 1, 'world': directory.name, 'seed': config['seed'],
                'config': config, 'config_sha256': sha256_file(config_path),
                'commit': provenance['commit'],
                'source_code_sha256': provenance['source_code_sha256'],
                'source_data_sha256': provenance['source_data_sha256'],
                'tables_sha256': hashes}
    path = directory / 'manifest.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != expected:
            raise ValueError(f'{directory}: existing manifest differs; use a new versioned world name')
    else:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(expected, stream, indent=2, ensure_ascii=False)
    return expected


def verify_world_manifest(directory: Path, *, validate=False) -> dict:
    directory = Path(directory)
    path = directory / 'manifest.json'
    if not path.is_file():
        raise FileNotFoundError(f'{directory}: missing manifest.json')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('world') != directory.name:
        raise ValueError(f'{directory}: manifest world mismatch')
    config_path = directory / 'config.json'
    if not config_path.is_file() or sha256_file(config_path) != manifest.get('config_sha256'):
        raise ValueError(f'{directory}: config missing or hash mismatch')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config != manifest.get('config') or config.get('seed') != manifest.get('seed'):
        raise ValueError(f'{directory}: manifest config/seed mismatch')
    actual = check_world_files(directory)
    if actual != manifest.get('tables_sha256'):
        raise ValueError(f'{directory}: Parquet hash mismatch')
    if validate:
        validate_world(directory)
    return manifest


def lock_cohort(path: Path, worlds: list[tuple[str, str]], provenance: dict, split_protocol: dict,
                *, synthetic_root=SYNTH) -> dict:
    """A world belongs to exactly one split; an existing split is never edited."""
    path, synthetic_root = Path(path), Path(synthetic_root)
    if not worlds or len({name for name, _ in worlds}) != len(worlds):
        raise ValueError('World names must be nonempty and unique')
    if set(role for _, role in worlds) != set(ROLES):
        raise ValueError('Split needs train, validation and test worlds')
    origin = pd.Timestamp(split_protocol['origin'])
    horizon = int(split_protocol['label_horizon_days'])
    if horizon < 1 or int(split_protocol['train_stride_days']) < 1 or int(split_protocol['eval_stride_days']) < 1:
        raise ValueError('Invalid split stride/horizon')
    entries, seeds = [], []
    for name, role in worlds:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError(f'Invalid world name: {name}')
        directory = synthetic_root / name
        manifest = verify_world_manifest(directory)
        if any(manifest[key] != provenance[key] for key in
               ('commit', 'source_code_sha256', 'source_data_sha256')):
            raise ValueError(f'{name}: source/commit differs from cohort')
        cfg = manifest['config']
        if not (pd.Timestamp(cfg['start']) + pd.Timedelta(days=90) < origin <
                pd.Timestamp(cfg['end']) - pd.Timedelta(days=horizon)):
            raise ValueError(f'{name}: split origin lacks train history or observable test horizon')
        seeds.append(manifest['seed'])
        entries.append({'name': name, 'role': role,
                        'manifest_sha256': sha256_file(directory / 'manifest.json')})
    if len(set(seeds)) != len(seeds):
        raise ValueError('World seeds overlap across splits')
    cohort = {'schema_version': 1, 'commit': provenance['commit'],
              'source_code_sha256': provenance['source_code_sha256'],
              'source_data_sha256': provenance['source_data_sha256'],
              'split_protocol': split_protocol, 'worlds': entries}
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != cohort:
            raise ValueError('Split is already locked to different worlds or hashes')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as stream:
            json.dump(cohort, stream, indent=2, ensure_ascii=False)
    return cohort


def load_cohort(path: Path, *, synthetic_root=SYNTH) -> dict:
    path, synthetic_root = Path(path), Path(synthetic_root)
    cohort = json.loads(path.read_text(encoding='utf-8'))
    entries = cohort.get('worlds', [])
    if not {'origin', 'label_horizon_days', 'train_stride_days', 'eval_stride_days'} <= set(cohort.get('split_protocol', {})):
        raise ValueError('Cohort split protocol is missing')
    if len({row['name'] for row in entries}) != len(entries) or set(row['role'] for row in entries) != set(ROLES):
        raise ValueError('Cohort split is incomplete or duplicates a world')
    for row in entries:
        name = row['name']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError(f'Invalid world name: {name}')
        directory = synthetic_root / name
        if sha256_file(directory / 'manifest.json') != row['manifest_sha256']:
            raise ValueError(f'{name}: world manifest hash mismatch')
        manifest = verify_world_manifest(directory)
        for key in ('commit', 'source_code_sha256', 'source_data_sha256'):
            if manifest[key] != cohort[key]:
                raise ValueError(f'{name}: source/commit differs from locked cohort')
    return cohort
