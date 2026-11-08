"""Train and evaluate T1 from a locked list of worlds, never from src/tgt names."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import code_provenance, load_cohort, sha256_file
from agent1.models.features import SnapshotBuilder, add_labels, model_snapshot_view
from agent1.models import t1
from agent1.paths import SYNTH


def _rows(directory: Path, origin, *, role: str, protocol: dict) -> pd.DataFrame:
    config = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
    start, end = pd.Timestamp(config['start']), pd.Timestamp(config['end'])
    origin = pd.Timestamp(origin)
    horizon = pd.Timedelta(days=int(protocol['label_horizon_days']))
    if role == 'train':
        first, last = start + pd.Timedelta(days=90), origin - horizon - pd.Timedelta(days=7)
        stride, label_end = int(protocol['train_stride_days']), origin
    else:
        first, last = origin, end - horizon
        stride, label_end = int(protocol['eval_stride_days']), end
    cutoffs = pd.date_range(first, last, freq=f'{stride}D')
    if not len(cutoffs):
        raise ValueError(f'{directory.name}: no {role} cutoff')
    invoices = pd.read_parquet(directory / 'invoices.parquet')
    payments = pd.read_parquet(directory / 'payments.parquet')
    promises = pd.read_parquet(directory / 'promises.parquet')
    builder = SnapshotBuilder(invoices, payments, promises)
    parts = []
    for cutoff in cutoffs:
        raw = builder.snapshot(cutoff)
        if raw.empty:
            continue
        visible = model_snapshot_view(raw, cutoff)
        labels = raw[['label_date', 'writeoff_date']]
        parts.append(pd.concat([visible, labels], axis=1))
    if not parts:
        raise ValueError(f'{directory.name}: no open invoices at {role} cutoffs')
    return add_labels(pd.concat(parts, ignore_index=True), label_end)


def train(cohort_path: Path, output: Path, *, synthetic_root=SYNTH,
          rounds=200, max_rows=50000) -> dict:
    cohort_path, output = Path(cohort_path), Path(output)
    cohort = load_cohort(cohort_path, synthetic_root=synthetic_root)
    current = code_provenance()
    if any(cohort[key] != current[key] for key in current):
        raise ValueError('Current code/commit differs from locked cohort')
    cohort_hash = sha256_file(cohort_path)
    metadata_path, model_path = output / 'train.json', output / 'model.txt'
    expected = {'cohort_sha256': cohort_hash, 'rounds': rounds, 'max_rows': max_rows,
                'train_worlds': [row['name'] for row in cohort['worlds'] if row['role'] == 'train']}
    if metadata_path.exists() or model_path.exists():
        if not (metadata_path.exists() and model_path.exists()):
            raise ValueError('Incomplete existing model artifact')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if any(metadata.get(key) != value for key, value in expected.items()) or \
                sha256_file(model_path) != metadata.get('model_sha256'):
            raise ValueError('Existing model does not match locked cohort/training settings')
        return metadata
    frames = [_rows(Path(synthetic_root) / row['name'], cohort['split_protocol']['origin'],
                    role='train', protocol=cohort['split_protocol'])
              for row in cohort['worlds'] if row['role'] == 'train']
    frame = pd.concat(frames, ignore_index=True)
    if len(frame) > max_rows:
        frame = frame.sample(max_rows, random_state=7).reset_index(drop=True)
    if len(frame) < 30 or not frame['event'].any():
        raise ValueError('Insufficient mature training observations')
    model = t1.HazardGBM(dict(min_data_in_leaf=20, num_leaves=31), rounds=rounds).fit(frame)
    output.mkdir(parents=True, exist_ok=True)
    model.booster.save_model(str(model_path))
    metadata = {**expected, 'n_rows': len(frame), 'n_events': int(frame['event'].sum()),
                'model_sha256': sha256_file(model_path), 'commit': cohort['commit'],
                'source_code_sha256': cohort['source_code_sha256'],
                'features': model.feats}
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return metadata


def evaluate(cohort_path: Path, output: Path, *, synthetic_root=SYNTH) -> pd.DataFrame:
    import lightgbm as lgb

    cohort_path, output = Path(cohort_path), Path(output)
    cohort = load_cohort(cohort_path, synthetic_root=synthetic_root)
    current = code_provenance()
    if any(cohort[key] != current[key] for key in current):
        raise ValueError('Current code/commit differs from locked cohort')
    metadata = json.loads((output / 'train.json').read_text(encoding='utf-8'))
    model_path = output / 'model.txt'
    if metadata['cohort_sha256'] != sha256_file(cohort_path) or \
            metadata['model_sha256'] != sha256_file(model_path):
        raise ValueError('Model artifact does not belong to locked cohort')
    model = t1.HazardGBM(feats=metadata['features'])
    model.booster = lgb.Booster(model_file=str(model_path))
    rows = []
    for entry in cohort['worlds']:
        if entry['role'] == 'train':
            continue
        frame = _rows(Path(synthetic_root) / entry['name'], cohort['split_protocol']['origin'],
                      role=entry['role'], protocol=cohort['split_protocol'])
        prediction = t1.quantiles_from_hazard(model.hazards(frame))
        baseline = t1.b1_dist(frame)
        for name, quantiles in (('DH-GBM', prediction), ('B1d', baseline)):
            measured = t1.evaluate_quantiles(frame['remaining'].to_numpy(), quantiles)
            rows.append({'world': entry['name'], 'role': entry['role'], 'model': name,
                         'n': len(frame), 'cohort_sha256': metadata['cohort_sha256'],
                         **{key: float(value) for key, value in measured.items()
                            if np.isscalar(value)}})
    result = pd.DataFrame(rows)
    result.to_csv(output / 'evaluation.csv', index=False)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['train', 'evaluate'])
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=200)
    parser.add_argument('--max-rows', type=int, default=50000)
    args = parser.parse_args()
    if args.stage == 'train':
        print(json.dumps(train(args.manifest, args.output, rounds=args.rounds,
                               max_rows=args.max_rows), indent=2))
    else:
        print(evaluate(args.manifest, args.output).to_string(index=False))


if __name__ == '__main__':
    main()
