import json

import numpy as np
import pandas as pd
import pytest

from agent2.postmortem_v4 import (KNOWN, METHODS, baseline_comparison, case_summary, decomposition,
    exact_metrics, fit_weighted_diagnostic, label_intervention, paired_effect, unlabelled_weights, world_gap, write_json)
from agent2.hybrid import LGBM


def test_diagnostic_label_modes_keep_evaluation_and_original_data_untouched():
    novel = 'fake_tax_payment'
    frame = pd.DataFrame({'is_fraud': [1, 1, 1, 1, 1, 1],
                          'fraud_type': ['known', novel, 'known', novel, 'known', novel],
                          'split': ['train', 'train', 'validation', 'validation', 'test', 'test']})
    before = frame.copy(deep=True)
    train, valid = label_intervention(frame, 'S1_masked')
    assert train.is_fraud.tolist() == valid.is_fraud.tolist() == [1, 0]
    train, valid = label_intervention(frame, 'S1_drop_train')
    assert train.index.tolist() == [0] and valid.index.tolist() == [2, 3]
    train, valid = label_intervention(frame, 'S1_drop_train_valid')
    assert train.index.tolist() == [0] and valid.index.tolist() == [2]
    pd.testing.assert_frame_equal(frame, before)
    with pytest.raises(ValueError, match='development pool'):
        label_intervention(frame, 'S2_original')


def test_unlabelled_weights_preserve_family_mass_and_downweight_every_zero_label():
    frame = pd.DataFrame({'is_fraud': [0, 0, 1, 1, 1], 'fraud_type': ['', '', 'a', 'a', 'b']})
    weights = unlabelled_weights(frame, balanced=True)
    np.testing.assert_allclose(weights, [.2, .2, .75, .75, 1.5])
    with pytest.raises(ValueError):
        unlabelled_weights(frame, factor=0)


def cases():
    return pd.DataFrame({'company_id': ['c'] * 3, 'case_id': ['1', '2', '3'],
                         'fraud_type': [KNOWN[0], KNOWN[1], 'fake_tax_payment'],
                         'rows': [2, 3, 5], 'hit::L3': [0, 0, 0]})


def test_paired_effect_resamples_whole_cases_and_detects_population_changes():
    base = cases()
    variant = base.copy()
    variant['hit::L3'] = variant.rows
    effect, draws = paired_effect(base, variant, 'L3', reps=200)
    assert effect['estimate'] == 1 and effect['ci95'] == [1, 1]
    np.testing.assert_array_equal(draws, 1)
    variant.loc[0, 'rows'] = 9
    with pytest.raises(ValueError, match='evaluation population'):
        paired_effect(base, variant, 'L3')


def test_exact_baseline_comparison_rejects_changed_family_metrics():
    assert exact_metrics({'recall': .5, 'by_family': {'x': .3}}, {'recall': .5, 'by_family': {'x': .3}}) == []
    changes = exact_metrics({'recall': .5, 'by_family': {'x': .4}}, {'recall': .5, 'by_family': {'x': .3}})
    assert changes[0]['metric'] == 'by_family.x'


def test_decomposition_is_exact_with_case_bootstrap_and_zero_total_control():
    dev, targets = [], []
    for world in range(3):
        development = pd.DataFrame({'company_id': ['c'] * len(KNOWN), 'case_id': [str(i) for i in range(len(KNOWN))],
                                     'fraud_type': KNOWN, 'rows': 2, 'hit::L3': 2})
        dev.append(development)
        target = development.drop(columns='hit::L3').copy()
        for protocol in ('S2', 'drop', 'S1'):
            target[protocol + '::L3'] = 2
        targets.append(target)
    result = decomposition(dev, targets, 'L3', reps=200)
    assert abs(result['identity_residual']) < 1e-12
    assert result['total'] == {'estimate': 0., 'ci95': [0., 0.]}
    assert all(v['ci95'] == [0., 0.] for v in result['components'].values())
    for target in targets:
        target['S1::L3'] = 0
    result = decomposition(dev, targets, 'L3', reps=200)
    assert result['total']['estimate'] == 1
    assert result['components']['remove_novel_training_rows_intervention']['estimate'] == 1


def test_checkpoint_write_is_strict_json_and_does_not_leave_temporary_file(tmp_path):
    target = tmp_path / 'check.json'
    write_json(target, {'status': 'hậu kiểm, không phải niêm phong'})
    assert json.loads(target.read_text(encoding='utf-8'))['status'].startswith('hậu kiểm')
    assert not target.with_suffix('.json.tmp').exists()


def test_weight_one_reproduces_frozen_fit_recipe(monkeypatch):
    from agent2 import postmortem_v4 as diagnostic
    rng = np.random.default_rng(21)
    frame = pd.DataFrame({'x': rng.normal(size=360), 'z': rng.normal(size=360)})
    frame['is_fraud'] = ((frame.x + frame.z) > 1).astype(int)
    frame['fraud_type'] = np.where(frame.is_fraud == 1, np.where(frame.x > 1.4, 'b', 'a'), '')
    factory = lambda: LGBM(lambda _: ['x', 'z'], 'toy', balance='family', grid=((7, .05), (15, .05)))
    monkeypatch.setitem(diagnostic.CANDIDATES, 'L4-FB', factory)
    train, valid = frame.iloc[:260], frame.iloc[260:]
    baseline = factory().fit(train, valid)
    weighted = fit_weighted_diagnostic('L4-FB', train, valid, factor=1)
    np.testing.assert_array_equal(baseline.score(valid), weighted.score(valid))
    assert baseline.model.get_params() == weighted.model.get_params()


def test_world_gap_preserves_reference_average_when_world_family_mixes_differ():
    reference = [cases().copy(), cases().copy()]
    reference[0]['hit::L3'] = [2, 0, 0]
    reference[1]['rows'] = [4, 1, 5]
    reference[1]['hit::L3'] = [0, 1, 5]
    subject = cases()
    result = world_gap(reference, subject, 'L3')
    assert result['reference_recall'] == pytest.approx(.4)
    assert result['composition_component'] + result['within_family_component'] == pytest.approx(result['gap'])
    assert sum(r['total'] for r in result['by_family']) == pytest.approx(result['gap'])


def test_ap_discrepancy_is_retained_but_operating_difference_still_stops():
    expected = {m: {'recall': .5, 'by_family': {'x': .4}, 'ap': .2} for m in METHODS}
    actual = {m: {'recall': .5, 'by_family': {'x': .4}, 'ap': .2 + 1e-9} for m in METHODS}
    result = baseline_comparison(actual, expected)
    assert result['status'] == 'passed'
    assert result['ap_diagnostic_only']['L3']['delta'] > 0
    actual['L3']['recall'] = .49
    with pytest.raises(ValueError, match='operating decisions'):
        baseline_comparison(actual, expected)
