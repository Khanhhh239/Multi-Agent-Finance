"""Regenerate a versioned short-pay-fixed cohort with four synthetic shock replays.

The named historical events inspire mechanisms; episode magnitudes and payment
effects remain simulation assumptions, not historical SME invoice observations.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import lock_cohort, source_provenance, verify_world_manifest
from agent1.paths import OUT, RAW, SYNTH
from agent1.synth.shocks import ShockEpisode
from agent1.synth.world import WorldConfig
from scripts.audit_train_readiness import audit_world
from scripts.build_final_train import assess_readiness, build_or_verify
from scripts.train_manifest import evaluate, train

PREFIX = 'v4_shortpay_4shock_20261028'
DESIGN = SYNTH / f'{PREFIX}_design.json'
STAGES = ('sources', 'smoke', 'worlds', 'audit_worlds', 'lock_split', 'train', 'evaluate')


def episodes(item: dict, shift_weeks: int = 0) -> list[ShockEpisode]:
    start = pd.Timestamp(item['replay_start']) + pd.Timedelta(weeks=shift_weeks)
    if start.weekday():
        raise ValueError(f'Non-Monday replay: {start}')
    return [ShockEpisode(start=str(start.date()), reference_event=item['reference_event'],
                         **spec) for spec in item['episodes']]


def configs(design: dict, calibration: dict, *, firms: int, base_seed: int):
    shared = dict(start='2019-01-01', end='2025-12-31', n_firms=firms,
                  write_xml=0, rng_version=3, supplier_cash_firm_p=.20,
                  ontime_shift=calibration['ontime_shift'], pd_mult=calibration['pd_mult'])
    smoke = WorldConfig(name=f'{PREFIX}_smoke', seed=base_seed, n_firms=1,
                        shock_schedule=[episode for item in design['training_replays']
                                        for episode in episodes(item)],
                        **{key: value for key, value in shared.items() if key != 'n_firms'})
    roles = [('train', i) for i in range(4)] + [('validation', i) for i in range(2)] + [
        ('test', 0), ('test', 1)]
    worlds = []
    for index, (role, ordinal) in enumerate(roles, start=1):
        # Replay shifts are fixed before data generation and remain within train history.
        shift = (0, 3, -2, 5)[ordinal] if role == 'train' else (1, -3)[ordinal]
        if role == 'test':
            shift = (2, -1)[ordinal]
        schedule = [episode for item in design['training_replays']
                    for episode in episodes(item, shift)]
        if role == 'test':
            schedule += episodes(design['test_replays'][ordinal])
        config = WorldConfig(name=f'{PREFIX}_{role}_{ordinal:03d}',
                             seed=base_seed + index,
                             tail=('atradius', 'uk', 'coface')[index % 3],
                             late_scale=(1., 1.15, .9)[index % 3],
                             macro_regime=('stress' if role != 'test' and ordinal % 2
                                           else 'baseline'),
                             shock_schedule=schedule, **shared)
        worlds.append((config, role))
    return smoke, worlds


def audit_scenarios(worlds, design: dict):
    expected = {item['reference_event'] for item in design['training_replays']}
    observed_train = {episode.reference_event for config, role in worlds if role == 'train'
                      for episode in config.shock_schedule}
    test_events = []
    for config, role in worlds:
        if role != 'test':
            continue
        truth = pd.read_parquet(SYNTH / config.name / 'shock_truth.parquet')
        for item in design['test_replays']:
            active = truth[(truth.reference_event == item['reference_event']) &
                           truth.strength.gt(0) & truth.week.between(
                               '2024-07-01', '2025-09-01')]
            if not active.empty:
                test_events.append({'world': config.name, 'reference_event': item['reference_event'],
                                    'active_eval_weeks': int(active.week.nunique())})
    return {'training_reference_events': sorted(observed_train),
            'test_events': test_events,
            'passed': observed_train == expected and len(test_events) == 2 and
                      len({row['world'] for row in test_events}) == 2}


def run(*, firms=40, base_seed=96317, rounds=200, max_rows=10000000,
        stop_after='evaluate'):
    if stop_after not in STAGES:
        raise ValueError(stop_after)
    design = json.loads(DESIGN.read_text(encoding='utf-8'))
    if design['version'] != PREFIX:
        raise ValueError('Design version mismatch')
    calibration_path = SYNTH / 'calibration_fit.json'
    calibration = json.loads(calibration_path.read_text(encoding='utf-8'))
    evidence = source_provenance(sources={
        'calibration': calibration_path,
        'oxcgrt': RAW / 'oxcgrt/OxCGRT_compact_national_v1.csv',
        'wdi': RAW / 'wdi_vn/wdi_vietnam.csv',
        'shock_design': DESIGN,
    })
    smoke, worlds = configs(design, calibration, firms=firms, base_seed=base_seed)
    output = OUT / 'data' / PREFIX
    cohort_path = SYNTH / f'{PREFIX}_cohort.json'
    result = {'prefix': PREFIX, 'sources': evidence, 'design': str(DESIGN)}
    if stop_after == 'sources':
        return result
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / 'scenario_protocol.json'
    protocol = {'design': design, 'design_sha256': evidence['source_data_sha256']['shock_design'],
                'smoke': smoke.name,
                'worlds': [{'name': config.name, 'role': role, 'seed': config.seed,
                            'macro_regime': config.macro_regime,
                            'shock_schedule': [asdict(episode) for episode in config.shock_schedule]}
                           for config, role in worlds]}
    protocol = json.loads(json.dumps(protocol))
    if protocol_path.exists():
        if json.loads(protocol_path.read_text(encoding='utf-8')) != protocol:
            raise ValueError('Existing scenario protocol differs; choose a new prefix')
    else:
        protocol_path.write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding='utf-8')
    build_or_verify(smoke, evidence, synthetic_root=SYNTH)
    verify_world_manifest(SYNTH / smoke.name, validate=True)
    result['smoke'] = smoke.name
    if stop_after == 'smoke':
        return result
    for config, _ in worlds:
        build_or_verify(config, evidence, synthetic_root=SYNTH)
        print(f'world ready: {config.name}', flush=True)
    result['worlds'] = [config.name for config, _ in worlds]
    if stop_after == 'worlds':
        return result
    audited = [audit_world(SYNTH / config.name) for config, role in worlds if role != 'test']
    scenarios = audit_scenarios(worlds, design)
    readiness = assess_readiness(audited, evidence, start='2019-01-01', end='2025-12-31',
                                 scenario_holdout_present=scenarios['passed'],
                                 world_regimes={config.name: config.macro_regime
                                                for config, role in worlds if role != 'test'})
    readiness['scenario_audit'] = scenarios
    readiness['gate_note'] = ('Test replays differ from train in timing, duration and severity; '
                              'all four historical templates are present in train, '
                              'so no shock family is held out.')
    readiness_path = output / 'readiness.json'
    readiness_path.write_text(json.dumps(readiness, indent=2, ensure_ascii=False), encoding='utf-8')
    result['audit_worlds'] = str(readiness_path)
    if stop_after == 'audit_worlds':
        return result
    if not readiness['passed']:
        raise ValueError('World readiness failed')
    split = {'origin': design['split_origin'], 'label_horizon_days': 120,
             'train_stride_days': 28, 'eval_stride_days': 28}
    lock_cohort(cohort_path, [(config.name, role) for config, role in worlds],
                evidence, split, synthetic_root=SYNTH)
    result['lock_split'] = str(cohort_path)
    if stop_after == 'lock_split':
        return result
    result['train'] = train(cohort_path, output, synthetic_root=SYNTH,
                            rounds=rounds, max_rows=max_rows)
    if stop_after == 'train':
        return result
    result['evaluate'] = evaluate(cohort_path, output, synthetic_root=SYNTH).to_dict('records')
    (output / 'run_summary.json').write_text(json.dumps(result, indent=2,
                                                        ensure_ascii=False), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--firms', type=int, default=40)
    parser.add_argument('--base-seed', type=int, default=96317)
    parser.add_argument('--rounds', type=int, default=200)
    parser.add_argument('--max-rows', type=int, default=10000000)
    parser.add_argument('--stop-after', choices=STAGES, default='evaluate')
    args = parser.parse_args()
    print(json.dumps(run(**vars(args)), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
