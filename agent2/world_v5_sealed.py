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

from sme_fraud.generate import WINDOWS, parse

from .world_v4_schemes import SCHEMES, SPLIT_WEIGHTS, NotApplicable
from .world_v4_sealed import WorldV4Sealed
from .world_v5_dev import WorldV5Development, development_config
from .world_v5_scenarios import NEW_DECOYS_V5 as _DECOYS
from .world_v5_scenarios import NOVEL_V5 as _NOVEL
from .world_v5_scenarios import ScenarioMixin

SEALED_SEEDS = (5101, 5102, 5103, 5104)
DRY_RUN_SEED = 5199
NOVEL_V5: dict = dict(_NOVEL)     # name -> (ACFE branch, weight, roles, reference); encoded from the locked prose (v6.2)
NEW_DECOYS_V5: tuple = tuple(_DECOYS)    # hard_negative_type names of the author's legitimate look-alikes
NOVEL_SHARE = .40            # share of additional cases drawn from the novel catalogue (as in sealed v4)
MIN_TEST_CASES_PER_NOVEL = 3
MIN_TEST_CASES_PER_WORLD = 40
# Fixed 2026-10-22 BEFORE reading the author's prose, so look-alike frequency cannot be tuned to the detector:
# each new look-alike occurs for a company and split with probability DECOY_RATE, 1 to DECOY_MAX times
# (sealed v4 used .3 to .5 and 0 to 2). Every new look-alike must appear on at least MIN_TEST_ROWS_PER_DECOY test rows;
# if the random pass falls short, extra test-split occurrences are added in random companies (at most 200 attempts).
DECOY_RATE = .5
DECOY_MAX = 2
MIN_TEST_ROWS_PER_DECOY = 3


def sealed_config(seed):
    if seed not in (*SEALED_SEEDS, DRY_RUN_SEED):
        raise ValueError('Sealed v5 seeds are fixed in advance')
    rng = np.random.default_rng(seed + 510_000)
    return {'seed': seed, 'rows': 200_000, 'fraud_rate': .004,
            'companies': int(rng.integers(30, 61)), 'money_scale': float(np.exp(rng.uniform(0, np.log(20)))),
            'difficulty_weights': rng.dirichlet(np.ones(3)).tolist(), 'calendar_seed': seed + 520_000,
            'data_origin': 'dữ liệu tổng hợp', 'sealed': seed != DRY_RUN_SEED}


class WorldV5Sealed(ScenarioMixin, WorldV5Development):
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

    # helpers shared with the v4 sealed generator: a manager's customers, invoice and receipt rows, monthly dates
    my_customers = WorldV4Sealed.my_customers
    invoice_row = WorldV4Sealed.invoice_row
    receipt_row = WorldV4Sealed.receipt_row
    months_in = WorldV4Sealed.months_in

    def inject_hard_negatives(self):
        """Development look-alikes, then the author's new ones through `decoy_<name>(cid, split)` methods.

        A decoy method writes legitimate rows with `self.put(split, row, hard=name)` and raises NotApplicable when
        the company lacks what the situation needs.
        """
        super().inject_hard_negatives()
        rng = self.rng
        for name in NEW_DECOYS_V5:
            make = getattr(self, f'decoy_{name}')
            for cid in self.company_staff:
                for split in WINDOWS:
                    if rng.random() >= DECOY_RATE:
                        continue
                    for _ in range(rng.randint(1, DECOY_MAX)):
                        try:
                            make(cid, split)
                        except NotApplicable:
                            break
        companies = list(self.company_staff)
        short = {}
        for name in NEW_DECOYS_V5:                               # top up the test split, as for novel cases
            make, attempts = getattr(self, f'decoy_{name}'), 0
            while self._test_rows(name) < MIN_TEST_ROWS_PER_DECOY and attempts < 200:
                attempts += 1
                try:
                    make(rng.choice(companies), 'test')
                except NotApplicable:
                    pass
            short[name] = self._test_rows(name)
        if short and min(short.values()) < MIN_TEST_ROWS_PER_DECOY:
            raise ValueError(f'sealed look-alike coverage not met: test rows per new look-alike {short}')

    def _test_rows(self, name):
        a, b = WINDOWS['test']
        return sum(t.get('hard_negative_type') == name and a <= parse(r['posted_at']) < b for r, t in zip(self.rows, self.truth))


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
