import json
import pickle
import shutil

import numpy as np
import pandas as pd
import pytest

from agent2 import methods as M
from agent2.alerting import benjamini_hochberg, conformal_pvalues, select_alerts
from agent2.feats import ENGINEERED, engineered_features
from agent2.metrics import evaluate_scores, weekly_alerts
from agent2.validate_v3 import validate_v3
from agent2.world_v3 import FAMILIES_V3, generate_v3


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    out = tmp_path_factory.mktemp("w3") / "d"
    generate_v3(out, n=10_000, rate=.005, seed=11, companies=3)
    return out


def test_world_validates_and_has_all_families(world):
    report = validate_v3(world, strict_artifacts=False)
    assert report["status"] == "passed"
    assert set(report["families"]) == set(FAMILIES_V3)
    assert {"easy", "medium", "hard"} <= set(report["difficulty"])
    assert report["max_share_vendors_same_onboard_day"] < .05           # v2 had 100 percent on 2023-01-01
    assert report["max_share_same_distinctive_name"] < .15              # v2 had one shared prefix


def test_no_truth_in_transactions_or_features(world):
    tx = pd.read_csv(world / "transactions.csv", nrows=3)
    assert not {"is_fraud", "fraud_type", "case_id", "difficulty", "variant"} & set(tx.columns)
    feats = pd.read_csv(world / "features.csv", nrows=3)
    assert "is_fraud" not in feats.columns and "transaction_id" in feats.columns


def test_unit_price_present_for_vendor_rows(world):
    tx = pd.read_csv(world / "transactions.csv", keep_default_na=False)
    vendor_rows = tx[tx.vendor_id != ""]
    assert (pd.to_numeric(vendor_rows.unit_price_vnd, errors="coerce") > 0).mean() > .99


def test_engineered_features_are_causal(world, tmp_path):
    full = engineered_features(world).set_index("transaction_id")
    tx = pd.read_csv(world / "transactions.csv", keep_default_na=False, dtype=str)
    cutoff = sorted(tx.posted_at)[int(len(tx) * .6)]
    part = tmp_path / "part"
    part.mkdir()
    tx[tx.posted_at < cutoff].to_csv(part / "transactions.csv", index=False)
    shutil.copy(world / "employees.csv", part / "employees.csv")
    early = engineered_features(part).set_index("transaction_id")
    common = early.index.intersection(full.index)
    assert len(common) > 1000
    pd.testing.assert_frame_equal(early.loc[common, ENGINEERED].sort_index(), full.loc[common, ENGINEERED].sort_index(), check_exact=False, atol=1e-9)


def test_weekly_budget_is_respected():
    df = pd.DataFrame({"company_id": ["A"] * 20 + ["B"] * 20, "week": [0] * 10 + [1] * 10 + [0] * 20})
    s = np.random.default_rng(0).random(40)
    for b in (1, 3):
        alerts = weekly_alerts(df, s, b)
        counts = df.assign(a=alerts).groupby(["company_id", "week"])["a"].sum()
        assert counts.max() == b


def test_metrics_perfect_and_random():
    n = 4000
    df = pd.DataFrame({"company_id": "A", "week": np.arange(n) // 100, "is_fraud": 0, "case_id": "", "hard_negative_type": "",
                       "t": pd.Timestamp("2025-01-01") + pd.to_timedelta(np.arange(n), unit="h"), "vendor_id": "", "employee_id": "", "creator_id": "u"})
    df.loc[::200, "is_fraud"] = 1
    df.loc[df.is_fraud == 1, "case_id"] = [f"c{i}" for i in range(int(df.is_fraud.sum()))]
    perfect = evaluate_scores(df, df.is_fraud.to_numpy() * 1.0)
    assert perfect["ap"] > .99 and perfect["r_precision"] > .99
    rand = evaluate_scores(df, np.random.default_rng(1).random(n))
    assert rand["ap"] < .1


def test_ecod_flags_the_extreme_row():
    rng = np.random.default_rng(0)
    train = pd.DataFrame({"a": rng.normal(size=2000), "b": rng.normal(size=2000)})
    m = M.ECOD(lambda d: ["a", "b"]).fit(train)
    test = pd.DataFrame({"a": [0.0, 8.0], "b": [0.0, 0.0]})
    s = m.score(test)
    assert s[1] > s[0]
    assert m.explain(test, 1)[1][0][0] == "a"


def test_gate_keeps_rule_order():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"rule_graph": rng.integers(0, 6, 500).astype(float), "x": rng.normal(size=500)})
    g = M.Gate(M.RuleScore("rule_graph", "r"), M.ECOD(lambda d: ["x"], name="e"), eps=.5).fit(df, df)
    s = g.score(df)
    hi, lo = df.rule_graph.to_numpy() >= 3, df.rule_graph.to_numpy() <= 2
    assert s[hi].min() >= s[lo].max()           # rule points dominate: the unsupervised band is only 0..0.5
    order = np.argsort(-s)
    assert df.rule_graph.to_numpy()[order[:10]].min() >= 4


def test_entity_deviation_flags_price_jump_and_pickles(world):
    df = pd.read_csv(world / "features.csv")
    eng = engineered_features(world)
    lab = pd.read_csv(world / "labels.csv", keep_default_na=False)
    d = df.merge(eng, on="transaction_id").merge(lab[["transaction_id", "is_fraud"]], on="transaction_id")
    m = M.EntityDeviation().fit(d)
    d2 = d.copy()
    mask = d2.price_n >= 6
    d2.loc[mask, "price_shift3"] = 2.0                      # inject a clear sustained price jump
    assert m.score(d2)[mask.to_numpy()].mean() > m.score(d)[mask.to_numpy()].mean()
    clone = pickle.loads(pickle.dumps(m))
    np.testing.assert_allclose(clone.score(d), m.score(d))


def test_conformal_pvalues_are_valid_under_exchangeability():
    rng = np.random.default_rng(0)
    cal = rng.normal(size=5000)
    p = conformal_pvalues(cal, rng.normal(size=20000))
    assert abs((p <= .05).mean() - .05) < .01
    keep = benjamini_hochberg(p, .05)
    assert keep.mean() < .01                                  # nothing to find in pure noise


def test_hard_triggers_not_demoted_in_feedback():
    from agent2.feedback_sim import simulate
    n = 600
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"week": np.arange(n) // 60, "company_id": "A", "is_fraud": 0, "case_id": "", "vendor_id": "", "employee_id": "",
                       "creator_id": [f"u{i%7}" for i in range(n)], "rule_hard": 0.0})
    df.loc[::97, "is_fraud"] = 1
    df.loc[df.is_fraud == 1, "case_id"] = [f"c{i}" for i in range(int(df.is_fraud.sum()))]
    df.loc[::97, "rule_hard"] = 1.0
    base = rng.random(n) * .5
    base[::97] = 1.0
    x = rng.random((n, 5))
    r = simulate(df, x, base, np.zeros(n, int), "reweight+audit", budget=2, seed=1)
    assert r["tp_rows"] >= df.is_fraud.sum() * .8


def test_slot_split_sums_to_budget():
    from agent2.pipeline import slots
    for b in range(1, 8):
        a, e = slots(b)
        assert a + e == b and a >= e


def test_select_mixed_respects_budget_and_adds_novelty():
    from agent2.alerting import select_mixed
    n = 60
    df = pd.DataFrame({"company_id": "A", "week": [0] * n})
    exploit = np.arange(n, dtype=float)             # exploit voice prefers high index
    novelty = -np.arange(n, dtype=float)            # novelty voice prefers low index
    alerts = select_mixed(df, exploit, novelty, 2, 1)
    assert alerts.sum() == 3
    assert alerts[-1] and alerts[-2] and alerts[0]


def test_reasons_are_ordered_by_learned_rule_weight():
    from agent2.alerting import reasons_for_row
    row = pd.Series({"rule_ids": "C1|B1", "explanation_vi": "x"})
    out = reasons_for_row(row, {}, {"C1": .1, "B1": 2.0}, top=1)
    from sme_fraud.rules import RULE_NAMES
    assert out == [RULE_NAMES["B1"]]


def test_review_page_embeds_cases(tmp_path):
    from agent2.review_page import build
    cases = pd.DataFrame({"case_id": ["AG2_000001"], "company_id": ["C001"], "entity": ["C001:V1"], "priority": ["cao"], "case_score": [.9],
                          "reason": ["Tài khoản NCC trùng nhân viên"], "action_vi": ["Kiểm tra"], "total_amount_vnd": [1000000], "rows": [1],
                          "opened_at": ["2025-01-01T00:00:00"]})
    csv = tmp_path / "c.csv"
    cases.to_csv(csv, index=False)
    out = tmp_path / "r.html"
    assert build(csv, out) == 1
    text = out.read_text(encoding="utf-8")
    assert "AG2_000001" in text and "Xác nhận bất thường thật" in text and "__DATA__" not in text
