"""Rebuild a synthetic reporting cache from unchanged raw sources, without truth files."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import uuid

from .feature_contract import cache_contract, sha, validate_cache
from .features import FEATURE_DESCRIPTIONS, build_features
from .generate import write_csv
from .rules import INPUT_TABLES, OPTIONAL_INPUT_TABLES
from .shadow_scoring import guarded, output_guard

EXCLUDED = {'features.csv', 'labels.csv', 'splits.csv', 'oracle.json', 'control_oracle.jsonl'}


def rebuild_cache(source, output):
    """Keep missing observation times missing; never attest invented source history."""
    source, output = guarded(source), guarded(output)
    output_guard(output, source, source/'unused-model')
    manifest_bytes = (source/'manifest.json').read_bytes()
    metadata = json.loads(manifest_bytes)
    if metadata.get('role') != 'reporting' or metadata.get('is_synthetic') is not True:
        raise ValueError('This migration accepts only synthetic reporting sources')
    source_manifest_sha = sha(source/'manifest.json')
    inputs = {}
    for name, entry in metadata['files'].items():
        if Path(name).name != name or '/' in name or '\\' in name or not name.endswith('.csv'):
            raise ValueError('Cache migration requires plain CSV source filenames')
        if name in EXCLUDED:
            continue
        expected = entry['sha256'] if isinstance(entry, dict) else entry
        path = guarded(source/name)
        if not path.is_relative_to(source) or sha(path) != expected:
            raise ValueError('Raw source checksum mismatch: '+name)
        inputs[name] = expected
    if not {name+'.csv' for name in INPUT_TABLES} <= inputs.keys():
        raise ValueError('Required raw feature source tables are missing')
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.parent/('.feature-rebuild-'+uuid.uuid4().hex)
    staged.mkdir()
    try:
        tables, files = {}, {}
        for name, expected in inputs.items():
            shutil.copyfile(source/name, staged/name)
            if sha(staged/name) != expected:
                raise ValueError('Raw source changed while copying: '+name)
            with (staged/name).open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            files[name] = dict(rows=len(rows), sha256=expected)
            if Path(name).stem in set(INPUT_TABLES+OPTIONAL_INPUT_TABLES):
                tables[Path(name).stem] = rows
        features = build_features(tables)
        write_csv(staged/'features.csv', features, ['transaction_id', *FEATURE_DESCRIPTIONS])
        files['features.csv'] = dict(rows=len(features), sha256=sha(staged/'features.csv'))
        rebuilt = dict(metadata, files=files, feature_columns=list(FEATURE_DESCRIPTIONS),
                       feature_contract=cache_contract(files))
        rebuilt['feature_derivation'] = dict(version='raw-source-cache-rebuild-v1',
            source=str(source), source_manifest_sha256=source_manifest_sha,
            input_sha256=inputs, raw_values_and_timestamps_modified=False,
            missing_observation_times='remain_unknown_and_masked_by_feature_policy',
            labels_loaded=False, splits_loaded=False, oracle_loaded=False)
        validate_cache(rebuilt)
        (staged/'manifest.json').write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if sha(source/'manifest.json') != source_manifest_sha or any(sha(source/n) != h for n,h in inputs.items()):
            raise ValueError('Source changed before cache publication')
        if output.exists():
            raise FileExistsError('Output appeared during rebuild; refusing replacement')
        staged.rename(output)
    finally:
        if staged.exists():
            # This exact, newly created staging directory is the only cleanup target.
            for path in staged.iterdir():
                path.unlink()
            staged.rmdir()
    return dict(output=str(output), observations=len(features), feature_count=len(FEATURE_DESCRIPTIONS),
                feature_contract_fingerprint=rebuilt['feature_contract']['fingerprint'],
                source_manifest_sha256=source_manifest_sha, manifest_sha256=sha(output/'manifest.json'),
                raw_sources_unchanged=True, labels_loaded=False, splits_loaded=False, oracle_loaded=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    print(json.dumps(rebuild_cache(args.source,args.output),ensure_ascii=False))


if __name__=='__main__':main()
