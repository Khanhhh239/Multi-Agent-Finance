"""Gated v3 pipeline: sources -> smoke -> contracts -> worlds -> split -> train -> evaluate."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import (create_world_manifest, lock_cohort,
                                        source_provenance, verify_world_manifest)
from agent1.paths import OUT, SYNTH
from agent1.synth.shocks import ShockEpisode
from agent1.synth.world import World, WorldConfig
from scripts.audit_train_readiness import audit_world
from scripts.train_manifest import train, evaluate

STAGES = ('sources', 'smoke', 'validate_smoke', 'worlds', 'audit_worlds',
          'lock_split', 'train', 'evaluate')


def assess_readiness(audited, evidence, *, start, end, scenario_holdout_present=False,
                     world_regimes=None):
    """Internal sanity gate; passing does not establish Vietnamese market fidelity."""
    full_window = pd.Timestamp(start) <= pd.Timestamp('2019-01-01') and \
                  pd.Timestamp(end) >= pd.Timestamp('2025-12-31')
    ratios = [row['net_revenue_ratio_2025_to_2019'] for row in audited
              if row['net_revenue_ratio_2025_to_2019'] is not None]
    regimes = world_regimes or {}
    baseline_ratios = [row['net_revenue_ratio_2025_to_2019'] for row in audited
                       if row['net_revenue_ratio_2025_to_2019'] is not None and
                       regimes.get(row.get('world'), 'baseline') == 'baseline']
    stress_ratios = [row['net_revenue_ratio_2025_to_2019'] for row in audited
                     if row['net_revenue_ratio_2025_to_2019'] is not None and
                     regimes.get(row.get('world')) == 'stress']
    readiness = {
        'full_2019_2025_window': full_window,
        'external_macro_inputs_present': all(evidence['source_data_sha256'].get(key)
                                             for key in ('oxcgrt', 'wdi')),
        'scenario_holdout_present': bool(scenario_holdout_present),
        'min_2025_to_2019_revenue_ratio': min(ratios, default=None),
        'baseline_min_2025_to_2019_revenue_ratio': min(baseline_ratios, default=None),
        'stress_min_2025_to_2019_revenue_ratio': min(stress_ratios, default=None),
        'world_regimes': regimes,
        'worlds': audited,
    }
    readiness['passed'] = (readiness['scenario_holdout_present'] and
                           (not full_window or
                            (readiness['external_macro_inputs_present'] and
                             readiness['baseline_min_2025_to_2019_revenue_ratio'] is not None and
                             readiness['baseline_min_2025_to_2019_revenue_ratio'] >= .6 and
                             (not stress_ratios or min(stress_ratios) > 0))))
    return readiness


def episode_schedule(start, end):
    """Train/validation mechanisms; credit is reserved for held-out test."""
    weeks = pd.date_range(pd.Timestamp(start) - pd.Timedelta(days=pd.Timestamp(start).weekday()),
                          end, freq='W-MON')
    if len(weeks) < 28:
        raise ValueError('Integrated shock worlds need at least 28 weeks')
    starts = [weeks[int((len(weeks) - 16) * fraction)] for fraction in (.12, .35, .58)]
    return [ShockEpisode(family=family, start=str(day.date()), severity=severity,
                         reference_event='synthetic_v3_assumption')
            for family, day, severity in zip(('demand', 'supply', 'price'),
                                             starts, (1.1, 1.0, .8))]


def heldout_schedule(origin, scenario):
    """Two distinct test-only paths; synthetic severities are not market estimates."""
    first = pd.Timestamp(origin) + pd.Timedelta(days=(7 - pd.Timestamp(origin).weekday()) % 7)
    if scenario == 0:
        return [ShockEpisode('credit', str(first.date()), rise_weeks=1,
                             peak_weeks=6, recovery_weeks=9, severity=1.3,
                             reference_event='heldout_credit_only_v1')]
    if scenario == 1:
        start = str((first + pd.Timedelta(weeks=4)).date())
        return [ShockEpisode(family, start, rise_weeks=3, peak_weeks=4,
                             recovery_weeks=10, severity=severity,
                             reference_event='heldout_price_credit_compound_v1')
                for family, severity in (('price', .9), ('credit', 1.1))]
    raise ValueError(f'Unknown held-out scenario: {scenario}')


def audit_heldout_scenarios(worlds, synthetic_root, origin, end):
    """Inspect scenario truth only, never test invoice outcomes before split lock."""
    familiar = {episode.family for config, role in worlds if role != 'test'
                for episode in config.shock_schedule}
    tests = [(config, pd.read_parquet(Path(synthetic_root) / config.name /
                                      'shock_truth.parquet'))
             for config, role in worlds if role == 'test']
    last_cutoff = pd.Timestamp(end) - pd.Timedelta(days=120)
    entries = []
    for config, truth in tests:
        active = truth[truth.strength.gt(0) & truth.week.between(origin, last_cutoff)]
        configured = {episode.family for episode in config.shock_schedule}
        entries.append({'world': config.name,
                        'families': sorted(configured),
                        'reference_events': sorted(set(truth.reference_event)),
                        'active_heldout_weeks_at_eval': int(active.loc[
                            ~active.family.isin(familiar), 'week'].nunique())})
    heldout = set().union(*(set(row['families']) for row in entries)) - familiar
    distinct = len({tuple(row['reference_events']) for row in entries}) == len(entries)
    return {'train_validation_families': sorted(familiar),
            'heldout_families': sorted(heldout), 'test_scenarios': entries,
            'passed': bool(len(entries) >= 2 and heldout and distinct and
                           all(row['active_heldout_weeks_at_eval'] > 0 for row in entries))}


def world_configs(prefix, *, start, end, origin, firms, train_worlds,
                  validation_worlds=2, base_seed, calibration):
    if not prefix.startswith('v3_') or not prefix.replace('_', '').isalnum():
        raise ValueError('Use a new alphanumeric v3_ prefix')
    if firms < 1 or train_worlds < 1 or validation_worlds < 1:
        raise ValueError('Need positive firms and at least one train and validation world')
    shared = dict(start=start, end=end, write_xml=0, rng_version=3,
                  supplier_cash_firm_p=.20,
                  ontime_shift=calibration['ontime_shift'], pd_mult=calibration['pd_mult'],
                  shock_schedule=episode_schedule(start, end))
    smoke = WorldConfig(name=f'{prefix}_smoke', seed=base_seed, n_firms=1,
                        macro_regime='baseline', **shared)
    roles = ([('train', i) for i in range(train_worlds)] +
             [('validation', i) for i in range(validation_worlds)] +
             [('test', 0), ('test', 1)])
    worlds = []
    for index, (role, ordinal) in enumerate(roles, start=1):
        config = WorldConfig(name=f'{prefix}_{role}_{ordinal:03d}', seed=base_seed + index,
                             n_firms=firms, tail=('atradius', 'uk', 'coface')[index % 3],
                             late_scale=(1., 1.15, .9)[index % 3],
                             macro_regime=('stress' if role != 'test' and ordinal % 2 else 'baseline'),
                             **{**shared, 'shock_schedule': heldout_schedule(origin, ordinal)
                                if role == 'test' else shared['shock_schedule']})
        worlds.append((config, role))
    return smoke, worlds


def build_or_verify(config, provenance, *, synthetic_root):
    directory = Path(synthetic_root) / config.name
    if directory.exists():
        manifest = verify_world_manifest(directory, validate=True)
        if manifest['config'] != json.loads(json.dumps(asdict(config))):
            raise ValueError(f'{config.name}: existing config differs; choose a new prefix')
        for key in ('commit', 'source_code_sha256', 'source_data_sha256'):
            if manifest[key] != provenance[key]:
                raise ValueError(f'{config.name}: source changed; choose a new prefix')
    else:
        World(config).run(directory, verbose=False)
        manifest = create_world_manifest(directory, provenance)
    return manifest


def run_pipeline(*, prefix='v3_final', start='2019-01-01', end='2025-12-31',
                 origin='2024-07-01', firms=40, train_worlds=2,
                 validation_worlds=2, base_seed=93000,
                 rounds=200, max_rows=50000, stop_after='evaluate',
                 synthetic_root=SYNTH, output_root=OUT / 'data', provenance=None,
                 calibration_path=None):
    if stop_after not in STAGES:
        raise ValueError(f'Unknown stage: {stop_after}')
    if (pd.Timestamp(start) <= pd.Timestamp('2019-01-01') and
            pd.Timestamp(end) >= pd.Timestamp('2025-12-31') and
            (train_worlds < 2 or validation_worlds < 2)):
        raise ValueError('Full-window release needs baseline and stress in both train and validation')
    synthetic_root, output_root = Path(synthetic_root), Path(output_root)
    calibration_path = Path(calibration_path) if calibration_path else SYNTH / 'calibration_fit.json'
    evidence = source_provenance(sources={
        'calibration': calibration_path,
        'oxcgrt': Path(__file__).resolve().parents[1] / 'data/raw/oxcgrt/OxCGRT_compact_national_v1.csv',
        'wdi': Path(__file__).resolve().parents[1] / 'data/raw/wdi_vn/wdi_vietnam.csv',
    }) if provenance is None else provenance
    calibration = json.loads(calibration_path.read_text(encoding='utf-8'))
    smoke, worlds = world_configs(prefix, start=start, end=end, origin=origin, firms=firms,
                                  train_worlds=train_worlds, validation_worlds=validation_worlds,
                                  base_seed=base_seed,
                                  calibration=calibration)
    output = output_root / prefix
    protocol = {
        'source_code_sha256': evidence['source_code_sha256'],
        'rng_version': 3,
        'supplier_cash_firm_p': .20,
        'supplier_cash_firm_p_basis': 'explicit simulation assumption; not a Vietnamese SME estimate',
        'baseline_common_factor': 'weekly Student-t AR(1) path clipped to [-0.8, 0.8]',
        'stress_common_factor': 'unclipped path capped above by fixed -0.6 sine wave in final calendar year; worse paths unchanged',
        'assignment_rule': 'train and validation even ordinal baseline, odd ordinal stress; tests baseline',
        'worlds': [{'name': config.name, 'role': role, 'seed': config.seed,
                    'macro_regime': config.macro_regime} for config, role in worlds],
    }
    cohort_path = synthetic_root / f'{prefix}_cohort.json'
    steps = {'sources': evidence}
    if stop_after == 'sources':
        return steps
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / 'scenario_protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text(encoding='utf-8')) != protocol:
        raise ValueError('Existing scenario protocol differs; choose a new prefix')
    if not protocol_path.exists():
        protocol_path.write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding='utf-8')
    steps['scenario_protocol'] = str(protocol_path)
    build_or_verify(smoke, evidence, synthetic_root=synthetic_root)
    steps['smoke'] = smoke.name
    if stop_after == 'smoke':
        return steps
    verify_world_manifest(synthetic_root / smoke.name, validate=True)
    steps['validate_smoke'] = True
    if stop_after == 'validate_smoke':
        return steps
    for config, role in worlds:
        build_or_verify(config, evidence, synthetic_root=synthetic_root)
    steps['worlds'] = [config.name for config, _ in worlds]
    if stop_after == 'worlds':
        return steps
    audited = [audit_world(synthetic_root / config.name) for config, role in worlds
               if role != 'test']
    holdout = audit_heldout_scenarios(worlds, synthetic_root, origin, end)
    readiness = assess_readiness(audited, evidence, start=start, end=end,
                                 scenario_holdout_present=holdout['passed'],
                                 world_regimes={config.name: config.macro_regime
                                                for config, role in worlds if role != 'test'})
    readiness['scenario_holdout'] = holdout
    output.mkdir(parents=True, exist_ok=True)
    (output / 'readiness.json').write_text(json.dumps(readiness, indent=2,
                                                    ensure_ascii=False), encoding='utf-8')
    steps['audit_worlds'] = str(output / 'readiness.json')
    if stop_after == 'audit_worlds':
        return steps
    if not readiness['passed']:
        raise ValueError('World readiness failed; inspect readiness.json before locking a train split')
    protocol = {'origin': str(pd.Timestamp(origin).date()), 'label_horizon_days': 120,
                'train_stride_days': 28, 'eval_stride_days': 28}
    lock_cohort(cohort_path, [(config.name, role) for config, role in worlds],
                evidence, protocol, synthetic_root=synthetic_root)
    steps['lock_split'] = str(cohort_path)
    if stop_after == 'lock_split':
        return steps
    steps['train'] = train(cohort_path, output, synthetic_root=synthetic_root,
                           rounds=rounds, max_rows=max_rows)
    if stop_after == 'train':
        return steps
    steps['evaluate'] = evaluate(cohort_path, output, synthetic_root=synthetic_root).to_dict('records')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'run_summary.json').write_text(json.dumps(steps, indent=2, ensure_ascii=False), encoding='utf-8')
    return steps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', default='v3_final')
    parser.add_argument('--start', default='2019-01-01')
    parser.add_argument('--end', default='2025-12-31')
    parser.add_argument('--origin', default='2024-07-01')
    parser.add_argument('--firms', type=int, default=40)
    parser.add_argument('--train-worlds', type=int, default=2)
    parser.add_argument('--validation-worlds', type=int, default=2)
    parser.add_argument('--base-seed', type=int, default=93000)
    parser.add_argument('--rounds', type=int, default=200)
    parser.add_argument('--max-rows', type=int, default=50000)
    parser.add_argument('--stop-after', choices=STAGES, default='evaluate')
    args = parser.parse_args()
    print(json.dumps(run_pipeline(prefix=args.prefix, start=args.start, end=args.end,
                                  origin=args.origin, firms=args.firms,
                                  train_worlds=args.train_worlds,
                                  validation_worlds=args.validation_worlds,
                                  base_seed=args.base_seed,
                                  rounds=args.rounds, max_rows=args.max_rows,
                                  stop_after=args.stop_after), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
