"""Regenerate isolated cohorts after lifecycle changes; keep earlier audits intact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import create_world_manifest, source_provenance, verify_world_manifest
from agent1.paths import OUT, SYNTH
from agent1.synth.hard_cases import HardCaseWorld
from agent1.synth.world import World, WorldConfig
from scripts.audit_train_readiness import audit_world


def build(directory, world, provenance):
    if directory.exists():
        manifest = verify_world_manifest(directory, validate=True)
        if manifest['source_code_sha256'] != provenance['source_code_sha256']:
            raise ValueError(f'{directory}: code changed; use a new name')
    else:
        world.run(directory, verbose=False)
        create_world_manifest(directory, provenance)
    return directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, nargs='*', default=[94317, 94318, 94319])
    parser.add_argument('--firms', type=int, default=24)
    parser.add_argument('--hard-cases', action='store_true')
    parser.add_argument('--skip-controls', action='store_true')
    parser.add_argument('--hard-case-version', default='v4')
    parser.add_argument('--control-version', default='v4')
    parser.add_argument('--cases', nargs='*', default=['heterogeneity', 'lumpy_customer'])
    args = parser.parse_args()
    if args.firms < 1 or not args.seeds:
        raise ValueError('Need at least one seed and a positive firm count')
    original = json.loads((SYNTH / 'v3_audit_public_macro_20261026' / 'config.json').read_text(encoding='utf-8'))
    provenance = source_provenance()
    rows = []
    for seed in ([] if args.skip_controls else args.seeds):
        config = WorldConfig(**{**original, 'name': f'{args.control_version}_lifecycle_control_{seed}',
                                'seed': seed, 'n_firms': args.firms})
        directory = build(SYNTH / config.name, World(config), provenance)
        metric = audit_world(directory)
        events = pd.read_parquet(directory / 'events.parquet')
        metric['lifecycle_event_counts'] = events.type.value_counts().loc[
            lambda counts: counts.index.isin(['customer_acquired', 'customer_churned',
                                               'customer_returned', 'seller_default_release'])].to_dict()
        rows.append(metric)
        print(config.name, metric['net_revenue_ratio_2025_to_2019'], flush=True)
    cases = {}
    if args.hard_cases:
        for case in args.cases:
            if case not in ('heterogeneity', 'lumpy_customer'):
                raise ValueError(f'Unsupported audit case: {case}')
            config = WorldConfig(name=f'hc_{case}_{args.hard_case_version}_lifecycle_20261026', seed=901,
                                 n_firms=12, write_xml=0, rng_version=2)
            world = HardCaseWorld(config, case)
            directory = build(SYNTH / config.name, world, provenance)
            invoices = pd.read_parquet(directory / 'invoices.parquet')
            if case == 'heterogeneity':
                paid = invoices[invoices.paid_date_true.notna()].copy()
                paid['delay'] = (paid.paid_date_true - paid.due_date).dt.days.clip(-60, 240)
                firm_mean = paid.groupby('firm_id').delay.transform('mean')
                customer_mean = paid.groupby(['firm_id', 'customer_id']).delay.transform('mean')
                cases[case] = {'customer_between_variance_share': float(
                    ((customer_mean - firm_mean) ** 2).sum() /
                    max(((paid.delay - firm_mean) ** 2).sum(), 1e-9))}
            else:
                customers = pd.read_parquet(directory / 'customers.parquet')
                anchors = set(customers.loc[customers.is_anchor, 'customer_id'])
                shares = (invoices[invoices.customer_id.isin(anchors)]
                          .groupby('firm_id').amount_gross.sum() /
                          invoices.groupby('firm_id').amount_gross.sum())
                cases[case] = {'firms_in_40_60_share': int(shares.between(.4, .6).sum()),
                               'firm_count': len(shares), 'min_share': float(shares.min()),
                               'median_share': float(shares.median()),
                               'max_share': float(shares.max())}
            print(config.name, cases[case], flush=True)
    output = OUT / 'data' / (f'{args.hard_case_version}_lifecycle_audit_20261026.json'
                             if args.skip_controls else
                             f'{args.control_version}_lifecycle_audit_20261026.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'controls': rows, 'hard_cases': cases}, indent=2,
                                 ensure_ascii=False), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
