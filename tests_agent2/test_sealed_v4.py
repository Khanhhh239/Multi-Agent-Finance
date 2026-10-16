import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent2 import sealed_v4


def invoke(monkeypatch, tmp_path, frozen=None):
    out = tmp_path / "sealed.json"
    freeze = tmp_path / "freeze.json"
    if frozen is not None:
        freeze.write_text(json.dumps(frozen), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["sealed_v4", "--dev", "unused_dev", "--sealed", "unused_sealed",
                                     "--frozen", str(freeze), "--out", str(out)])
    monkeypatch.setattr(sealed_v4, "prepare", lambda _: pytest.fail("guard must precede loading data"))
    return out


def test_existing_output_refused_before_loading_data(monkeypatch, tmp_path):
    out = invoke(monkeypatch, tmp_path)
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="once only"):
        sealed_v4.main()


def test_changed_hash_refused_before_loading_data(monkeypatch, tmp_path):
    invoke(monkeypatch, tmp_path, {"hashes": {"changed": "wrong"}})
    with pytest.raises(SystemExit, match="code changed"):
        sealed_v4.main()


def test_known_novel_and_new_decoy_rates():
    novel = next(iter(sealed_v4.NOVEL))
    te = pd.DataFrame({"company_id": ["a"] * 5, "case_id": ["k", "n", "n", "", ""],
                       "is_fraud": [1, 1, 1, 0, 0], "fraud_type": ["known", novel, novel, "", ""],
                       "hard_negative_type": ["", "", "", sealed_v4.NEW_DECOYS[0], ""],
                       "t": pd.to_datetime(["2025-07-01"] * 5), "week": ["2025-W27"] * 5,
                       "vendor_id": ["v"] * 5, "employee_id": [""] * 5, "creator_id": ["e"] * 5})
    r = sealed_v4.report(te, {"model": np.array([True, False, True, True, False])}, {})["model"]
    assert r["known_recall"] == 1
    assert r["novel_recall"] == .5
    assert r["novel_case_recall"] == 1
    assert r["new_decoy_alert_rate"] == 1


def test_driver_masks_novel_history_and_persists_before_printing(monkeypatch, tmp_path):
    novel = next(iter(sealed_v4.NOVEL))
    frame = pd.DataFrame({"split": ["train", "validation", "test"],
                          "fraud_type": [novel] * 3, "is_fraud": [1] * 3})
    freeze = tmp_path / "frozen.json"
    freeze.write_text(json.dumps({"hashes": sealed_v4.file_hashes(Path(".")), "chosen": "m"}))
    out = tmp_path / "nested" / "result.json"
    monkeypatch.setattr(sys, "argv", ["sealed_v4", "--dev", "dev", "--sealed", "smoke",
                                     "--frozen", str(freeze), "--out", str(out)])
    monkeypatch.setattr(sealed_v4, "prepare", lambda _: frame.copy())
    calls = []

    def run(train, valid, test, **kwargs):
        calls.append((train.copy(), valid.copy(), test.copy(), kwargs))
        return {}, {}, {}

    monkeypatch.setattr(sealed_v4, "run_candidates", run)
    monkeypatch.setattr(sealed_v4, "alerts_for", lambda *args: ({}, {}))
    metrics = {k: .5 for k in ("recall", "known_recall", "novel_recall", "case_recall", "hard_neg_alert_rate")}
    monkeypatch.setattr(sealed_v4, "report", lambda *args: {"m": metrics})

    def verify_print(*args, **kwargs):
        assert json.loads(out.read_text())["worlds"]["smoke"]["test_novel_rows"] == 1

    monkeypatch.setattr("builtins.print", verify_print)
    sealed_v4.main()
    assert calls[0][0].is_fraud.tolist() == [0]
    assert calls[0][1].fraud_type.tolist() == [""]
    assert calls[0][2].is_fraud.tolist() == [1]
    pd.testing.assert_frame_equal(calls[1][3]["ref_for_novelty"], frame[frame.split == "validation"])


def test_development_pool_preserves_rows_order_dtypes_and_omits_test(monkeypatch):
    worlds = [pd.DataFrame({"split": ["train", "validation", "test"],
                            "is_fraud": [0, 1, 1], "company_id": [name] * 3,
                            "value": np.array([1, 2, 3], dtype=np.float32)}) for name in ("a", "b", "c")]
    monkeypatch.setattr(sealed_v4, "prepare", lambda path: worlds[path].copy())
    train, valid = sealed_v4.development_pool([0, 1, 2])
    for split, actual in (("train", train), ("validation", valid)):
        expected = pd.concat([w[w.split == split] for w in worlds], ignore_index=True)
        pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected)
