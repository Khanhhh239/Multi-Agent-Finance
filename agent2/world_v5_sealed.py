"""Sealed v5 worlds (R3). Generated only if the pre-seal gate passes; evaluated exactly once (R4).

Seeds are chosen and recorded here BEFORE any generation (seal keeper's choice): sealed 5101-5104, dry run 5199.
They differ from every development seed (1001-1020), v4 seeds and dry-run seeds. Context randomization uses the
same registered ranges as the development worlds (30 to 60 companies, money scale log-uniform 1 to 20,
Dirichlet(1,1,1) concealment, randomized pay calendars).

The novel scenario catalogue `NOVEL_V5` is filled ONLY by encoding the independent author's prose
(docs/05_ke_hoach_giao_viec/independent_scenarios/scenarios_v5.md) without adjusting it to be easier or harder.
All data are dữ liệu tổng hợp.
"""
from __future__ import annotations

import numpy as np

from .world_v4_schemes import SCHEMES, SPLIT_WEIGHTS
from .world_v5_dev import WorldV5Development, development_config

SEALED_SEEDS = (5101, 5102, 5103, 5104)
DRY_RUN_SEED = 5199
NOVEL_V5: dict = {}          # name -> (ACFE branch, weight, roles, Vietnamese reference); filled from the prose
NEW_DECOYS_V5: tuple = ()    # hard_negative_type names of the author's legitimate look-alikes
NOVEL_SHARE = .40            # share of additional cases drawn from the novel catalogue (as in sealed v4)
MIN_TEST_CASES_PER_NOVEL = 3
MIN_TEST_CASES_PER_WORLD = 40


def sealed_config(seed):
    if seed not in (*SEALED_SEEDS, DRY_RUN_SEED):
        raise ValueError('Sealed v5 seeds are fixed in advance')
    rng = np.random.default_rng(seed + 510_000)
    return {'seed': seed, 'rows': 200_000, 'fraud_rate': .004,
            'companies': int(rng.integers(30, 61)), 'money_scale': float(np.exp(rng.uniform(0, np.log(20)))),
            'difficulty_weights': rng.dirichlet(np.ones(3)).tolist(), 'calendar_seed': seed + 520_000,
            'data_origin': 'dữ liệu tổng hợp', 'sealed': seed != DRY_RUN_SEED}


class WorldV5Sealed(WorldV5Development):
    catalog = {**SCHEMES, **NOVEL_V5}

    def inject_fraud(self):
        if not NOVEL_V5:
            raise RuntimeError('NOVEL_V5 is empty: encode the independent scenarios first')
        rng = self.rng
        comps = [c for c, p in self.profile.items() if p['fraud_mu'] > 0]
        weights = [self.profile[c]['fraud_mu'] * self.profile[c]['n_staff'] ** .5 for c in comps]
        created = 0
        for scheme in NOVEL_V5:                                  # coverage: train/validation once, test at least 3x
            for split in SPLIT_WEIGHTS:
                for _ in range(MIN_TEST_CASES_PER_NOVEL if split == 'test' else 1):
                    created += self.try_case(scheme, comps, weights, split)
        for scheme in SCHEMES:
            created += self.try_case(scheme, comps, weights, 'test')
        target, attempts = round(self.n * self.rate), 0
        known, novel = list(SCHEMES), list(NOVEL_V5)
        while created < target and attempts < 20_000:
            attempts += 1
            if rng.random() < NOVEL_SHARE:
                scheme = rng.choices(novel, [NOVEL_V5[s][1] for s in novel])[0]
            else:
                scheme = rng.choices(known, [SCHEMES[s][1] for s in known])[0]
            created += self.try_case(scheme, comps, weights)
        test_cases = [c for c in self.cases if c['split'] == 'test']
        short = {s: sum(c['scheme'] == s for c in test_cases) for s in NOVEL_V5}
        if len(test_cases) < MIN_TEST_CASES_PER_WORLD or min(short.values()) < MIN_TEST_CASES_PER_NOVEL:
            raise ValueError(f'sealed coverage not met: test cases {len(test_cases)}, per novel {short}')


def generate_sealed(seed, directory):
    """Same writing path as development worlds (streamed save, manifest), with the sealed world class."""
    from pathlib import Path
    from .runtime_v5 import write_json
    from .world_v5_io import save_dataset_streamed
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f'Refusing to overwrite existing world: {directory}')
    config = sealed_config(seed)
    tables = WorldV5Sealed(config).finalize()
    manifest = save_dataset_streamed(directory, tables, config['rows'], config['fraud_rate'], config['seed'], config['companies'])
    manifest.update(version='5.0-sealed', sealed=config, novel_catalogue=sorted(NOVEL_V5), data_origin='dữ liệu tổng hợp')
    write_json(directory / 'manifest.json', manifest)
    return manifest
