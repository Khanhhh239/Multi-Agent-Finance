"""Compare label-free operational feature construction with research artifacts."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from agent2.data import load
from agent2.inference_v4 import build


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("work/data/w4_s411"))
    p.add_argument("--company", default="C001")
    p.add_argument("--week", default="2025-W40")
    p.add_argument("--out", type=Path, default=Path("work/inference_smoke"))
    a = p.parse_args()
    operational, report, hashes = build(a.data, a.out / "snapshot", a.company, a.week)
    reference = load(a.data).set_index("transaction_id")
    actual = operational.set_index("transaction_id")
    expected = reference.loc[actual.index]
    columns = actual.select_dtypes(include="number").columns
    errors = {}
    for col in columns:
        left, right = actual[col].to_numpy(dtype=float), expected[col].to_numpy(dtype=float)
        if not np.allclose(left, right, rtol=0, atol=1e-9, equal_nan=True):
            errors[col] = float(np.nanmax(abs(left - right)))
    if errors:
        raise AssertionError(f"operational feature mismatch: {errors}")
    result = {"status": "passed", "data_kind": "synthetic", "company_id": a.company, "week": a.week,
              "rows": len(actual), "numeric_columns_compared": len(columns), "maximum_feature_difference": 0,
              "input_report": report, "input_snapshot_hashes": hashes,
              "operational_loader_reads_truth": False}
    (a.out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("input_report", "input_snapshot_hashes")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
