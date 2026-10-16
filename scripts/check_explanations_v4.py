"""Check every rendered v4 observation on frozen-policy P1 development alerts."""
import json
from pathlib import Path

import numpy as np

from agent2.eval_v4 import prepare
from agent2.explain_check import check
from agent2.explain_v4 import V4_REASONS, observations


def main():
    frozen = json.loads(Path("results/v4/v4_frozen.json").read_text(encoding="utf-8"))
    output = {"data_kind": "synthetic", "policy": frozen["chosen"], "scope": "P1 v4 observation templates; not unrestricted semantic entailment", "worlds": {}}
    coverage = set()
    for seed in (411, 412, 413):
        name = f"w4_s{seed}"
        frame = prepare(Path("work/data") / name)
        test = frame[frame.split == "test"].reset_index(drop=True)
        with np.load(Path("work/results/v4_methods") / f"{name}_P1_alerts.npz", allow_pickle=False) as saved:
            np.testing.assert_array_equal(test.transaction_id.to_numpy(), saved["transaction_id"])
            flags = saved["alerts"][saved["names"].tolist().index(frozen["chosen"])]
        count, empty, failed = 0, 0, []
        for row in test[flags].to_dict("records"):
            reasons = observations(row)
            empty += not bool(reasons)
            for item in reasons:
                coverage.add(item["feature"])
                count += 1
                if not check(item["text"], item["evidence"])["ok"]:
                    failed.append(row["transaction_id"])
        output["worlds"][name] = {"alert_rows": int(flags.sum()), "v4_observations_checked": count,
                                    "rows_without_v4_observation": empty, "unsupported_numeric_values": len(failed)}
        assert not failed
    output["template_coverage"] = sorted(coverage)
    output["templates_not_observed"] = sorted(set(V4_REASONS) - coverage)
    output["status"] = "passed"
    Path("results/v4/explanation_fidelity.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
