import json

import joblib
import pytest

from agent2.deployment_v4 import serializable_model
from agent2.hybrid import Collective
from agent2.train_pretrained_v4 import train
from agent2.sealed_v4 import file_hashes
from pathlib import Path


def test_sealed_world_cannot_be_a_training_input(tmp_path):
    with pytest.raises(ValueError, match="411/412"):
        train([tmp_path / "s4_s931", tmp_path / "w4_s412"], tmp_path / "w4_s413",
              tmp_path / "unused", tmp_path / "unused", tmp_path / "model.joblib")


def test_training_requires_complete_matching_one_shot_report(tmp_path):
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps({"chosen": "L3", "hashes": {}}))
    sealed = tmp_path / "sealed.json"
    sealed.write_text(json.dumps({"frozen": {"chosen": "L3", "hashes": {}}, "worlds": {"v4s_smoke": {}}}))
    with pytest.raises(ValueError, match="A5 complete"):
        train([tmp_path / "w4_s411", tmp_path / "w4_s412"], tmp_path / "w4_s413",
              frozen, sealed, tmp_path / "model.joblib")


def test_collective_training_closure_removed_without_mutating_original(tmp_path):
    original = Collective(lambda: None, "collective")
    export = serializable_model(original)
    assert original.base_factory is not None
    assert export.base_factory is None
    joblib.dump(export, tmp_path / "model.joblib")
    assert joblib.load(tmp_path / "model.joblib").base_factory is None


def test_global_stop_cannot_be_bypassed_by_training_cli(tmp_path):
    frozen = {'chosen': 'L3', 'hashes': file_hashes(Path('.'))}
    freeze_path, report = tmp_path / 'frozen.json', tmp_path / 'report.json'
    freeze_path.write_text(json.dumps(frozen))
    world = {scenario: {'L3': {'recall': .4, 'hard_neg_alert_rate': .1}} for scenario in ('S1', 'S2')}
    report.write_text(json.dumps({'frozen': frozen, 'worlds': {f's4_s{seed}': world for seed in (931, 932, 933)}}))
    with pytest.raises(ValueError, match='M2 global stop'):
        train([tmp_path / 'w4_s411', tmp_path / 'w4_s412'], tmp_path / 'w4_s413',
              freeze_path, report, tmp_path / 'model.joblib')
    assert not (tmp_path / 'model.joblib').exists()
