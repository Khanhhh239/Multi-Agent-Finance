"""Prepare a synthetic-only local UI fixture using the existing Rules policy.

This fixture is not the configuration selected by the v4 method study.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent2.pipeline_v4 import run
from agent2.review_store_v4 import ReviewStore
from agent2.sealed_v4 import file_hashes


def main():
    root = Path("work/ui_smoke")
    root.mkdir(parents=True, exist_ok=True)
    config = {"schema_version": 2, "profile": "cold", "budget": 3, "qa_fixture_only": True,
              "frozen": {"chosen": "Rules+Graph (friend)", "cold_start": "Rules+Graph (friend)", "hashes": file_hashes(Path("."))},
              "minimum_history_rows": 20, "calibration_days": 90, "input_data_kind": "synthetic"}
    cfg = root / "config.json"
    cfg.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    report, cases = run(Path("work/data/w4_s411"), root / "run", cfg, "2025-W40", "C001")
    store = ReviewStore(root / "review.sqlite")
    ingest = store.add_ingest("C001", root / "run/input_snapshot", {"data_kind": "synthetic", "qa_fixture_only": True})
    store.add_score("C001", ingest, "2025-W40", cases.to_dict("records"), report)
    (root / "tenants.json").write_text(json.dumps({"C001": "synthetic-ui-test", "EMPTY": "synthetic-empty-company"}), encoding="utf-8")
    print(json.dumps({"data_kind": "synthetic", "qa_fixture_only": True, "cases": len(cases), "ingest_id": ingest, "report": report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
