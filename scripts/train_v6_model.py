"""Train the deployable v6 secondary-score model on all twenty development worlds (dữ liệu tổng hợp).

  python scripts/train_v6_model.py --out results/v6/v6_secondary_score.joblib
Writes the bundle and results/v6/v6_model.json (sha256, configuration, validation AP). Needs work/v5_matrices.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from agent2.runtime_v5 import limit_memory, write_json  # noqa: E402
from agent2.v6_model import train_final  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--matrices", type=Path, default=Path("work/v5_matrices"))
    p.add_argument("--out", type=Path, default=Path("results/v6/v6_secondary_score.joblib"))
    p.add_argument("--threads", type=int, default=6)
    a = p.parse_args()
    limit_memory(10)
    frozen = json.loads(Path("results/v6/v6_frozen.json").read_text(encoding="utf-8"))
    began = time.monotonic()
    digest, meta = train_final(a.matrices, a.out, w=frozen["w"], hn=frozen["hn"], fraction=frozen["fraction"], threads=a.threads)
    write_json(a.out.with_name("v6_model.json"), {"sha256": digest, "file": a.out.name, "seconds": time.monotonic() - began,
                                                   "frozen_candidate": frozen["supervised"], **meta})
    print(json.dumps({"sha256": digest, "seconds": round(time.monotonic() - began)}))


if __name__ == "__main__":
    main()
