import json

import joblib
import pytest

from agent2.deployment_v4 import serializable_model
from agent2.hybrid import Collective
from agent2.train_pretrained_v4 import train


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
