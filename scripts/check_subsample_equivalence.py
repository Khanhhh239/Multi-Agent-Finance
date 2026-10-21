"""Registered infrastructure check (R1 v1.2): does negative subsampling change the S2 model? (dữ liệu tổng hợp)

Fits the same candidate on one target with negative_fraction = 1.0 and 0.1 (fixed 400 trees, PU w = 0.2) and
compares the target scores. Pass: Spearman >= 0.95 and |recall@B3 difference| <= 2 percentage points.
Run BEFORE any screening; if it fails, repeat with fraction 0.2 and record both runs.
  python scripts/check_subsample_equivalence.py --target 1001 --kind L4-PU --fraction 0.1
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, ".")
from agent2.base_v5 import fit_source  # noqa: E402
from agent2.metrics import tie_break, weekly_alerts  # noqa: E402
from agent2.runtime_v5 import limit_memory, write_json  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=int, default=1001)
    p.add_argument("--kind", default="L4-PU")
    p.add_argument("--fraction", type=float, default=.1)
    p.add_argument("--matrices", type=Path, default=Path("work/v5_matrices"))
    p.add_argument("--out", type=Path, default=Path("results/v5/subsample_equivalence.json"))
    a = p.parse_args()
    limit_memory(6)
    te = pd.read_parquet(a.matrices / f"s{a.target}" / "test.parquet")
    runs = {}
    for fraction in (1.0, a.fraction):
        scores, details = fit_source(a.target, a.matrices, None, .2, kind=a.kind, max_rounds=400, early_stop=None,
                                     negative_fraction=fraction)
        alerts = weekly_alerts(te, scores + tie_break(len(te), 5), 3)
        pos = te.is_fraud.to_numpy() == 1
        runs[fraction] = dict(scores=scores, recall=float(alerts[pos].mean()), details=details)
        print(fraction, runs[fraction]["recall"], details["source_train_rows"], flush=True)
    rho = float(spearmanr(runs[1.0]["scores"], runs[a.fraction]["scores"]).statistic)
    diff = 100 * (runs[a.fraction]["recall"] - runs[1.0]["recall"])
    result = {"data_origin": "dữ liệu tổng hợp", "target": a.target, "kind": a.kind, "fraction": a.fraction,
              "spearman": rho, "recall_full": runs[1.0]["recall"], "recall_subsampled": runs[a.fraction]["recall"],
              "recall_difference_points": diff, "passed": rho >= .95 and abs(diff) <= 2,
              "details": {str(k): v["details"] for k, v in runs.items()}}
    write_json(a.out, result)
    print(json.dumps({k: result[k] for k in ("spearman", "recall_difference_points", "passed")}))


if __name__ == "__main__":
    main()
