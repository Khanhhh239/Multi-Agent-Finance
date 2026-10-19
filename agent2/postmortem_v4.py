"""Post-hoc diagnostics on synthetic v4 data; never a new sealed evaluation.

Only the original three methods are fitted. Diagnostic label interventions do
not create v5 model candidates. Historical results and frozen sources are read
only. Existing v4 feature caches are required after the upstream rules update.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import eval_v4
from .eval_v4 import CANDIDATES, alerts_for, prepare, run_candidates
from .hybrid import family_weights
from .sealed_v4 import (compact_integer_storage, development_pool, file_hashes,
                        release_feature_caches, report, wait_for_memory)
from .world_v4_schemes import SCHEMES
from .world_v4_sealed import NOVEL

METHODS = ('L3', 'L4-FB', 'Novelty max(R,E)')
PROTOCOLS = ('S1_masked', 'S2_original', 'S1_drop_train', 'S1_drop_train_valid', 'S1_unlabelled_0p2')
KNOWN = tuple(sorted(SCHEMES))
PROTECTED = ('results/v4/sealed_v4.json', 'results/v4/v4_frozen.json',
             'work/results/v4_frozen.json', 'results/v4/sealed_gates.json',
             'docs/03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md')
CACHES = ('engineered.pkl', 'v4feats.pkl', 'rules2.pkl', 'ustack.pkl')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8', newline='\n')
    temporary.replace(path)


def json_finite(value):
    if isinstance(value, dict):
        return {k: json_finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_finite(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def label_intervention(frame, mode):
    """Oracle removal is diagnostic only; every test row remains untouched."""
    if mode not in PROTOCOLS:
        raise ValueError('unknown diagnostic protocol')
    if mode == 'S2_original':
        raise ValueError('S2 uses the development pool, not target labels')
    novel = frame.fraud_type.isin(NOVEL)
    masked = frame.copy()
    masked.loc[novel, 'is_fraud'] = 0
    masked.loc[novel, 'fraud_type'] = ''
    train = masked[masked.split == 'train'].copy()
    valid = masked[masked.split == 'validation'].copy()
    if mode in ('S1_drop_train', 'S1_drop_train_valid'):
        train = train.loc[~novel.loc[train.index]].copy()
    if mode == 'S1_drop_train_valid':
        valid = valid.loc[~novel.loc[valid.index]].copy()
    return train, valid


def unlabelled_weights(train, balanced=False, factor=.2):
    if not 0 < factor <= 1:
        raise ValueError('unlabelled weight must be in (0, 1]')
    weights = family_weights(train) if balanced else np.ones(len(train))
    weights[train.is_fraud.to_numpy() == 0] *= factor
    return weights


def fit_weighted_diagnostic(method, train, valid, factor=.2):
    """Frozen LGBM recipe with only the training sample-weight intervention.

    Validation labels, AP selection, positive class scaling, features and grid
    remain those of hybrid.LGBM. This is an R0 sensitivity check, not R2 PU work.
    """
    import lightgbm as lgb
    from sklearn.metrics import average_precision_score
    model = CANDIDATES[method]()
    model.cols = model.cols_fn(train)
    x = train[model.cols].to_numpy(dtype=np.float32)
    y = train.is_fraud.to_numpy()
    weights = unlabelled_weights(train, model.balance == 'family', factor)
    positive_weight = max(1., (len(y) - y.sum()) / max(1, y.sum())) ** .5
    best = (-1., None)
    for leaves, rate in model.grid:
        current = lgb.LGBMClassifier(n_estimators=600, learning_rate=rate, num_leaves=leaves,
                    min_child_samples=10, subsample=.8, subsample_freq=1, colsample_bytree=.6,
                    reg_lambda=2., scale_pos_weight=positive_weight, random_state=model.seed,
                    verbose=-1, n_jobs=4)
        if valid is not None and valid.is_fraud.sum() > 0:
            xv = valid[model.cols].to_numpy(dtype=np.float32)
            current.fit(x, y, sample_weight=weights, eval_set=[(xv, valid.is_fraud.to_numpy())],
                        eval_metric='average_precision', callbacks=[lgb.early_stopping(60, verbose=False)])
            ap = average_precision_score(valid.is_fraud, current.predict_proba(xv)[:, 1])
        else:
            current.set_params(n_estimators=200)
            current.fit(x, y, sample_weight=weights)
            ap = 0.
        if ap > best[0]:
            best = (ap, current)
    model.model = best[1]
    return model


def add_metadata(frame, path):
    companies = pd.read_csv(path / 'companies.csv', dtype=str, keep_default_na=False)
    companies['company_id'] = path.name + ':' + companies.company_id
    # The sealed generator's replacement schedules are disjoint from all dev schedules.
    companies['pay_shift'] = companies.pay_days.isin(('1', '20', '7|22')).map({True: 'changed', False: 'unchanged'})
    result = frame.merge(companies[['company_id', 'pay_shift', 'size_class', 'pay_days']], on='company_id', validate='many_to_one')
    truth = pd.read_csv(path / 'truth_cases.csv', dtype=str, keep_default_na=False)
    truth['company_id'] = path.name + ':' + truth.company_id
    result = result.merge(truth[['company_id', 'case_id', 'concealment']], on=['company_id', 'case_id'], how='left', validate='many_to_one')
    result['world'] = path.name
    return result


def case_summary(frame, flags):
    positive = frame.is_fraud.to_numpy() == 1
    keys = ['world', 'company_id', 'case_id', 'fraud_type', 'difficulty', 'concealment', 'pay_shift', 'size_class']
    rows = frame.loc[positive, keys].copy()
    if rows.case_id.isna().any() or (rows.case_id == '').any():
        raise ValueError('positive rows require case identifiers')
    rows['rows'] = 1
    for method, alerts in flags.items():
        if np.asarray(alerts).shape != (len(frame),):
            raise ValueError('misaligned alert vector')
        rows['hit::' + method] = np.asarray(alerts, dtype=int)[positive]
    grouped = rows.groupby(keys, sort=True, dropna=False).sum(numeric_only=True).reset_index()
    if grouped.duplicated(['company_id', 'case_id']).any():
        raise ValueError('a case crosses metadata strata; do not split a bootstrap cluster')
    return grouped


def recall_interval(cases, method, reps=2000, seed=0):
    if not len(cases):
        return {'recall': None, 'ci95': None, 'cases': 0, 'rows': 0, 'companies': 0}
    a = cases[['rows', 'hit::' + method]].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws = a[rng.integers(len(a), size=(reps, len(a)))].sum(axis=1)
    estimates = draws[:, 1] / draws[:, 0]
    return {'recall': float(a[:, 1].sum() / a[:, 0].sum()),
            'ci95': np.quantile(estimates, [.025, .975]).tolist(), 'cases': len(a),
            'rows': int(a[:, 0].sum()), 'companies': int(cases.company_id.nunique())}


def exact_metrics(actual, expected, prefix=''):
    """Fail before interventions if upstream dependency changes affect the baseline."""
    differences = []
    for key, value in expected.items():
        current = actual[key]
        label = prefix + key
        if isinstance(value, dict):
            differences.extend(exact_metrics(current, value, label + '.'))
        elif isinstance(value, (float, int)):
            if value is None or (isinstance(value, float) and np.isnan(value)):
                okay = current is None or (isinstance(current, float) and np.isnan(current))
            else:
                okay = current is not None and np.isclose(current, value, rtol=0, atol=1e-12)
            if not okay:
                differences.append({'metric': label, 'expected': value, 'actual': current})
    return differences


def baseline_comparison(actual, expected):
    """Gate the exact operating decisions used by R0; retain AP discrepancies.

    AP ranks all rows rather than the fixed weekly alerts. Historical AP is
    retained as a separate diagnostic, never overwritten or used for selection.
    """
    differences, ap = [], {}
    for method in METHODS:
        fields = {k: v for k, v in expected[method].items() if k != 'ap'}
        differences.extend(exact_metrics(actual[method], fields, method + '.'))
        ap[method] = {'historical': expected[method]['ap'], 'rerun': actual[method]['ap'],
                      'delta': actual[method]['ap'] - expected[method]['ap']}
    if differences:
        raise ValueError(f'original operating decisions failed to reproduce: {differences}')
    return {'status': 'passed', 'scope': 'all historical numeric fields except AP, including per-family recalls',
            'maximum_tolerance': 1e-12, 'ap_diagnostic_only': ap,
            'raw_scores_bit_identical_claimed': False}


def development_cases(path, alerts_path):
    with np.load(alerts_path, allow_pickle=False) as saved:
        frame = pd.DataFrame({k: saved[k] for k in ('company_id', 'case_id', 'transaction_id', 'is_fraud')})
        flags = dict(zip(saved['names'].tolist(), saved['alerts']))
    labels = pd.read_csv(path / 'labels.csv', dtype=str, keep_default_na=False)
    labels['transaction_id'] = path.name + ':' + labels.transaction_id
    frame = frame.merge(labels[['transaction_id', 'fraud_type', 'difficulty']], on='transaction_id', validate='one_to_one')
    frame = add_metadata(frame, path)
    return case_summary(frame, {m: flags[m] for m in METHODS})


def subgroup_tables(cases, reps, seed):
    output = {}
    scopes = {'all_known': cases[cases.fraud_type.isin(KNOWN)],
              'known_payroll': cases[cases.fraud_type.isin([s for s in KNOWN if SCHEMES[s][0] == 'payroll'])]}
    for scope, subset in scopes.items():
        output[scope] = {}
        for columns in (['pay_shift'], ['size_class'], ['pay_shift', 'size_class']):
            name = '+'.join(columns)
            output[scope][name] = {}
            for group, part in subset.groupby(columns, sort=True):
                tag = '|'.join(group if isinstance(group, tuple) else (group,))
                output[scope][name][tag] = {m: recall_interval(part, m, reps, seed) for m in METHODS}
    return output


def paired_effect(base, variant, method, scope='all', reps=2000, seed=0):
    """Paired whole-case effect; positive means the intervention finds more."""
    keys = ['company_id', 'case_id']
    hit = 'hit::' + method
    joined = base.merge(variant[keys + ['rows', hit]], on=keys, suffixes=('_base', '_variant'), validate='one_to_one')
    if len(joined) != len(base) or not np.array_equal(joined.rows_base, joined.rows_variant):
        raise ValueError('interventions changed the evaluation population')
    if scope == 'known':
        joined = joined[joined.fraud_type.isin(KNOWN)]
    elif scope == 'novel':
        joined = joined[joined.fraud_type.isin(NOVEL)]
    elif scope != 'all':
        raise ValueError('unknown effect scope')
    if not len(joined):
        raise ValueError('empty paired effect population')
    values = joined[['rows_base', hit + '_base', hit + '_variant']].to_numpy(dtype=float)
    index = np.random.default_rng(seed).integers(len(values), size=(reps, len(values)))
    draws = values[index].sum(axis=1)
    estimates = (draws[:, 2] - draws[:, 1]) / draws[:, 0]
    point = float((values[:, 2].sum() - values[:, 1].sum()) / values[:, 0].sum())
    return {'estimate': point, 'ci95': np.quantile(estimates, [.025, .975]).tolist(), 'cases': len(values)}, estimates


def world_composition(path):
    labels = pd.read_csv(path / 'labels.csv', dtype=str, keep_default_na=False)
    splits = pd.read_csv(path / 'splits.csv', dtype=str, keep_default_na=False)
    labels = labels.merge(splits, on='transaction_id', validate='one_to_one')
    truth = pd.read_csv(path / 'truth_cases.csv', dtype=str, keep_default_na=False)
    output = {}
    for split in ('train', 'validation', 'test'):
        rows = labels[(labels.split == split) & (labels.is_fraud == '1')]
        cases = truth[truth.split == split]
        novel = rows.fraud_type.isin(NOVEL)
        output[split] = {'fraud_rows': len(rows), 'known_rows': int((~novel).sum()), 'novel_rows': int(novel.sum()),
                         'cases': len(cases), 'known_cases': int((~cases.scheme.isin(NOVEL)).sum()),
                         'novel_cases': int(cases.scheme.isin(NOVEL).sum()),
                         'concealment_cases': cases.concealment.value_counts().sort_index().to_dict(),
                         'schemes': {family: {'rows': len(part), 'cases': int(part.case_id.nunique())}
                                     for family, part in rows.groupby('fraud_type', sort=True)}}
    return output


def family_drops(development, protocols):
    output = {}
    for method in METHODS:
        output[method] = {}
        for mode in ('S1_masked', 'S2_original'):
            rows = []
            for family in KNOWN:
                dev = [c[c.fraud_type == family] for c in development]
                target = [pd.DataFrame(p[mode]['cases']) for p in protocols.values()]
                target = [c[c.fraud_type == family] for c in target]
                recall_dev = float(np.mean([c['hit::' + method].sum() / c.rows.sum() for c in dev]))
                recall_target = float(np.mean([c['hit::' + method].sum() / c.rows.sum() for c in target]))
                rows.append({'family': family, 'development_recall': recall_dev, 'target_recall': recall_target,
                             'drop': recall_dev - recall_target, 'development_cases': sum(len(c) for c in dev),
                             'target_cases': sum(len(c) for c in target), 'target_fraud_rows': sum(int(c.rows.sum()) for c in target)})
            output[method][mode] = sorted(rows, key=lambda r: (-r['drop'], r['family']))
    return output


def world_gap(reference, subject, method):
    """Exact two-factor descriptive breakdown of a reference mean minus 933."""
    hit = 'hit::' + method
    families = sorted(set(subject.fraud_type) | {f for c in reference for f in c.fraud_type})
    ref_weights, ref_mass = [], []
    for cases in reference:
        n = np.asarray([cases.loc[cases.fraud_type == f, 'rows'].sum() for f in families], dtype=float)
        h = np.asarray([cases.loc[cases.fraud_type == f, hit].sum() for f in families], dtype=float)
        ref_weights.append(n / n.sum())
        ref_mass.append(h / n.sum())
    weights = np.mean(ref_weights, axis=0)
    mass = np.mean(ref_mass, axis=0)
    if np.any(weights == 0):
        raise ValueError('a subject family is absent from both reference worlds')
    rates = mass / weights
    n = np.asarray([subject.loc[subject.fraud_type == f, 'rows'].sum() for f in families], dtype=float)
    h = np.asarray([subject.loc[subject.fraud_type == f, hit].sum() for f in families], dtype=float)
    if np.any(n == 0):
        raise ValueError('a reference family is absent from the subject world')
    own_weights, own_rates = n / n.sum(), h / n
    composition = (weights - own_weights) * rates
    conditional = own_weights * (rates - own_rates)
    delta = float(mass.sum() - h.sum() / n.sum())
    assert np.isclose((composition + conditional).sum(), delta, atol=1e-12)
    return {'reference_recall': float(mass.sum()), 'subject_recall': float(h.sum() / n.sum()), 'gap': delta,
            'composition_component': float(composition.sum()), 'within_family_component': float(conditional.sum()),
            'by_family': sorted([{'family': f, 'composition': float(composition[i]), 'within_family': float(conditional[i]),
                                  'total': float(composition[i] + conditional[i])} for i, f in enumerate(families)],
                                key=lambda row: (-row['total'], row['family'])),
            'interpretation': 'descriptive association, not a causal allocation'}


def _dev_levels(development, method, reps, rng):
    rates, overall = [], []
    for cases in development:
        n = np.zeros((reps, len(KNOWN)))
        h = np.zeros_like(n)
        for j, family in enumerate(KNOWN):
            group = cases[cases.fraud_type == family][['rows', 'hit::' + method]].to_numpy(dtype=float)
            if not len(group):
                raise ValueError('development family missing; standardisation is undefined')
            draws = group[rng.integers(len(group), size=(reps, len(group)))].sum(axis=1)
            n[:, j], h[:, j] = draws[:, 0], draws[:, 1]
        rates.append(h / n)
        overall.append(h.sum(axis=1) / n.sum(axis=1))
    return np.mean(overall, axis=0), np.mean(rates, axis=0)


def decomposition(development, target, method, reps=2000, seed=20261019):
    """An ordered descriptive identity, not a unique causal attribution.

    A dev P1; B dev rates at target-known family mix; C target S2 known;
    D target S2 all; E target S1 drop-train; F target original S1.
    Dev bootstrap stratifies by world and family; target resamples whole cases
    within each world, paired across all protocols. Budgets stay fixed.
    """
    rng = np.random.default_rng(seed)
    dev_a, dev_rates = _dev_levels(development, method, reps, rng)
    point_a = np.mean([c['hit::' + method].sum() / c.rows.sum() for c in development])
    point_rates = np.mean([[c.loc[c.fraud_type == f, 'hit::' + method].sum() / c.loc[c.fraud_type == f, 'rows'].sum()
                            for f in KNOWN] for c in development], axis=0)
    all_points, all_samples = [], []
    for cases in target:
        n = cases.rows.to_numpy(dtype=float)
        family = cases.fraud_type.to_numpy()
        known = np.isin(family, KNOWN)
        s2, drop, s1 = (cases[k + '::' + method].to_numpy(dtype=float) for k in ('S2', 'drop', 'S1'))
        mix = np.asarray([n[family == f].sum() for f in KNOWN])
        point = [float(mix @ point_rates / mix.sum()), float(s2[known].sum() / n[known].sum()),
                 float(s2.sum() / n.sum()), float(drop.sum() / n.sum()), float(s1.sum() / n.sum())]
        index = rng.integers(len(n), size=(reps, len(n)))
        sampled_n, sampled_family = n[index], family[index]
        sampled_known = known[index]
        denominator = sampled_n.sum(axis=1)
        denominator_known = (sampled_n * sampled_known).sum(axis=1)
        if np.any(denominator_known == 0):
            raise ValueError('bootstrap draw has no known fraud cases')
        mixture = np.stack([(sampled_n * (sampled_family == f)).sum(axis=1) for f in KNOWN], axis=1)
        samples = np.stack([(mixture * dev_rates).sum(axis=1) / denominator_known,
                            (s2[index] * sampled_known).sum(axis=1) / denominator_known,
                            s2[index].sum(axis=1) / denominator, drop[index].sum(axis=1) / denominator,
                            s1[index].sum(axis=1) / denominator], axis=1)
        all_points.append(point)
        all_samples.append(samples)
    levels = np.r_[point_a, np.mean(all_points, axis=0)]
    sampled_levels = np.column_stack([dev_a, np.mean(all_samples, axis=0)])
    differences = levels[:-1] - levels[1:]
    draws = sampled_levels[:, :-1] - sampled_levels[:, 1:]
    names = ('known_family_composition', 'known_conditional_transfer', 'novel_mixture_under_S2',
             'training_source_and_history_residual', 'remove_novel_training_rows_intervention')
    total = levels[0] - levels[-1]
    assert np.isclose(differences.sum(), total, atol=1e-12)
    return {'method': method, 'levels': dict(zip(('A_dev', 'B_reweighted_dev', 'C_S2_known', 'D_S2_all', 'E_drop_train', 'F_S1'), levels.tolist())),
            'components': {name: {'estimate': float(differences[i]), 'ci95': np.quantile(draws[:, i], [.025, .975]).tolist()} for i, name in enumerate(names)},
            'total': {'estimate': float(total), 'ci95': np.quantile(sampled_levels[:, 0] - sampled_levels[:, -1], [.025, .975]).tolist()},
            'identity_residual': float(differences.sum() - total), 'reps': reps, 'seed': seed,
            'interpretation': 'post-hoc descriptive ordered identity; not unique or causal; fixed models and budgets'}


def provenance(paths, saved_alerts, out, reps, seed):
    frozen = json.loads(Path(PROTECTED[1]).read_text(encoding='utf-8'))
    if file_hashes(Path('.')) != frozen['hashes']:
        raise ValueError('v4 frozen sources changed')
    for path in paths:
        for cache in CACHES:
            if not (path / '_cache' / cache).exists():
                raise FileNotFoundError(f'required historical v4 cache missing: {path / cache}; do not rebuild with updated rules')
    files = [Path(p) for p in PROTECTED] + [Path(__file__)] + list(saved_alerts)
    for path in paths:
        files.extend(path / name for name in ('labels.csv', 'transactions.csv', 'features.csv', 'splits.csv', 'companies.csv', 'truth_cases.csv'))
        files.extend(path / '_cache' / cache for cache in CACHES)
    manifest = {'analysis_kind': 'hậu kiểm, không phải niêm phong', 'data_kind': 'dữ liệu tổng hợp',
                'methods': METHODS, 'protocols': PROTOCOLS, 'unlabelled_weight_fixed': .2, 'reps': reps, 'seed': seed,
                'v5_model_training_started': False, 'protected_sha256': {p: sha256(p) for p in PROTECTED},
                'inputs_sha256': {str(p): sha256(p) for p in files}, 'frozen_hashes': frozen['hashes'],
                'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}
    path = out / 'manifest.json'
    if path.exists():
        old = json.loads(path.read_text(encoding='utf-8'))
        if json_finite(manifest) != old:
            raise ValueError('diagnostic provenance changed; use another output directory and retain old results')
    else:
        write_json(path, manifest)
    return manifest


def protocol_result(world, mode, frame, metadata, pool, expected, out, manifest):
    destination = out / f'{world}_{mode}.json'
    plan_hash = hashlib.sha256(json.dumps(json_finite(manifest), sort_keys=True).encode()).hexdigest()
    if destination.exists():
        previous = json.loads(destination.read_text(encoding='utf-8'))
        if previous['plan_hash'] != plan_hash:
            raise ValueError('checkpoint plan differs')
        return previous
    print(f'{world}: {mode}', flush=True)
    original_valid = frame[frame.split == 'validation']
    test = frame[frame.split == 'test'].reset_index(drop=True)
    test_metadata = metadata[metadata.split == 'test'].reset_index(drop=True)
    if test.transaction_id.tolist() != test_metadata.transaction_id.tolist():
        raise ValueError('metadata order changed')
    train, valid = pool if mode == 'S2_original' else label_intervention(frame, mode)
    metrics, flags, fit = {}, {}, {}
    for method in METHODS:
        wait_for_memory()
        began = time.perf_counter()
        if mode == 'S1_unlabelled_0p2' and not method.startswith('Novelty'):
            model = fit_weighted_diagnostic(method, train, valid)
            scores = model.score(test)
            calibration = model.score(original_valid)
            del model
        else:
            scored, calibrated, _ = run_candidates(train, valid, test, names=[method], ref_for_novelty=original_valid)
            scores, calibration = scored[method], calibrated[method]
            del scored, calibrated
        alerts, _ = alerts_for(test, {method: scores}, {method: calibration})
        flags[method] = alerts[method]
        metrics[method] = report(test, {method: flags[method]}, {method: scores})[method]
        fit[method] = {'seconds': time.perf_counter() - began, 'train_rows': len(train),
                       'labelled_positive_rows': int(train.is_fraud.sum()), 'validation_rows': len(valid)}
        del scores, calibration, alerts
        gc.collect()
    checks = None
    if mode in ('S1_masked', 'S2_original'):
        protocol = 'S1' if mode == 'S1_masked' else 'S2'
        checks = baseline_comparison(metrics, expected[protocol])
        checks['original_protocol'] = protocol
    result = {'analysis_kind': 'hậu kiểm, không phải niêm phong', 'data_kind': 'dữ liệu tổng hợp',
              'plan_hash': plan_hash, 'world': world, 'protocol': mode, 'metrics': json_finite(metrics),
              'fit': fit, 'original_baseline_check': checks,
              'cases': json_finite(case_summary(test_metadata, flags).to_dict(orient='records'))}
    write_json(destination, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('results/v5/postmortem_v4'))
    parser.add_argument('--reps', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=20261019)
    args = parser.parse_args()
    if args.reps < 100:
        raise ValueError('use at least 100 bootstrap replicates')
    eval_v4.WORKERS = json.loads(Path(PROTECTED[1]).read_text(encoding='utf-8')).get('candidate_workers', 1)
    dev = [Path(f'work/data/w4_s{s}') for s in (411, 412, 413)]
    targets = [Path(f'work/data/s4_s{s}') for s in (931, 932, 933)]
    saved = [Path(f'work/results/v4_methods/{p.name}_P1_alerts.npz') for p in dev]
    manifest = provenance(dev + targets, saved, args.out, args.reps, args.seed)
    development = [development_cases(p, a) for p, a in zip(dev, saved)]
    write_json(args.out / 'development_cases.json', [json_finite(f.to_dict(orient='records')) for f in development])
    pool = development_pool(dev, compact=True)
    original = json.loads(Path(PROTECTED[0]).read_text(encoding='utf-8'))['worlds']
    worlds = {}
    for path in targets:
        frame = compact_integer_storage(prepare(path))
        release_feature_caches()
        metadata = add_metadata(frame[frame.split == 'test'].reset_index(drop=True), path)
        worlds[path.name] = {}
        for mode in PROTOCOLS:
            worlds[path.name][mode] = protocol_result(path.name, mode, frame, metadata, pool, original[path.name], args.out, manifest)
        del frame, metadata
        gc.collect()
    del pool
    gc.collect()
    summary = {'analysis_kind': manifest['analysis_kind'], 'data_kind': manifest['data_kind'], 'label_effects': {},
               'subgroups': {}, 'decomposition': {}, 'paired_label_effects': {}, 'composition': {p.name: world_composition(p) for p in targets}}
    target_cases = []
    for world, protocols in worlds.items():
        summary['label_effects'][world] = {mode: protocols[mode]['metrics'] for mode in PROTOCOLS}
        summary['subgroups'][world] = {mode: subgroup_tables(pd.DataFrame(protocols[mode]['cases']), args.reps, args.seed)
                                        for mode in ('S1_masked', 'S2_original')}
        base = pd.DataFrame(protocols['S1_masked']['cases'])
        keys = ['company_id', 'case_id']
        joined = base.rename(columns={'hit::' + m: 'S1::' + m for m in METHODS})
        for mode, prefix in (('S2_original', 'S2'), ('S1_drop_train', 'drop')):
            other = pd.DataFrame(protocols[mode]['cases'])
            other = other[keys + ['hit::' + m for m in METHODS]].rename(columns={'hit::' + m: prefix + '::' + m for m in METHODS})
            joined = joined.merge(other, on=keys, validate='one_to_one')
        assert len(joined) == len(base)
        target_cases.append(joined)
    summary['family_drops'] = family_drops(development, worlds)
    for mode in ('S1_drop_train', 'S1_drop_train_valid', 'S1_unlabelled_0p2'):
        summary['paired_label_effects'][mode] = {}
        for method in METHODS:
            summary['paired_label_effects'][mode][method] = {}
            for scope in ('all', 'known', 'novel'):
                points, samples, per_world = [], [], {}
                for number, (world, protocols) in enumerate(worlds.items()):
                    effect, draws = paired_effect(pd.DataFrame(protocols['S1_masked']['cases']),
                                                 pd.DataFrame(protocols[mode]['cases']), method, scope,
                                                 args.reps, args.seed + number)
                    per_world[world] = effect
                    points.append(effect['estimate'])
                    samples.append(draws)
                summary['paired_label_effects'][mode][method][scope] = {
                    'macro_estimate': float(np.mean(points)), 'macro_ci95': np.quantile(np.mean(samples, axis=0), [.025, .975]).tolist(),
                    'worlds': per_world}
    for method in METHODS:
        summary['decomposition'][method] = decomposition(development, target_cases, method, args.reps, args.seed)
    summary['world_933_gap'] = {mode: {m: world_gap([pd.DataFrame(worlds[w][mode]['cases']) for w in ('s4_s931', 's4_s932')],
                                                   pd.DataFrame(worlds['s4_s933'][mode]['cases']), m) for m in METHODS}
                                for mode in ('S1_masked', 'S2_original')}
    if {p: sha256(p) for p in PROTECTED} != manifest['protected_sha256']:
        raise ValueError('protected v4 artifact changed during diagnostics')
    summary['protected_artifacts_unchanged'] = True
    write_json(args.out / 'summary.json', summary)
    print(json.dumps({'status': 'complete', 'analysis_kind': manifest['analysis_kind'],
                      'data_kind': manifest['data_kind'], 'out': str(args.out)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
