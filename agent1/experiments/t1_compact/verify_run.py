"""Independent recomputation of the frozen candidate and its data provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import CompactT1, FEATURES, sha256
from experiments.t1_compact.train import metrics


def verify(output):
    output = output.resolve()
    result = json.loads((output/"test_results.json").read_text(encoding="utf-8"))
    inventory = json.loads((output/"inventory.json").read_text(encoding="utf-8"))
    sources = json.loads((output/"source_snapshot.json").read_text(encoding="utf-8"))
    audit = json.loads((output/"data_audit.json").read_text(encoding="utf-8"))
    meta = json.loads((output/"artifact/metadata.json").read_text(encoding="utf-8"))
    checked = 0
    for entry in inventory:
        manifest = output/entry["directory"]/"replay_manifest.json"
        assert sha256(manifest) == entry["replay_manifest_sha256"]
        replay = json.loads(manifest.read_text(encoding="utf-8"))
        for file, expected in replay["files"].items():
            assert sha256(manifest.parent/file) == expected
            checked += 1
    for entry in audit:
        assert sha256(output/"prepared"/(entry["world"]+".parquet")) == entry["sha256"]
        assert sha256(output/"protocol.json") == entry["protocol_sha256"]
        checked += 1
    for entry in sources:
        assert sha256(output/"runtime_source"/entry["path"]) == entry["sha256"]
        checked += 1
    assert sha256(output/"runtime_source/agent1/adaptive/compact_t1.py") == meta["source_sha256"]
    assert sha256(output/"runtime_source/experiments/t1_compact/train.py") == meta["training_script_sha256"]
    assert sha256(output/"artifact/metadata.json") == result["artifact_metadata_sha256"]
    fingerprint = hashlib.sha256(json.dumps(audit, sort_keys=True).encode()).hexdigest()
    assert fingerprint == meta["data_fingerprint"]
    roles = {e["name"]: e["role"] for e in inventory}
    assert len(roles) == 14
    model = CompactT1.load(output/"artifact")
    test = pd.concat([pd.read_parquet(output/"prepared"/(e["name"]+".parquet")) for e in inventory if e["role"] == "test"], ignore_index=True)
    assert set(test.world).isdisjoint({w for w, role in roles.items() if role != "test"})
    measured, firms, worlds = metrics(model, test)
    for key, value in measured.items():
        assert np.isclose(value, result["candidate"][key], atol=1e-12, rtol=0)
    p = model.distribution_from_features(test[list(FEATURES)].to_numpy(float))
    assert p.shape == (len(test), 14)
    assert np.isfinite(p).all() and (p >= 0).all()
    np.testing.assert_allclose(p.sum(1), 1, atol=1e-12)
    explanations = 0
    for path in (output/"workspace_plans").glob("*.json"):
        plan = json.loads(path.read_text(encoding="utf-8"))
        for row in plan["collections"]:
            exp = row["payment_explanation"]
            assert exp["protocol"] == "compact-t1-grouped-exact-v1"
            assert exp["coalition_count"] <= 64 and exp["background_count"] <= 24
            assert abs(exp["baseline_probability"]+sum(f["contribution"] for f in exp["factors"])-row["payment_probability_4w"]) < 1e-10
            explanations += 1
    report = dict(passed=True, payload_and_source_hashes_checked=checked,
                  test_anchors_recomputed=len(test), test_firms=len(firms), test_worlds=len(worlds),
                  active_state_inputs=len(model.active), estimator_inputs=model.booster.num_feature(),
                  probabilities_normalized=True, workspace_explanations_reconstructed=explanations,
                  artifact_metadata_sha256=sha256(output/"artifact/metadata.json"))
    (output/"verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    verify(parser.parse_args().output)
