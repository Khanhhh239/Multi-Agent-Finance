"""Owner-approved v1.1 aggregation; all benchmark results are dữ liệu tổng hợp."""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

SUPERVISED = ('L3-PU', 'L4-FB-PU', 'L4-PU-E2-AR', 'L4-PU-E2-AR-2plus1')
COLD = ('Cold-Rules-E2', 'Cold-v4')
PU_WEIGHTS = (.1, .2, .5)
TIERS = {'screening': (tuple(range(1001, 1009)), 2), 'selection': (tuple(range(1001, 1021)), 4)}
HARD_NEGATIVE_MAX = .15


def _count(value):
    if isinstance(value, bool) or int(value) != value or value < 0:
        raise ValueError('Counts must be nonnegative integers')
    return int(value)


def recall(tp, positives):
    tp, positives = _count(tp), _count(positives)
    if tp > positives or positives == 0:
        raise ValueError('Recall requires positive support and tp <= positives')
    return tp / positives


def branch_macro(protocols: Mapping, expected_branches):
    """One recall per large branch, plus one micro recall for all small branches.

    Each tp is measured from the run that hid THAT branch, with all target rows
    competing for the budget. Zero-support branches still require a saved run.
    """
    if set(protocols) != set(expected_branches) or len(expected_branches) != 10:
        raise ValueError('Exactly the ten registered hidden-branch protocols are required')
    large, small_tp, small_n, small_names = {}, 0, 0, []
    for branch in expected_branches:
        item = protocols[branch]
        tp, n = _count(item['branch_tp']), _count(item['branch_positives'])
        if tp > n:
            raise ValueError('Branch true positives exceed support')
        if n >= 10:
            large[branch] = tp / n
        else:
            small_tp += tp
            small_n += n
            small_names.append(branch)
    terms = list(large.values())
    if small_n:
        terms.append(small_tp / small_n)
    if not terms:
        raise ValueError('No positive target support for B')
    return {'B': float(np.mean(terms)), 'large_branches': large,
            'small_group': {'branches':small_names,'tp':small_tp,'positives':small_n,
                            'recall':small_tp/small_n if small_n else None}, 'averaging_terms':len(terms)}


def world_summary(protocols, branches):
    if set(protocols) != {'S2', *branches}:
        raise ValueError('World requires S2 and all ten P2xS2 runs')
    r = recall(protocols['S2']['tp'], protocols['S2']['positives'])
    b = branch_macro({key:protocols[key] for key in branches}, branches)
    rates = {}
    for key, item in protocols.items():
        rate = recall(item['hard_negative_alerts'], item['hard_negatives'])
        rates[key] = rate
    return {'R':r, **b, 'Q':(r+b['B'])/2, 'hard_negative_rates':rates,
            'eligible':all(value <= HARD_NEGATIVE_MAX for value in rates.values()),
            'data_origin':'dữ liệu tổng hợp'}


def candidate_summary(worlds, tier):
    seeds, tail_n = TIERS[tier]
    if set(worlds) != set(seeds):
        raise ValueError('Missing or unexpected worlds; never drop a bad world')
    for world in worlds.values():
        if not all(math.isfinite(world[key]) and 0 <= world[key] <= 1 for key in ('R','B','Q')):
            raise ValueError('Missing, invalid or nonfinite metric')
    ordered = sorted(seeds, key=lambda seed:(worlds[seed]['Q'],seed))
    q = [worlds[seed]['Q'] for seed in seeds]
    r = [worlds[seed]['R'] for seed in seeds]
    b = [worlds[seed]['B'] for seed in seeds]
    return {'J':float(np.mean([worlds[seed]['Q'] for seed in ordered[:tail_n]])),
            'tail_worlds':ordered[:tail_n], 'Q_min':min(q), 'Q_mean':float(np.mean(q)),
            'R_mean':float(np.mean(r)), 'R_min':min(r), 'B_mean':float(np.mean(b)), 'B_min':min(b),
            'eligible':all(worlds[seed]['eligible'] for seed in seeds), 'worlds':worlds,
            'tier':tier, 'data_origin':'dữ liệu tổng hợp'}


def advance(candidates, order=SUPERVISED, count=3):
    if set(candidates) != set(order):
        raise ValueError('Screening must finish the complete registered candidate list')
    return sorted((name for name in order if candidates[name]['eligible']),
                  key=lambda name:(-candidates[name]['J'],order.index(name)))[:count]


def selection_roster(supervised_screening):
    """Only supervised models compete for three slots; BOTH Cold controls run."""
    return {'supervised':advance(supervised_screening), 'cold':list(COLD)}


def choose_cold(candidates):
    """Do not select Cold until both controls finish all twenty selection worlds."""
    if set(candidates) != set(COLD):
        raise ValueError('Both Cold candidates must finish the selection tier')
    for candidate in candidates.values():
        if candidate['tier'] != 'selection' or {int(seed) for seed in candidate['worlds']} != set(TIERS['selection'][0]):
            raise ValueError('Each Cold candidate requires all twenty selection worlds')
    return final_choice(candidates,COLD)


def final_choice(candidates, order):
    """Retain v1's final near-tie rule; screening uses exact ties only."""
    valid = [name for name in order if name in candidates and candidates[name]['eligible']]
    if not valid:
        return None
    best = max(candidates[name]['J'] for name in valid)
    return next(name for name in valid if best-candidates[name]['J'] < .01)


def pre_seal_gate(summary, cold=False):
    if summary['tier'] != 'selection':
        raise ValueError('Only the selection tier can authorize sealing')
    thresholds = {'R_mean':.40,'B_mean':.33,'R_min':.30} if cold else {'R_mean':.65,'B_mean':.40,'R_min':.50}
    checks = {key:{'value':summary[key],'minimum':minimum,'passed':summary[key] >= minimum}
              for key, minimum in thresholds.items()}
    checks['hard_negative_limit'] = {'passed':bool(summary['eligible']),'maximum_per_world_protocol':.15}
    passed = all(item['passed'] for item in checks.values())
    return {'passed':passed,'checks':checks,'cold':cold,
            'decision':'continue' if passed else ('drop_cold' if cold else 'stop_without_generating_sealed_worlds'),
            'data_origin':'dữ liệu tổng hợp'}
