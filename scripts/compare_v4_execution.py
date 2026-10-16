"""Require identical alert decisions and numerical metrics across execution modes."""
import argparse
import json
import math
from pathlib import Path

import numpy as np


def compare(reference, candidate, world):
    with np.load(reference / f"{world}_P1_alerts.npz", allow_pickle=False) as a, np.load(candidate / f"{world}_P1_alerts.npz", allow_pickle=False) as b:
        assert set(a.files) == set(b.files)
        for name in a.files:
            np.testing.assert_array_equal(a[name], b[name], err_msg=name)
        rows, policies = len(a["transaction_id"]), len(a["names"])
    before = json.loads((reference / f"{world}.json").read_text(encoding="utf-8"))
    after = json.loads((candidate / f"{world}.json").read_text(encoding="utf-8"))
    errors = []

    def visit(a, b):
        if isinstance(a, dict):
            assert set(a) == set(b)
            for key in a:
                if key != "seconds":
                    visit(a[key], b[key])
        elif isinstance(a, (int, float)):
            if math.isnan(a) and math.isnan(b):
                return
            np.testing.assert_allclose(a, b, rtol=0, atol=1e-12, equal_nan=True)
            errors.append(abs(a - b))
        else:
            assert a == b
    visit(before["P1"], after["P1"])
    return {"status": "passed", "data_kind": "synthetic", "world": world, "test_rows": rows,
            "policies": policies, "changed_alert_flags": 0, "maximum_metric_absolute_difference": max(errors, default=0),
            "serial_P1_seconds": before["P1_seconds"], "parallel_P1_seconds": after["P1_seconds"],
            "parallel_workers": after["candidate_workers"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--world", default="w4_s411")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = compare(a.reference, a.candidate, a.world)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
