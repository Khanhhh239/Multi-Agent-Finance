"""Registered v5 sealed gates and measurement (synthetic test doubles)."""
import numpy as np
import pandas as pd
import pytest

import agent2.sealed_v5 as S


def world(recall, novel, hard):
    return {"recall": recall, "novel_recall": novel, "hard_negative_rate": hard}


def test_gates_require_every_registered_condition():
    frozen = {"dev_S2_recall_mean": .70, "cold": None}
    ok = {"worlds": {str(s): {"S2": world(.66, .40, .12)} for s in range(4)}}
    g = S.gates(ok, frozen)
    assert g["S2"]["passed"] and not g["Cold"]["passed"]
    low_floor = {"worlds": {**ok["worlds"], "3": {"S2": world(.44, .40, .12)}}}
    assert not S.gates(low_floor, frozen)["S2"]["checks"]["V5-S2 sàn"]
    gap = S.gates(ok, {"dev_S2_recall_mean": .85, "cold": None})
    assert not gap["S2"]["checks"]["V5-S2 lệch dev"] and not gap["S2"]["passed"]
    hard = {"worlds": {**ok["worlds"], "2": {"S2": world(.70, .40, .151)}}}
    assert not S.gates(hard, frozen)["S2"]["passed"]


def test_cold_gate_only_when_frozen_cold_exists():
    frozen = {"dev_S2_recall_mean": .66, "cold": "Cold-v4"}
    w = {str(s): {"S2": world(.66, .40, .12), "Cold": world(.36, .31, .10)} for s in range(4)}
    g = S.gates({"worlds": w}, frozen)
    assert g["Cold"]["passed"]
    w["0"]["Cold"] = world(.24, .31, .10)
    assert not S.gates({"worlds": w}, frozen)["Cold"]["checks"]["V5-Cold sàn"]


def test_measure_separates_known_novel_and_new_decoys():
    te = pd.DataFrame({"is_fraud": [1, 1, 1, 0, 0, 0], "fraud_type": ["known", "nov", "nov", "", "", ""],
                       "hard_negative_type": ["", "", "", "old", "new_x", ""], "case_id": ["a", "b", "b", "", "", ""]})
    flags = np.array([True, True, False, True, False, False])
    m = S.measure(te, flags, {"nov"}, {"new_x"})
    assert m["recall"] == pytest.approx(2 / 3) and m["known_recall"] == 1 and m["novel_recall"] == .5
    assert m["hard_negative_rate"] == .5 and m["new_hard_negative_rate"] == 0
    assert m["novel_cases"] == 1 and m["cases"] == 2


def test_freeze_refuses_when_pre_seal_gate_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "R2", tmp_path)
    monkeypatch.setattr(S, "FROZEN", tmp_path / "frozen.json")
    (tmp_path / "selection_summary.json").write_text('{"gate": {"passed": false}, "chosen": null}', encoding="utf-8")
    (tmp_path / "cold_selection.json").write_text('{"gate": null, "chosen": null}', encoding="utf-8")
    with pytest.raises(SystemExit, match="pre-seal gate did not pass"):
        S.freeze()
    assert not (tmp_path / "frozen.json").exists()
