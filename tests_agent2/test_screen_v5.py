"""screen_v5 runner on tiny synthetic matrices (dữ liệu tổng hợp)."""
import numpy as np
import pandas as pd
import pytest

import agent2.screen_v5 as S
from agent2.base_v5 import change_feature_names
from agent2.runtime_v5 import write_json

BR = list(S.BRANCHES)


@pytest.fixture()
def matrices(tmp_path, monkeypatch):
    monkeypatch.setattr(S, 'ROUNDS', 15)
    rng = np.random.default_rng(3)
    names = change_feature_names()
    for seed in S.WORLDS:
        d = tmp_path / f's{seed}'
        d.mkdir()
        write_json(d / 'manifest.json', dict(columns=['x', 'z', 'q'], L3_columns=['x', 'z']))
        write_json(d / 'manifest_cd.json', dict(columns=names, files={}))
        for split, n in [('train', 300), ('validation', 150), ('test', 210)]:
            y = np.arange(n) % 7 == 0
            branch = np.where(y, np.array(BR)[np.arange(n) % len(BR)], '')
            x = rng.normal(size=(n, 3)).astype(np.float32)
            x[:, 0] += 2 * y
            np.save(d / f'{split}.npy', x)
            np.save(d / f'{split}_cd.npy', rng.normal(size=(n, len(names))).astype(np.float32))
            pd.DataFrame(dict(transaction_id=[f'{seed}:{i}' for i in range(n)], company_id=np.where(np.arange(n) % 2, 'A', 'B'),
                              is_fraud=y.astype(int), fraud_type=np.where(y, branch, ''), case_id='', branch=branch,
                              hard_negative_type=np.where(np.arange(n) % 11 == 0, 'legit', ''), week=np.arange(n) // 30,
                              t=0, rule_graph=rng.random(n), u_entity=rng.random(n))).to_parquet(d / f'{split}.parquet', index=False)
    return tmp_path


def test_link_shortcut_columns_are_removed_and_max_recomputed(matrices):
    names = change_feature_names()
    seq = S.CleanChangeSequence(matrices / 's1001' / 'train_cd.npy', names)
    raw = np.load(matrices / 's1001' / 'train_cd.npy')
    out = seq[0:10]
    kept = [i for i, n in enumerate(names) if n not in S.LINK_SHORTCUT]
    det = [i for i, n in enumerate(names) if n[-1] in '+-' and n not in S.LINK_SHORTCUT]
    np.testing.assert_allclose(out[:, :-1], raw[:10, kept])
    np.testing.assert_allclose(out[:, -1], raw[:10, det].max(axis=1))
    assert out.shape[1] == len(S.clean_change_names(matrices))
    assert not set(S.clean_change_names(matrices)) & (S.LINK_SHORTCUT - {'ed2_score'})
    np.testing.assert_allclose(seq[3], out[3])


def test_label_swapping_equals_fresh_dataset(matrices):
    pool = S.SourcePool(1001, matrices, 'L4-PU-E2-AR', 1.0)
    pool.fit_score(None, .2, 0)
    reused, _ = pool.fit_score(BR[0], .2, 0)
    fresh, _ = S.SourcePool(1001, matrices, 'L4-PU-E2-AR', 1.0).fit_score(BR[0], .2, 0)
    np.testing.assert_allclose(reused, fresh, rtol=1e-6)


def test_subsampled_pool_keeps_every_fraud_row(matrices):
    full = S.SourcePool(1001, matrices, 'L3-PU', 1.0)
    sub = S.SourcePool(1001, matrices, 'L3-PU', .2)
    assert sub.meta.is_fraud.sum() == full.meta.is_fraud.sum()
    assert sub.rows < .5 * full.rows
    plain = (sub.meta.is_fraud == 0) & (sub.meta.hard_negative_type == '')
    assert np.allclose(sub.meta.factor[plain], 5.0)


def test_world_runs_produce_registered_summaries(matrices, tmp_path):
    out = tmp_path / 'out'
    sup = S.run_supervised('L4-PU-E2-AR', 1001, out, matrices, .2, (0, 1), 1.0)
    assert set(sup) >= {'R', 'B', 'Q', 'eligible'}
    two = S.run_two_plus_one(1001, out, matrices)
    cold = S.run_cold('Cold-Rules-E2', 1001, out, matrices)
    cold4 = S.run_cold('Cold-v4', 1001, out, matrices)
    for s in (sup, two, cold, cold4):
        assert 0 <= s['Q'] <= 1
    again = S.run_supervised('L4-PU-E2-AR', 1001, out, matrices, .2, (0, 1), 1.0)   # resume: no refit
    assert again == sup


def test_hard_negative_weight_only_changes_confirmed_legitimate_hard_negatives():
    from agent2.base_v5 import observed_labels
    meta = pd.DataFrame(dict(is_fraud=[1, 0, 0, 0, 1], fraud_type=['a', '', '', '', 'b'], branch=['x', '', '', '', 'y'],
                             hard_negative_type=['', '', 'legit_x', '', '']))
    y0, w0 = observed_labels(meta, None, False, .1)
    y1, w1 = observed_labels(meta, None, False, .1, None)
    assert (y0 == y1).all() and (w0 == w1).all()                       # v5 behaviour is unchanged by default
    y2, w2 = observed_labels(meta, None, False, .1, 1.0)
    assert (y2 == y0).all()                                            # labels never change
    assert list(w2) == [1., .1, 1., .1, 1.]                            # only the hard-negative row moved from w to h
    _, w3 = observed_labels(meta, 'x', False, .1, 2.0)                 # a hidden branch stays unknown at w, not at h
    assert w3[0] == .1 and w3[2] == 2.0
    with pytest.raises(ValueError, match='Unregistered hard-negative weight'):
        observed_labels(meta, None, False, .1, .3)


def test_hn_stage_locks_h_and_screening_uses_it(matrices, tmp_path, monkeypatch):
    import json
    import sys
    out = tmp_path / 'R6'
    out.mkdir()
    write_json(out / 'PU_locked.json', {'status': 'inherited_from_v5', 'w': .1, 'data_origin': 'dữ liệu tổng hợp'})
    monkeypatch.setattr(S, 'limit_memory', lambda *_: None)
    import agent2.select_v5 as SEL
    tiny = {'screening': ((1001, 1002), 1), 'selection': ((1001, 1002), 1)}
    monkeypatch.setattr(S, 'TIERS', tiny)
    monkeypatch.setattr(SEL, 'TIERS', tiny)
    monkeypatch.setattr(S, 'HN_WEIGHTS', (.5, 1.))
    monkeypatch.setattr(sys, 'argv', ['screen_v5', 'hn', '--matrices', str(matrices), '--output', str(out), '--fraction', '1',
                                      '--threads', '2'])
    S.main()
    locked = json.loads((out / 'HN_locked.json').read_text(encoding='utf-8'))
    assert locked['status'] in ('locked', 'no_eligible_hn_weight') and set(locked['J']) == {'0.5', '1.0'}
    assert (out / 'hn_0.5' / 'L4-FB-PU' / 's1001' / 'summary.json').exists()
