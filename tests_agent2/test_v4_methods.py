"""Tests for the v4 method study (hybrid.py) and the sealed v4 world."""
import numpy as np
import pandas as pd
import pytest

from agent2.hybrid import Novelty, family_weights, memory_features
from agent2.world_v4_schemes import SCHEMES
from agent2.world_v4_sealed import NOVEL


def test_memory_features_match_bruteforce_and_are_causal():
    rng = np.random.default_rng(0)
    n = 300
    t = pd.Timestamp("2024-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 300, n)), "D") + pd.to_timedelta(rng.integers(0, 86400, n), "s")
    f = pd.DataFrame({"company_id": rng.choice(["C1", "C2"], n), "t": t, "r": rng.random(n),
                      "creator_id": rng.choice(["a", "b", ""], n)}).sample(frac=1, random_state=2)
    m = memory_features(f)
    for i, row in f.iterrows():
        if row.creator_id == "":
            assert m.loc[i, "m_creator_id_one"] == 0
            continue
        past = f[(f.company_id == row.company_id) & (f.creator_id == row.creator_id) & (f.t < row.t) & (f.t >= row.t - pd.Timedelta("90D"))]
        assert m.loc[i, "m_creator_id_one"] == len(past)
        assert m.loc[i, "m_creator_id_max"] == pytest.approx(past.r.max() if len(past) else 0.0)
        assert m.loc[i, "m_creator_id_hi"] == (past.r >= .99).sum()


def test_family_weights_give_each_family_equal_mass():
    d = pd.DataFrame({"is_fraud": [0, 0, 1, 1, 1, 1, 1], "fraud_type": ["", "", "a", "a", "a", "a", "b"]})
    w = family_weights(d)
    assert w[:2].tolist() == [1, 1]
    assert w[2:6].sum() == pytest.approx(w[6]) and w[2:].sum() == pytest.approx(5)


def test_novelty_uses_reference_ranks_only():
    ref = pd.DataFrame({"rule_graph": np.arange(100.0), "u_entity": np.zeros(100)})
    m = Novelty().fit(None, ref)
    s = m.score(pd.DataFrame({"rule_graph": [-1.0, 1000.0], "u_entity": [0.0, 0.0]}))
    assert s[1] > s[0] and s.max() <= 1.01


def test_sealed_schemes_are_new():
    assert not set(NOVEL) & set(SCHEMES)
    assert len(NOVEL) == 7


def test_sealed_world_small_is_valid(tmp_path):
    from agent2.validate_v4 import validate_v4
    from agent2.world_v4_sealed import generate_v4_sealed
    out = tmp_path / "s"
    generate_v4_sealed(out, n=60_000, rate=.004, seed=977, companies=14)
    r = validate_v4(out, run_shortcut=False)
    assert r["status"] == "passed"
    assert len(set(NOVEL) & set(r["rows_per_scheme"])) >= 6
    assert {"legit_volume_discount", "legit_extra_withdrawal", "legit_tax_installment"} <= set(r["decoys"])


def test_accounting_extension_keeps_source_validation_and_feature_contract():
    from agent2 import accounting_ext
    from sme_fraud.exception_validation import validated_record
    from sme_fraud.features import FEATURE_DESCRIPTIONS
    from sme_fraud.generate import PAIRS

    original_pairs = dict(PAIRS)
    original_features = dict(FEATURE_DESCRIPTIONS)
    accounting_ext.install()
    assert PAIRS == original_pairs
    assert FEATURE_DESCRIPTIONS == original_features
    assert set(accounting_ext.NEW_KINDS).isdisjoint(PAIRS)
    record = dict(transaction_id="EXT_TX", company_id="EXT_COMPANY")
    for kind in accounting_ext.NEW_KINDS:
        assert validated_record("transactions", dict(record, txn_type=kind))["txn_type"] == kind
    with pytest.raises(ValueError, match="unknown transaction type"):
        validated_record("transactions", dict(record, txn_type="cash_withdrawal_typo"))
    with pytest.raises(ValueError, match="goods_receipt_verified"):
        validated_record("transactions", dict(record, txn_type="cash_withdrawal", goods_receipt_verified=2))
