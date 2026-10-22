import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from agent2.explain_check import check
from agent2.inference_v4 import TABLES, week_bounds
from agent2.pipeline import Agent2Detector
from agent2.pipeline_v4 import run
from agent2.sealed_v4 import file_hashes
from agent2.world_v4 import generate_v4


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("operational_v4")
    raw = root / "raw"
    generate_v4(raw, n=30_000, rate=.004, seed=481, companies=8)
    source = root / "unlabelled"
    source.mkdir()
    for name in TABLES:
        if (raw / f"{name}.csv").exists():
            shutil.copy2(raw / f"{name}.csv", source / f"{name}.csv")
    return source


def config():
    return {"schema_version": 2, "profile": "cold", "budget": 3,
            "frozen": {"chosen": "Rules+Graph (friend)", "cold_start": "Rules+Graph (friend)", "hashes": file_hashes(Path("."))},
            "minimum_history_rows": 20, "calibration_days": 90, "input_data_kind": "synthetic_test"}


def test_unlabelled_weekly_pipeline_budget_and_future_invariance(world, tmp_path):
    before = tmp_path / "before"
    report, cases = run(world, before, config(), "2025-W40", "C001")
    alerts = pd.read_csv(before / "alerts.csv", keep_default_na=False)
    start, end = week_bounds("2025-W40")
    dates = pd.to_datetime(alerts.posted_at, utc=True)
    assert ((dates >= start) & (dates < end)).all()
    assert report["alert_rows"] <= 3
    assert report["change_observations"] == "used"
    assert set(cases.company_id) <= {"C001"}
    assert all(cases.reason.str.len() > 0)
    assert not json.loads((before / "run_manifest.json").read_text())["labels_read"]
    for line in (before / "explanations.jsonl").read_text(encoding="utf-8").splitlines():
        assert all(check(x["text"], x["evidence"])["ok"] for x in json.loads(line)["observations"])
    future_world = tmp_path / "future"
    shutil.copytree(world, future_world)
    tx = pd.read_csv(future_world / "transactions.csv", dtype=str, keep_default_na=False)
    row = tx[tx.company_id == "C001"].iloc[[0]].copy()
    row["transaction_id"] = "FUTURE_CHANGED"
    row["posted_at"], row["approved_at"], row["created_at"] = ["2025-12-29T12:00:00+07:00", "2025-12-29T11:00:00+07:00", "2025-12-29T10:00:00+07:00"]
    row["amount_vnd"] = "999999999999999"
    pd.concat([tx, row], ignore_index=True).to_csv(future_world / "transactions.csv", index=False, encoding="utf-8-sig")
    after = tmp_path / "after"
    run(future_world, after, config(), "2025-W40", "C001")
    pd.testing.assert_frame_equal(alerts, pd.read_csv(after / "alerts.csv", keep_default_na=False))


def test_from_config_refuses_changed_frozen_feature_code():
    cfg = config()
    cfg["frozen"]["hashes"]["agent2/feats.py"] = "changed"
    with pytest.raises(ValueError, match="feature code"):
        Agent2Detector.from_config(cfg)
