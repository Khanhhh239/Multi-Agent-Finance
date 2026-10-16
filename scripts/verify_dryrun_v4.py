"""Verify A4 completeness without scoring any true sealed world."""
import json
import argparse
from pathlib import Path

import pandas as pd

from agent2.eval_v4 import CANDIDATES, POLICIES
from agent2.world_v4_sealed import NOVEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('work/results/sealed_v4_dryrun.json'))
    parser.add_argument('--out', type=Path, default=Path('results/v4/dryrun_verification.json'))
    args = parser.parse_args()
    source = Path("work/data/v4s_smoke")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    frozen = json.loads(Path("work/results/v4_frozen.json").read_text(encoding="utf-8"))
    assert report["frozen"] == frozen
    assert set(report["worlds"]) == {"v4s_smoke"}
    world = report["worlds"]["v4s_smoke"]
    names = set(CANDIDATES) | {p[0] for p in POLICIES}
    for scenario in ("S1", "S2"):
        assert set(world[scenario]) == names
        for name in names:
            assert {"known_recall", "novel_recall", "new_decoy_alert_rate", "by_family"} <= set(world[scenario][name])
    labels = pd.read_csv(source / "labels.csv", keep_default_na=False)
    splits = pd.read_csv(source / "splits.csv", keep_default_na=False)
    test = labels.merge(splits, on="transaction_id", validate="one_to_one").query("split == 'test'")
    count = int(test.fraud_type.isin(NOVEL).sum())
    assert world["test_novel_rows"] == count
    assert world["test_fraud_rows"] == int(test.is_fraud.sum())
    validation = json.loads((source / "validation_v4.json").read_text(encoding="utf-8"))
    assert validation["status"] == "passed"
    output = {"status": "passed", "world": source.name, "seed": 939, "rows": validation["rows"],
              "policies_per_scenario": len(names), "test_fraud_rows": world["test_fraud_rows"],
              "test_novel_rows_from_labels": count, "frozen_matches": True}
    output['execution_max_concurrent_candidates'] = report.get('execution_max_concurrent_candidates', 3)
    args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
