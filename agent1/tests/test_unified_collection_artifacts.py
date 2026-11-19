import hashlib
import json
import zipfile

import pytest

from experiments.unified_collection_v2 import artifacts, data
from experiments.unified_collection_v2.verify import regression_audit


def snapshot(directory):
    directory.mkdir(parents=True)
    original = b"measured benchmark code\n"
    hashes = {"experiments/retired/source.py": hashlib.sha256(original).hexdigest()}
    (directory/"source_hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    with zipfile.ZipFile(directory/"source_snapshot.zip", "w") as archive:
        archive.writestr(next(iter(hashes)), original)


def test_snapshot_verifies_retired_source_without_importing_it(tmp_path):
    directory = tmp_path/"saved"
    snapshot(directory)
    result = artifacts.verify_source_snapshot(directory)
    assert result["frozen_source_snapshot_verified"]
    assert not result["active_source_matches_snapshot"]
    with zipfile.ZipFile(directory/"source_snapshot.zip", "w") as archive:
        archive.writestr("experiments/retired/source.py", b"tampered code")
    with pytest.raises(ValueError, match="snapshot changed"):
        artifacts.verify_source_snapshot(directory)


@pytest.mark.parametrize("changed", ["model.txt", "decision.json"])
def test_saved_run_rejects_changed_weights_or_verdict(tmp_path, monkeypatch, changed):
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    directory = tmp_path/"outputs/data/example"
    snapshot(directory)
    (directory/"model.txt").write_text("weights", encoding="utf-8")
    (directory/"decision.json").write_text('{"research_passed": false}', encoding="utf-8")
    files = {f.relative_to(tmp_path).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in directory.iterdir()}
    maintenance = tmp_path/"outputs/maintenance/unified_v1_removal_20261104.json"
    maintenance.parent.mkdir()
    maintenance.write_text(json.dumps({"preserved_files_sha256": files}), encoding="utf-8")
    assert artifacts.verify_saved_run(directory)["artifact_files_verified"] == 4
    (directory/changed).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Historical artifact changed"):
        artifacts.verify_saved_run(directory)


def test_frozen_output_refuses_source_rewrite_before_preparation(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "ROOT", tmp_path)
    monkeypatch.setattr(data, "source_hashes", lambda: {"new.py": "new"})
    directory = tmp_path/"outputs/data/unified_collection_v2_frozen"
    directory.mkdir(parents=True)
    locked = directory/"source_hashes.json"
    locked.write_text('{"old.py": "old"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen run source differs"):
        data.prepare({"output_directory": "outputs/data/unified_collection_v2_frozen"})
    assert json.loads(locked.read_text()) == {"old.py": "old"}
    assert sorted(f.name for f in directory.iterdir()) == ["source_hashes.json"]


def test_protection_excludes_only_the_current_run(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "ROOT", tmp_path)
    monkeypatch.setattr(data, "old_protected", lambda: {})
    current = tmp_path/"outputs/data/unified_collection_v2_current"
    old = tmp_path/"outputs/data/unified_collection_v2_old"
    for directory in (current, old):
        directory.mkdir(parents=True)
        (directory/"model.txt").write_text("weights")
    protected = data.protected_files(current)
    assert set(protected) == {"outputs/data/unified_collection_v2_old/model.txt"}


def test_minimal_fixture_preserves_both_daily_accounting_regressions(tmp_path):
    result = regression_audit(tmp_path)
    assert result["passed"]
    balances = {r["firm_id"]: r["true_week13_balance"] for r in result["cases"]}
    assert balances["F000"] == pytest.approx(-361507975.54138, abs=1)
    assert balances["F003"] == pytest.approx(-538265404.59485, abs=1)
    assert all(r["fee_bridge_max_error_vnd"] <= 1 and r["oracle_daily_policy_max_error_vnd"] <= 1
               for r in result["cases"])
