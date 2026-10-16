import json

from agent2.repro_v4 import check_fingerprints


def test_missing_or_mismatched_fingerprint_blocks_progress(tmp_path):
    assert check_fingerprints(tmp_path, ["w4_s411"])["status"] == "blocked"
    directory = tmp_path / "w4_s411"
    directory.mkdir()
    path = directory / "validation_v4.json"
    path.write_text(json.dumps({"status": "passed", "fraud_rows": 800, "cases": 194, "schemes": 30}))
    assert check_fingerprints(tmp_path, ["w4_s411"])["status"] == "passed"
    path.write_text(json.dumps({"status": "passed", "fraud_rows": 800, "cases": 193, "schemes": 30}))
    assert check_fingerprints(tmp_path, ["w4_s411"])["worlds"]["w4_s411"]["status"] == "mismatch"
