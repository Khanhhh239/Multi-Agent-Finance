"""Domain distance of one real company-week export against the synthetic development matrices (never reads labels).

  python scripts/domain_distance.py --data export_dir --company C001 --week 2025-W40 --out result.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from agent2.domain_distance import domain_distance  # noqa: E402
from agent2.inference_v4 import build  # noqa: E402


def reference(matrices, worlds, rows_each=4000, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for w in worlds:
        d = Path(matrices) / f"s{w}"
        columns = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["columns"]
        x = np.load(d / "train.npy", mmap_mode="r")
        idx = np.sort(rng.choice(len(x), min(rows_each, len(x)), replace=False))
        frames.append(pd.DataFrame(np.asarray(x[idx], dtype=np.float32), columns=columns))
    return pd.concat(frames, ignore_index=True), columns


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--week", required=True)
    p.add_argument("--matrices", type=Path, default=Path("work/v5_matrices"))
    p.add_argument("--worlds", type=int, nargs="+", default=[1001, 1005, 1010, 1015, 1020])
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    frame, _, _ = build(a.data, a.out.parent / "domain_snapshot", a.company, a.week)
    ref, columns = reference(a.matrices, a.worlds)
    result = domain_distance(frame, ref, columns)
    result.update(company=a.company, week=a.week, real_rows=int(len(frame)), reference_worlds=a.worlds, data_origin="see run")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(json.dumps(result, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps({k: result[k] for k in ("auc", "distance", "advice")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
