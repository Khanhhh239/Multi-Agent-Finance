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
