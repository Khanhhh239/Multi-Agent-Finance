"""Subsampling, concatenated streams and the change-feature candidate in base_v5 (dữ liệu tổng hợp)."""
import numpy as np
import pandas as pd

from agent2.base_v5 import (ConcatSequence, MatrixSequence, SubsetSequence, change_feature_names, fit_source,
                            negative_subsample)
from agent2.runtime_v5 import write_json


def test_concat_and_subset_sequences_match_dense(tmp_path):
    rng = np.random.default_rng(5)
    a, b = rng.normal(size=(50, 4)).astype(np.float32), rng.normal(size=(50, 3)).astype(np.float32)
    np.save(tmp_path / "a.npy", a)
    np.save(tmp_path / "b.npy", b)
    dense = np.hstack([a[:, [2, 0]], b])
    seq = ConcatSequence([MatrixSequence(tmp_path / "a.npy", [2, 0]), MatrixSequence(tmp_path / "b.npy")])
    np.testing.assert_allclose(seq[3:9], dense[3:9])
    np.testing.assert_allclose(seq[7], dense[7])
    rows = np.array([1, 4, 5, 6, 30, 49])
    sub = SubsetSequence(seq, rows)
    assert len(sub) == 6
    np.testing.assert_allclose(sub[0:6], dense[rows])
    np.testing.assert_allclose(sub[4], dense[30])


def test_negative_subsample_keeps_positives_and_hard_negatives_and_reweights():
    n = 10_000
    meta = pd.DataFrame({"hard_negative_type": np.where(np.arange(n) % 97 == 0, "legit_x", "")})
    y = (np.arange(n) % 50 == 0).astype(np.int8)
    index, factor = negative_subsample(meta, y, .1, 1001)
    kept_y, kept_hard = y[index], meta.hard_negative_type.to_numpy()[index] != ""
    assert kept_y.sum() == y.sum()
    assert kept_hard.sum() == (meta.hard_negative_type != "").sum()
    plain = (kept_y == 0) & ~kept_hard
    assert np.allclose(factor[plain], 10.0) and np.allclose(factor[~plain], 1.0)
    # expected total weight of plain negatives is preserved within sampling error
    assert abs(factor[plain].sum() - ((y == 0) & (meta.hard_negative_type == "")).sum()) / n < .05
    index2, _ = negative_subsample(meta, y, .1, 1001)
    np.testing.assert_array_equal(index, index2)                     # deterministic per world


def _worlds(tmp_path, with_change):
    rng = np.random.default_rng(34)
    names = change_feature_names()
    for seed in range(1001, 1021):
        d = tmp_path / f"s{seed}"
        d.mkdir()
        write_json(d / "manifest.json", dict(columns=["x", "z"], L3_columns=["x"]))
        if with_change:
            write_json(d / "manifest_cd.json", dict(columns=names, files={}))
        for split, n in [("train", 400), ("validation", 120), ("test", 60)]:
            y = np.arange(n) % 8 == 0
            x = rng.normal(size=(n, 2)).astype(np.float32)
            np.save(d / f"{split}.npy", x)
            cd = rng.normal(size=(n, len(names))).astype(np.float32)
            cd[:, 0] += 2.5 * y                                          # signal only in a change feature
            np.save(d / f"{split}_cd.npy", cd)
            branch = np.where(y, np.where(np.arange(n) % 16 == 0, "a", "b"), "")
            pd.DataFrame(dict(is_fraud=y.astype(int), branch=branch, fraud_type=np.where(y, branch, ""),
                              hard_negative_type="")).to_parquet(d / f"{split}.parquet", index=False)


def test_change_candidate_uses_change_features_and_fixed_rounds(tmp_path):
    _worlds(tmp_path, True)
    s_base, d_base = fit_source(1001, tmp_path, None, .2, kind="L4-PU", max_rounds=40, early_stop=None)
    s_cd, d_cd = fit_source(1001, tmp_path, None, .2, kind="L4-PU-E2-AR", max_rounds=40, early_stop=None)
    y = np.arange(60) % 8 == 0
    from sklearn.metrics import roc_auc_score
    assert roc_auc_score(y, s_cd) > roc_auc_score(y, s_base) + .2
    assert d_cd["trees"] == 40 and d_cd["round_policy"] == "fixed" and "warning" not in d_cd


def test_subsampled_fit_reports_rows_and_keeps_all_positives(tmp_path):
    _worlds(tmp_path, False)
    _, full = fit_source(1001, tmp_path, None, .2, kind="L4-PU", max_rounds=20, early_stop=None)
    _, sub = fit_source(1001, tmp_path, None, .2, kind="L4-PU", max_rounds=20, early_stop=None, negative_fraction=.25)
    assert sub["source_observed_train_positives"] == full["source_observed_train_positives"]
    assert sub["source_train_rows"] < .45 * full["source_train_rows"]
