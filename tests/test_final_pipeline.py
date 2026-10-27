"""End-to-end gates for a manifest-driven synthetic training cohort."""
import json
from dataclasses import replace
from pathlib import Path
import sys

import pandas as pd
import pytest

from agent1.data.world_manifest import (check_world_files, load_cohort,
                                        lock_cohort, verify_world_manifest)
from agent1.synth.shocks import ShockEpisode
from agent1.synth.world import World, WorldConfig
from scripts.build_final_train import (assess_readiness, audit_heldout_scenarios,
                                       run_pipeline, world_configs)
from scripts.train_manifest import train, evaluate
from scripts import world_registry


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp('final_cohort')
    synthetic = root / 'synthetic'
    synthetic.mkdir()
    calibration = root / 'calibration_fit.json'
    calibration.write_text(json.dumps({'ontime_shift': {}, 'pd_mult': {}}), encoding='utf-8')
    options = dict(prefix='v3_contract', start='2023-01-01', end='2024-12-31',
                   origin='2024-07-01', firms=1, train_worlds=1,
                   validation_worlds=1, base_seed=95100,
                   synthetic_root=synthetic, output_root=root / 'outputs',
                   calibration_path=calibration)
    steps = run_pipeline(**options, stop_after='lock_split')
    return root, synthetic, options, steps


def test_world_manifests_and_split_are_locked(built):
    root, synthetic, options, steps = built
    cohort_path = Path(steps['lock_split'])
    cohort = load_cohort(cohort_path, synthetic_root=synthetic)
    assert [row['role'] for row in cohort['worlds']] == ['train', 'validation', 'test', 'test']
    assert len({row['name'] for row in cohort['worlds']}) == 4
    readiness = json.loads((root / 'outputs' / 'v3_contract' / 'readiness.json').read_text())
    assert readiness['scenario_holdout']['heldout_families'] == ['credit']
    assert json.loads((root / 'outputs' / 'v3_contract' / 'scenario_protocol.json').read_text())['rng_version'] == 3
    assert len(readiness['scenario_holdout']['test_scenarios']) == 2
    assert all(row['active_heldout_weeks_at_eval'] > 0 for row in
               readiness['scenario_holdout']['test_scenarios'])
    assert len(readiness['worlds']) == 2  # No test invoice outcomes in pre-lock audit.
    for row in cohort['worlds']:
        manifest = verify_world_manifest(synthetic / row['name'])
        assert manifest['seed'] == manifest['config']['seed']
        assert manifest['commit'] == cohort['commit']
        assert manifest['source_data_sha256']['calibration']
        assert len(manifest['tables_sha256']) == len(check_world_files(synthetic / row['name']))
    with pytest.raises(ValueError, match='Split is already locked'):
        lock_cohort(cohort_path, [(row['name'], row['role']) for row in cohort['worlds']],
                    steps['sources'], {**cohort['split_protocol'], 'train_stride_days': 14},
                    synthetic_root=synthetic)


def test_registry_and_train_fail_on_missing_or_changed_parquet(built, monkeypatch):
    root, synthetic, _, steps = built
    name = load_cohort(steps['lock_split'], synthetic_root=synthetic)['worlds'][0]['name']
    table = synthetic / name / 'invoices.parquet'
    original = table.read_bytes()
    table.unlink()
    try:
        monkeypatch.setattr(sys, 'argv', ['world_registry.py', '--cohort', steps['lock_split'],
                                       '--synthetic-root', str(synthetic),
                                       '--output', str(root / 'registry.csv')])
        with pytest.raises(FileNotFoundError, match='missing Parquet'):
            world_registry.main()
        with pytest.raises(FileNotFoundError, match='missing Parquet'):
            train(steps['lock_split'], root / 'model', synthetic_root=synthetic, rounds=5)
    finally:
        table.write_bytes(original)
    table.write_bytes(original + b'changed')
    try:
        with pytest.raises(ValueError, match='Parquet hash mismatch'):
            verify_world_manifest(synthetic / name)
    finally:
        table.write_bytes(original)


def test_train_and_evaluate_read_only_manifest_roles(built):
    root, synthetic, _, steps = built
    cohort_path = Path(steps['lock_split'])
    output = root / 'model'
    metadata = train(cohort_path, output, synthetic_root=synthetic, rounds=5, max_rows=3000)
    assert metadata['train_worlds'] == ['v3_contract_train_000']
    result = evaluate(cohort_path, output, synthetic_root=synthetic)
    assert set(result['role']) == {'validation', 'test'}
    assert set(result['model']) == {'DH-GBM', 'B1d'}
    assert result['n'].gt(0).all()
    assert pd.read_csv(output / 'evaluation.csv').shape == result.shape


def test_train_rejects_changed_code_after_split_lock(built, monkeypatch):
    from scripts import train_manifest
    root, synthetic, _, steps = built
    monkeypatch.setattr(train_manifest, 'code_provenance',
                        lambda: {'commit': '0' * 40, 'source_code_sha256': 'changed'})
    with pytest.raises(ValueError, match='Current code/commit'):
        train_manifest.train(steps['lock_split'], root / 'changed_code_model',
                             synthetic_root=synthetic, rounds=5)


def test_full_train_cannot_be_locked_with_missing_macro_or_revenue_collapse():
    row = {'net_revenue_ratio_2025_to_2019': .32}
    evidence = {'source_data_sha256': {'oxcgrt': None, 'wdi': None}}
    failed = assess_readiness([row], evidence, start='2019-01-01', end='2025-12-31')
    assert not failed['passed']
    assert failed['min_2025_to_2019_revenue_ratio'] == .32
    evidence['source_data_sha256'] = {'oxcgrt': 'verified-hash', 'wdi': 'verified-hash'}
    assert not assess_readiness([row], evidence, start='2019-01-01',
                                end='2025-12-31')['passed']
    assert not assess_readiness([{'net_revenue_ratio_2025_to_2019': .9}], evidence,
                                start='2019-01-01', end='2025-12-31')['passed']
    assert assess_readiness([{'net_revenue_ratio_2025_to_2019': .9}], evidence,
                            start='2019-01-01', end='2025-12-31',
                            scenario_holdout_present=True)['passed']
    mixed = [{'world': 'baseline', 'net_revenue_ratio_2025_to_2019': .9},
             {'world': 'stress', 'net_revenue_ratio_2025_to_2019': .35}]
    checked = assess_readiness(mixed, evidence, start='2019-01-01', end='2025-12-31',
                               scenario_holdout_present=True,
                               world_regimes={'baseline': 'baseline', 'stress': 'stress'})
    assert checked['passed'] and checked['min_2025_to_2019_revenue_ratio'] == .35
    assert checked['baseline_min_2025_to_2019_revenue_ratio'] == .9
    assert not assess_readiness([], evidence, start='2023-01-01',
                                end='2024-12-31')['passed']


def test_credit_family_and_compound_scenario_are_test_only():
    _, worlds = world_configs('v3_holdout_contract', start='2019-01-01',
                              end='2025-12-31', origin='2024-07-01', firms=2,
                              train_worlds=2, validation_worlds=2, base_seed=96000,
                              calibration={'ontime_shift': {}, 'pd_mult': {}})
    assert [role for _, role in worlds] == ['train', 'train', 'validation', 'validation', 'test', 'test']
    assert [(role, config.macro_regime) for config, role in worlds] == [
        ('train', 'baseline'), ('train', 'stress'),
        ('validation', 'baseline'), ('validation', 'stress'),
        ('test', 'baseline'), ('test', 'baseline')]
    assert worlds[1][0].seed == 96002  # Seed assignment is fixed before outcomes.
    familiar = {episode.family for config, role in worlds if role != 'test'
                for episode in config.shock_schedule}
    assert familiar == {'demand', 'supply', 'price'}
    test = [config for config, role in worlds if role == 'test']
    assert [{episode.family for episode in config.shock_schedule} for config in test] == [
        {'credit'}, {'price', 'credit'}]
    assert {episode.reference_event for config in test for episode in config.shock_schedule} == {
        'heldout_credit_only_v1', 'heldout_price_credit_compound_v1'}
    assert len({config.seed for config, _ in worlds}) == len(worlds)


def test_macro_regimes_are_predeclared_and_stress_the_final_year():
    base = World(WorldConfig(seed=94319, macro_regime='baseline')).macro()
    stress = World(WorldConfig(seed=94319, macro_regime='stress')).macro()
    raw = World(WorldConfig(seed=94319, macro_regime='unrestricted')).macro()
    assert base.common_factor.abs().max() <= .8
    final = stress.week.dt.year.eq(2025)
    assert stress.loc[final, 'common_factor'].mean() < base.loc[final, 'common_factor'].mean()
    deep = final & raw.common_factor.lt(-.6)
    pd.testing.assert_series_equal(stress.loc[deep, 'common_factor'],
                                   raw.loc[deep, 'common_factor'])


def test_heldout_gate_rejects_family_leakage_or_inactive_test_window(built):
    _, synthetic, options, _ = built
    _, worlds = world_configs(options['prefix'], start=options['start'],
                              end=options['end'], origin=options['origin'],
                              firms=options['firms'], train_worlds=options['train_worlds'],
                              validation_worlds=options['validation_worlds'],
                              base_seed=options['base_seed'],
                              calibration={'ontime_shift': {}, 'pd_mult': {}})
    assert audit_heldout_scenarios(worlds, synthetic, options['origin'],
                                   options['end'])['passed']
    first, role = worlds[0]
    leaked = [(replace(first, shock_schedule=[*first.shock_schedule,
               ShockEpisode('credit', '2024-04-01')]), role), *worlds[1:]]
    assert not audit_heldout_scenarios(leaked, synthetic, options['origin'],
                                       options['end'])['passed']
    assert not audit_heldout_scenarios(worlds, synthetic, '2024-11-01',
                                       options['end'])['passed']
